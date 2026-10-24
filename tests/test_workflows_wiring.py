"""Web service -> Render Workflows hand-off, with a stand-in for the Render SDK client.

The SDK's client signature (run_task(task_slug, input_data) -> TaskRunDetails with .results)
was checked against render-oss/sdk source; this test pins how we call it and read the result.
"""

from tests import _env  # noqa: F401  (must be first)

import sys
import types
import unittest
from unittest import mock

from app import config, db, pipeline


class FakeRun:
    def __init__(self, results):
        self.results = results


def fake_render_module(result, calls):
    class Workflows:
        def run_task(self, task_slug, input_data):
            calls.append((task_slug, input_data))
            return FakeRun([result])

    class Render:
        def __init__(self):
            self.workflows = Workflows()

    mod = types.ModuleType("render")
    mod.Render = Render
    return mod


class WorkflowsHandOff(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.env = mock.patch.multiple(config, RENDER_WORKFLOW_SLUG="kachra-wf", RENDER_API_KEY="rnd_x")
        self.env.start()

    def tearDown(self):
        self.env.stop()
        sys.modules.pop("render", None)

    def test_graded_by_workflow_task(self):
        calls = []
        result = {"grade": "C", "contamination": 50, "found_items": ["bottle"], "tag": "Oops! ...",
                  "confidence": 0.8, "provider": "gemini", "model": "m", "latency_ms": 900, "source": "note"}
        sys.modules["render"] = fake_render_module(result, calls)
        rid = db.create_report("Azad", "wet", None, "bottle on top", None)
        r = pipeline.process_report(rid)
        self.assertEqual((r["status"], r["grade"], r["provider"]), ("graded", "C", "gemini"))
        slug, payload = calls[0]
        self.assertEqual(slug, "kachra-wf/grade_bin_task")
        self.assertEqual(set(payload), {"photo_b64", "mime", "stream", "note"})

    def test_unreadable_from_workflow_is_shown_not_retried(self):
        sys.modules["render"] = fake_render_module({"unreadable": "Take the photo again."}, [])
        rid = db.create_report("Azad", "wet", None, "hello", None)
        r = pipeline.process_report(rid)
        self.assertEqual((r["status"], r["error"]), ("failed", "Take the photo again."))


if __name__ == "__main__":
    unittest.main()
