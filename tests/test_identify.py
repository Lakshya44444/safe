"""Item identification: correct bin for each found item, and hazard flags for worker safety."""

from tests import _env  # noqa: F401  (must be first)

import unittest

from starlette.testclient import TestClient

from app import db, scoring
from app.identify import identify
from app.server import app


class Identify(unittest.TestCase):
    def test_belongs(self):
        got = {x["item"]: x["belongs"] for x in identify(["plastic bag", "food scraps", "medicine strip", "sanitary pad"], "dry")}
        self.assertEqual(got, {"plastic bag": "dry", "food scraps": "wet", "medicine strip": "special_care",
                               "sanitary pad": "sanitary"})

    def test_hazards(self):
        r = {x["item"]: x["hazard"] for x in identify(["battery", "syringe", "bottle", "diaper"], "wet")}
        self.assertEqual(r, {"battery": True, "syringe": True, "bottle": False, "diaper": True})
        self.assertIn("fire", identify(["battery"], "dry")[0]["why"])

    def test_hazard_in_its_own_bin_is_fine(self):
        self.assertFalse(identify(["battery"], "special_care")[0]["hazard"])
        self.assertFalse(identify(["diaper"], "sanitary")[0]["hazard"])
        self.assertTrue(identify(["blade"], "dry")[0]["hazard"])  # sharps are flagged in ordinary bins

    def test_unknown_item_not_guessed(self):
        x = identify(["mystery object"], "wet")[0]
        self.assertEqual((x["belongs"], x["hazard"]), (None, False))


class HazardFlow(unittest.TestCase):
    def test_report_shows_hazard_and_jumps_collection_order(self):
        with TestClient(app) as c:
            r = c.post("/api/reports?wait=1", data={"bhawan": "Cautley", "bin_stream": "wet",
                                                    "note": "a battery and food on top"}).json()
            self.assertTrue(r["hazard"])
            bat = next(x for x in r["identified"] if x["item"] == "battery")
            self.assertEqual(bat["belongs"], "special_care")
            plan = scoring.collection_plan()
            stop = next(p for p in plan if p["bhawan"] == "Cautley")
            self.assertEqual(stop["reasons"][0]["kind"], "hazard")
            self.assertGreaterEqual(stop["hazards_today"], 1)
            self.assertGreaterEqual(c.get("/api/summary").json()["hazards"]["bins"], 1)


if __name__ == "__main__":
    unittest.main()
