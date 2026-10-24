"""HTTP API end to end with the offline mock LLM."""

from tests import _env  # noqa: F401  (must be first)

import io
import threading
import time
import unittest

from PIL import Image
from starlette.testclient import TestClient

from app.llm_gateway import LLMGateway, LLMResponse, get_gateway, reset_gateway
from app.server import app


def png_bytes(size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (40, 140, 80)).save(buf, format="PNG")
    return buf.getvalue()


PNG = png_bytes()


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
        self.assertTrue(url.endswith(".jpg"))  # normalised to JPEG whatever was uploaded
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

    def test_corrupt_image_rejected(self):
        r = self.c.post("/api/reports", data={"bhawan": "Rajiv", "bin_stream": "dry"},
                        files={"photo": ("x.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "image/png")})
        self.assertEqual(r.status_code, 400)
        self.assertIn("could not be read", r.json()["error"])

    def test_oversized_request_rejected_before_reading(self):
        r = self.c.post("/api/issues", content=b"{}", headers={"content-length": str(50 * 1024 * 1024),
                                                               "content-type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_briefing_and_dashboard(self):
        b = self.c.get("/api/briefing/Govind").json()
        self.assertTrue(b["text"].startswith("Good evening"))
        self.assertIsNone(b["audio_url"])  # no ElevenLabs key in tests
        self.assertIn("segregation_rate", self.c.get("/api/summary").json())
        self.assertIsInstance(self.c.get("/api/leaderboard").json(), list)
        self.assertIn("chain", self.c.get("/api/llm/stats").json())


class NonBlocking(unittest.TestCase):
    """A slow LLM call must not freeze the server for everyone else."""

    def test_other_requests_answer_while_grading(self):
        class Slow:
            name, model = "slow", "slow"

            def complete(self, req):
                time.sleep(1.5)
                return LLMResponse(text='{"contamination_pct": 5}', provider="slow", model="slow")

        previous = get_gateway()
        reset_gateway(LLMGateway([Slow()]))
        try:
            with TestClient(app) as c:
                t = threading.Thread(target=lambda: c.post("/api/reports?wait=1", data={
                    "bhawan": "Azad", "bin_stream": "wet", "note": "clean"}))
                t.start()
                time.sleep(0.3)
                t0 = time.perf_counter()
                self.assertEqual(c.get("/api/health").status_code, 200)
                elapsed = time.perf_counter() - t0
                t.join()
            self.assertLess(elapsed, 0.5)
        finally:
            reset_gateway(previous)


if __name__ == "__main__":
    unittest.main()
