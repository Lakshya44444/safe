"""HTTP API end to end with the offline mock LLM."""

from tests import _env  # noqa: F401  (must be first)

import unittest

from starlette.testclient import TestClient

from app.server import app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app)
        cls.c = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_meta(self):
        m = self.c.get("/api/meta").json()
        self.assertEqual(len(m["streams"]), 4)
        self.assertTrue(m["llm_chain"][0].startswith("mock"))

    def test_report_with_note(self):
        r = self.c.post("/api/reports?wait=1", data={"bhawan": "govind bhawan", "bin_stream": "geela",
                                                     "note": "polythene on top"})
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual((body["bhawan"], body["bin_stream"], body["status"]), ("Govind", "wet", "graded"))
        self.assertTrue(body["tag"].startswith(("Needs attention", "Oops")))
        self.assertNotIn("photo_path", body)

    def test_report_with_photo(self):
        r = self.c.post("/api/reports?wait=1", data={"bhawan": "Rajiv", "bin_stream": "dry"},
                        files={"photo": ("bin.png", PNG, "image/png")})
        self.assertEqual(r.status_code, 201, r.text)
        url = r.json()["photo_url"]
        self.assertEqual(self.c.get(url).status_code, 200)

    def test_rejects_non_image_upload(self):
        r = self.c.post("/api/reports", data={"bhawan": "Rajiv", "bin_stream": "dry"},
                        files={"photo": ("x.png", b"<script>", "image/png")})
        self.assertEqual(r.status_code, 400)

    def test_validation_errors(self):
        self.assertEqual(self.c.post("/api/reports", data={"bhawan": "nowhere", "bin_stream": "wet",
                                                           "note": "x"}).status_code, 400)
        self.assertEqual(self.c.post("/api/reports", data={"bhawan": "Azad", "bin_stream": "wet"}).status_code, 400)
        self.assertEqual(self.c.get("/api/leaderboard?days=abc").status_code, 400)

    def test_unreadable_note_is_reported_not_crashed(self):
        r = self.c.post("/api/reports?wait=1", data={"bhawan": "Azad", "bin_stream": "wet", "note": "hello"})
        self.assertEqual(r.json()["status"], "failed")
        self.assertIn("doesn't say what is in the bin", r.json()["error"])

    def test_path_traversal_blocked(self):
        self.assertEqual(self.c.get("/api/photos/..%2F..%2Fapp%2Fconfig.py").status_code, 404)

    def test_issues_flow(self):
        r = self.c.post("/api/issues", json={"bhawan": "Ganga", "kind": "bin is full"})
        self.assertEqual(r.status_code, 201)
        iid = r.json()["id"]
        self.assertTrue(any(i["id"] == iid and i["kind"] == "overflow" for i in self.c.get("/api/issues").json()))
        self.assertEqual(self.c.post(f"/api/issues/{iid}/resolve").json()["status"], "resolved")

    def test_agent_tools(self):
        say = self.c.post("/api/agent/report", json={"bhawan": "Indira", "bin_stream": "dry",
                                                     "note": "all clean"}).json()
        self.assertTrue(say["ok"])
        self.assertIn("grade A", say["say"])
        self.assertFalse(self.c.post("/api/agent/report", json={"bhawan": "??", "bin_stream": "dry"}).json()["ok"])
        self.assertIn("Complaint number", self.c.post("/api/agent/issue", json={"bhawan": "Indira",
                                                                                "note": "pickup missed"}).json()["say"])
        self.assertIn("Indira", self.c.post("/api/agent/score", json={"bhawan": "indira"}).json()["say"])

    def test_briefing_and_dashboard(self):
        b = self.c.get("/api/briefing/Govind").json()
        self.assertTrue(b["text"].startswith("Good evening"))
        self.assertIsNone(b["audio_url"])  # no ElevenLabs key in tests
        self.assertIn("segregation_rate", self.c.get("/api/summary").json())
        self.assertIsInstance(self.c.get("/api/leaderboard").json(), list)
        self.assertIn("chain", self.c.get("/api/llm/stats").json())


if __name__ == "__main__":
    unittest.main()
