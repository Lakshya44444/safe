"""Core checks. Run:  python -m unittest discover -s tests"""

import os
import tempfile
import unittest

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["GRADER_PROVIDER"] = "mock"

from app import db, grader, scoring  # noqa: E402
from app.server import match_bhawan, match_stream  # noqa: E402


class GradeRule(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(grader.grade_from_contamination(0), "A")
        self.assertEqual(grader.grade_from_contamination(10), "A")
        self.assertEqual(grader.grade_from_contamination(11), "B")
        self.assertEqual(grader.grade_from_contamination(35), "B")
        self.assertEqual(grader.grade_from_contamination(36), "C")

    def test_tags(self):
        self.assertTrue(grader.make_tag("A", "wet", []).startswith("Shabash"))
        self.assertTrue(grader.make_tag("C", "wet", ["plastic bag"]).startswith("Oops"))
        self.assertIn("plastic bag", grader.make_tag("B", "dry", ["plastic bag"]))

    def test_mock_reads_worker_words(self):
        self.assertEqual(grader.grade_bin(None, "wet", "dabba saaf hai").grade, "A")
        bad = grader.grade_bin(None, "wet", "polythene aur bottle aur packet")
        self.assertEqual(bad.grade, "C")
        self.assertIn("plastic bag", bad.found_items)


class Matching(unittest.TestCase):
    def test_bhawan(self):
        self.assertEqual(match_bhawan("govind bhawan"), "Govind")
        self.assertEqual(match_bhawan("RAJENDRA"), "Rajendra")
        self.assertIsNone(match_bhawan("bhawan"))
        self.assertIsNone(match_bhawan("xyz"))

    def test_stream(self):
        self.assertEqual(match_stream("geela"), "wet")
        self.assertEqual(match_stream("special care"), "special_care")
        self.assertIsNone(match_stream("blue"))


class Scores(unittest.TestCase):
    def test_leaderboard_order(self):
        db.init_db()
        for note, b in [("saaf hai", "Azad"), ("saaf hai", "Azad"), ("polythene bottle packet", "Ganga")]:
            rid = db.create_report(b, "wet", "t", note, None)
            g = grader.grade_bin(None, "wet", note)
            db.save_grade(rid, g.grade, g.contamination, g.found_items, g.tag_hi)
        rows = scoring.bhawan_scores(7)
        self.assertEqual(rows[0]["bhawan"], "Azad")
        self.assertEqual(rows[0]["score"], 100)
        self.assertEqual(rows[-1]["bhawan"], "Ganga")
        self.assertEqual(rows[-1]["score"], 20)


class Issues(unittest.TestCase):
    def test_issue_flow(self):
        from app.server import match_issue_kind
        db.init_db()
        self.assertEqual(match_issue_kind("dabba bhar gaya"), "overflow")
        self.assertEqual(match_issue_kind("gaadi nahi aayi"), "missed_pickup")
        iid = db.create_issue("Govind", "overflow", "full", None)
        self.assertTrue(any(i["id"] == iid for i in db.list_issues("open")))
        self.assertEqual(db.resolve_issue(iid)["status"], "resolved")
        self.assertFalse(any(i["id"] == iid for i in db.list_issues("open")))


if __name__ == "__main__":
    unittest.main()
