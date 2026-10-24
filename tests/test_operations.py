"""Worker checks of AI grades, collection priority, forecast, impact and the compliance report."""

from tests import _env  # noqa: F401  (must be first)

import unittest
from datetime import datetime, timedelta, timezone

from starlette.testclient import TestClient

from app import config, db, grader, scoring
from app.server import app


def add(bhawan, stream, note, when=None):
    rid = db.create_report(bhawan, stream, "t", note, None, created_at=when)
    db.save_grade(rid, grader.grade_bin(None, stream, note))
    return rid


class WorkerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app)
        cls.c = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_agree_keeps_grade(self):
        rid = add("Rajiv", "wet", "bin is clean")
        r = self.c.post(f"/api/reports/{rid}/verdict", json={"agree": True}).json()
        self.assertEqual((r["verdict"], r["grade"], r["ai_grade"]), ("agree", "A", "A"))

    def test_correction_changes_score_and_keeps_ai_grade(self):
        rid = add("Ravindra", "wet", "bin is clean")  # AI says A
        r = self.c.post(f"/api/reports/{rid}/verdict", json={"agree": False, "grade": "C"}).json()
        self.assertEqual((r["verdict"], r["grade"], r["ai_grade"]), ("disagree", "C", "A"))
        self.assertTrue(r["tag"].startswith("Oops!"))
        row = next(x for x in scoring.bhawan_scores(7) if x["bhawan"] == "Ravindra")
        self.assertEqual(row["grades"]["C"], 1)
        stats = db.verdict_stats("2000-01-01")
        self.assertGreaterEqual(stats["ai_too_lenient"], 1)  # AI said A, worker said C

    def test_changing_mind_twice_keeps_original_ai_grade(self):
        rid = add("Rajendra", "dry", "plastic bag bottle packet")  # AI: C
        self.c.post(f"/api/reports/{rid}/verdict", json={"agree": False, "grade": "B"})
        r = self.c.post(f"/api/reports/{rid}/verdict", json={"agree": True}).json()
        self.assertEqual((r["ai_grade"], r["grade"]), ("C", "C"))

    def test_bad_verdicts(self):
        rid = add("Azad", "wet", "bin is clean")
        self.assertEqual(self.c.post(f"/api/reports/{rid}/verdict", json={"agree": False}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/reports/{rid}/verdict", json={"agree": False, "grade": "Z"}).status_code, 400)
        self.assertEqual(self.c.post("/api/reports/999999/verdict", json={"agree": True}).status_code, 404)

    def test_summary_reports_agreement_and_co2(self):
        s = self.c.get("/api/summary").json()
        self.assertIn("agreement_rate", s["worker_checks"])
        self.assertEqual(s["co2e_kg_avoided_estimate"],
                         round(s["wet_bins_compost_ready"] * config.KG_PER_WET_BIN * config.CO2E_KG_PER_KG_COMPOSTED))

    def test_compliance_report(self):
        r = self.c.get("/api/compliance?days=30").json()
        for key in ("summary", "bhawans", "issues", "forecast", "method"):
            self.assertIn(key, r)
        self.assertIn("EPA WARM", r["method"]["co2e_source"])


class CollectionPlan(unittest.TestCase):
    def test_overflow_ranks_first_and_older_is_more_urgent(self):
        now = datetime.now(timezone.utc)
        db.init_db()
        db.create_issue("Kasturba", "overflow", None, None, created_at=(now - timedelta(hours=20)).isoformat(timespec="seconds"))
        db.create_issue("Indira", "overflow", None, None, created_at=(now - timedelta(hours=1)).isoformat(timespec="seconds"))
        db.create_issue("Himalaya", "broken_bin", None, None, created_at=(now - timedelta(hours=1)).isoformat(timespec="seconds"))
        plan = [p for p in scoring.collection_plan() if p["bhawan"] in ("Kasturba", "Indira", "Himalaya")]
        self.assertEqual([p["bhawan"] for p in plan], ["Kasturba", "Indira", "Himalaya"])
        self.assertEqual(plan[0]["reasons"][0]["kind"], "overflow")


class Forecast(unittest.TestCase):
    def test_falling_bhawan_is_flagged(self):
        now = datetime.now(timezone.utc)
        notes = ["bin is clean", "bin is clean", "some plastic", "plastic bag bottle packet", "plastic bag bottle packet"]
        for d, note in enumerate(notes):  # oldest first: clean, clean, B, C, C
            when = (now - timedelta(days=len(notes) - 1 - d)).replace(hour=3).isoformat(timespec="seconds")
            add("Malviya", "wet", note, when)
        f = next(x for x in scoring.forecast(7) if x["bhawan"] == "Malviya")
        self.assertLess(f["slope_per_day"], 0)
        self.assertTrue(f["needs_nudge"])
        self.assertLessEqual(f["tomorrow"], f["last"])

    def test_slope(self):
        self.assertAlmostEqual(scoring._slope([10, 20, 30]), 10)
        self.assertEqual(scoring._slope([50]), 0)


if __name__ == "__main__":
    unittest.main()
