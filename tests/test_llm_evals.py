"""LLM evals as tests.

The grader eval suite runs offline here (replay fixtures), so a prompt, parser or grade-rule
change that breaks grading fails the build. Live-model numbers come from
`python -m evals.run_evals --provider gemini`.
"""

from tests import _env  # noqa: F401  (must be first)

import unittest

from evals import run_evals


class GraderEvalSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = run_evals.load_cases()
        cls.replay = run_evals.run("replay", cases=cls.cases)
        cls.mock = run_evals.run("mock", cases=cls.cases)

    def test_dataset_is_well_formed(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)), "duplicate case ids")
        tags = {t for c in self.cases for t in c.get("tags", [])}
        for needed in ("clean", "dirty", "hinglish", "injection", "unreadable"):
            self.assertIn(needed, tags, f"dataset needs at least one '{needed}' case")
        for c in self.cases:
            self.assertIn(c["stream"], ("wet", "dry", "sanitary", "special_care"))
            self.assertIn(c.get("expected_grade"), ("A", "B", "C", None))

    def test_replay_meets_all_thresholds(self):
        self.assertEqual(self.replay["failures"], [], self.replay["metrics"])

    def test_messy_model_output_is_parsed(self):
        # Fixtures include ```json fences, chatter before the JSON and "50%" strings.
        self.assertEqual(self.replay["metrics"]["errors"], 0)
        self.assertEqual(self.replay["metrics"]["json_first_pass_rate"], 1.0)

    def test_no_dirty_bin_graded_clean(self):
        self.assertEqual(self.replay["metrics"]["false_clean_rate"], 0.0)

    def test_prompt_injection_cases_not_graded_clean(self):
        inj = [r for r in self.replay["results"] if "injection" in r["tags"]]
        self.assertTrue(inj)
        for r in inj:
            self.assertIn(r["predicted_grade"], ("B", "C"), r)

    def test_evals_catch_a_weak_grader(self):
        # The keyword mock ignores which bin it is ("plastic" in a dry bin is fine), so the
        # suite must flag it. If this passes for the mock, the evals are too easy.
        self.assertTrue(self.mock["failures"], self.mock["metrics"])
        self.assertLess(self.mock["metrics"]["grade_accuracy"], run_evals.THRESHOLDS["grade_accuracy"])

    def test_check_reports_threshold_misses(self):
        m = dict(self.replay["metrics"], grade_accuracy=0.1, false_clean_rate=0.5)
        fails = run_evals.check(m)
        self.assertTrue(any("grade_accuracy" in f for f in fails))
        self.assertTrue(any("false_clean_rate" in f for f in fails))


if __name__ == "__main__":
    unittest.main()
