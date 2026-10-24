"""Provider wire formats: what we send to Gemini, Anthropic and ElevenLabs, and how we read the replies.

No network: requests.post is replaced by a fake that records the call and returns a canned reply
in each API's documented shape.
"""

from tests import _env  # noqa: F401  (must be first)

import base64
import io
import json
import os
import unittest
from unittest import mock

import requests
from PIL import Image

from app import config, grader, voice
from app.llm_gateway import ImageInput, LLMGateway, LLMRequest, ProviderError, reset_gateway
from app.llm_gateway.providers import AnthropicProvider, GeminiProvider


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b"", text=""):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, **kw):
        self.calls.append({"url": url, **kw})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


ASSESSMENT = {"readable": True, "contamination_pct": 40, "wrong_items": ["plastic bag"], "confidence": 0.8}
GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": json.dumps(ASSESSMENT)}]}, "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 812, "candidatesTokenCount": 31}}
ANTHROPIC_OK = {"content": [{"type": "text", "text": json.dumps(ASSESSMENT)}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 900, "output_tokens": 40}}


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 120, 60)).save(buf, format="JPEG")
    return buf.getvalue()


IMG = ImageInput(data=jpeg(), mime="image/jpeg")


class Gemini(unittest.TestCase):
    def test_request_shape(self):
        rec = Recorder(FakeResponse(200, GEMINI_OK))
        with mock.patch("app.llm_gateway.providers.requests.post", rec):
            resp = GeminiProvider("AQ.test-key", "gemini-2.5-flash").complete(
                LLMRequest(task="t", prompt="grade it", image=IMG, system="sys"))
        call = rec.calls[0]
        self.assertTrue(call["url"].endswith("/v1beta/models/gemini-2.5-flash:generateContent"))
        self.assertEqual(call["headers"], {"x-goog-api-key": "AQ.test-key"})
        self.assertNotIn("key=", call["url"])  # key never in the URL
        body = call["json"]
        parts = body["contents"][0]["parts"]
        self.assertEqual(parts[0], {"text": "grade it"})
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(base64.b64decode(parts[1]["inline_data"]["data"]), IMG.data)
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "sys"}]})
        self.assertEqual((resp.provider, resp.input_tokens, resp.output_tokens), ("gemini", 812, 31))
        self.assertEqual(json.loads(resp.text), ASSESSMENT)

    def test_error_mapping(self):
        cases = [(429, True), (503, True), (400, False), (403, False)]
        for status, retryable in cases:
            rec = Recorder(FakeResponse(status, {"error": {"message": "x"}}))
            with mock.patch("app.llm_gateway.providers.requests.post", rec), self.assertRaises(ProviderError) as cm:
                GeminiProvider("k", "m").complete(LLMRequest(task="t", prompt="p"))
            self.assertEqual(cm.exception.retryable, retryable, status)

    def test_timeout_is_retryable(self):
        with mock.patch("app.llm_gateway.providers.requests.post", Recorder(requests.Timeout())), \
                self.assertRaises(ProviderError) as cm:
            GeminiProvider("k", "m").complete(LLMRequest(task="t", prompt="p"))
        self.assertTrue(cm.exception.retryable)

    def test_safety_block_has_no_text(self):
        blocked = {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
        with mock.patch("app.llm_gateway.providers.requests.post", Recorder(FakeResponse(200, blocked))), \
                self.assertRaises(ProviderError) as cm:
            GeminiProvider("k", "m").complete(LLMRequest(task="t", prompt="p"))
        self.assertIn("SAFETY", str(cm.exception))

    def test_empty_candidates_without_reason(self):
        with mock.patch("app.llm_gateway.providers.requests.post", Recorder(FakeResponse(200, {"candidates": []}))), \
                self.assertRaises(ProviderError):
            GeminiProvider("k", "m").complete(LLMRequest(task="t", prompt="p"))

    def test_missing_key(self):
        with self.assertRaises(ValueError):
            GeminiProvider("", "m")


class Anthropic(unittest.TestCase):
    def test_request_shape(self):
        rec = Recorder(FakeResponse(200, ANTHROPIC_OK))
        with mock.patch("app.llm_gateway.providers.requests.post", rec):
            resp = AnthropicProvider("sk-ant", "claude-x").complete(
                LLMRequest(task="t", prompt="grade it", image=IMG, system="sys", max_tokens=300))
        call = rec.calls[0]
        self.assertEqual(call["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(call["headers"]["x-api-key"], "sk-ant")
        self.assertEqual(call["headers"]["anthropic-version"], "2023-06-01")
        body = call["json"]
        self.assertEqual((body["model"], body["max_tokens"], body["system"]), ("claude-x", 300, "sys"))
        content = body["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "image")  # image before text, as recommended
        self.assertEqual(content[0]["source"]["media_type"], "image/jpeg")
        self.assertIn("grade it", content[1]["text"])
        self.assertIn("JSON", content[1]["text"])
        self.assertEqual((resp.input_tokens, resp.output_tokens), (900, 40))

    def test_overloaded_is_retryable(self):
        with mock.patch("app.llm_gateway.providers.requests.post", Recorder(FakeResponse(529, {"type": "error"}))), \
                self.assertRaises(ProviderError) as cm:
            AnthropicProvider("k", "m").complete(LLMRequest(task="t", prompt="p"))
        self.assertTrue(cm.exception.retryable)


class EndToEndGrading(unittest.TestCase):
    """Photo -> grader -> gateway -> (fake) Gemini HTTP -> GradeResult."""

    def setUp(self):
        self.photo = os.path.join(config.DATA_DIR, "e2e.jpg")
        config.ensure_dirs()
        with open(self.photo, "wb") as f:
            f.write(jpeg())

    def tearDown(self):
        reset_gateway(None)

    def test_photo_graded_by_gemini(self):
        rec = Recorder(FakeResponse(200, GEMINI_OK))
        reset_gateway(LLMGateway([GeminiProvider("k", "gemini-2.5-flash")]))
        with mock.patch("app.llm_gateway.providers.requests.post", rec):
            g = grader.grade_bin(self.photo, "wet")
        self.assertEqual((g.grade, g.contamination, g.provider, g.source), ("C", 40, "gemini", "photo"))
        self.assertIn("plastic bag", g.tag)
        prompt = rec.calls[0]["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn("WET bin", prompt)

    def test_gemini_down_falls_back_to_anthropic(self):
        rec = Recorder(FakeResponse(503, {}), FakeResponse(503, {}), FakeResponse(503, {}), FakeResponse(200, ANTHROPIC_OK))
        gw = LLMGateway([GeminiProvider("k", "g"), AnthropicProvider("k", "a")], max_retries=2, backoff_s=0)
        reset_gateway(gw)
        with mock.patch("app.llm_gateway.providers.requests.post", rec):
            g = grader.grade_bin(self.photo, "dry")
        self.assertEqual(g.provider, "anthropic")
        self.assertEqual([c["url"].split("/")[2] for c in rec.calls],
                         ["generativelanguage.googleapis.com"] * 3 + ["api.anthropic.com"])
        self.assertEqual(gw.stats()["tasks"]["grade_bin_photo"]["retries"], 2)


class ElevenLabs(unittest.TestCase):
    def setUp(self):
        self.patch = mock.patch.multiple(config, ELEVENLABS_API_KEY="sk_test", ELEVENLABS_VOICE_ID="voice123",
                                         ELEVENLABS_MODEL="eleven_multilingual_v2", ELEVENLABS_STT_MODEL="scribe_v1")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_tts_request_and_cache(self):
        rec = Recorder(FakeResponse(200, content=b"ID3-fake-mp3"))
        with mock.patch("app.voice.requests.post", rec):
            path1 = voice.synthesize("Good evening, Govind.")
            path2 = voice.synthesize("Good evening, Govind.")
        self.assertEqual(path1, path2)
        self.assertEqual(len(rec.calls), 1)  # second call served from the cache
        call = rec.calls[0]
        self.assertEqual(call["url"], "https://api.elevenlabs.io/v1/text-to-speech/voice123")
        self.assertEqual(call["headers"]["xi-api-key"], "sk_test")
        self.assertEqual(call["json"], {"text": "Good evening, Govind.", "model_id": "eleven_multilingual_v2"})
        with open(path1, "rb") as f:
            self.assertEqual(f.read(), b"ID3-fake-mp3")

    def test_tts_error_becomes_voice_error(self):
        with mock.patch("app.voice.requests.post", Recorder(FakeResponse(401, {"detail": "bad key"}))), \
                self.assertRaises(voice.VoiceError):
            voice.synthesize("something new")

    def test_stt_request(self):
        rec = Recorder(FakeResponse(200, {"text": " plastic bag in the wet bin ", "language_code": "eng"}))
        with mock.patch("app.voice.requests.post", rec):
            text = voice.transcribe(b"webm-bytes", "note.webm", "audio/webm")
        self.assertEqual(text, "plastic bag in the wet bin")
        call = rec.calls[0]
        self.assertEqual(call["url"], "https://api.elevenlabs.io/v1/speech-to-text")
        self.assertEqual(call["data"], {"model_id": "scribe_v1"})
        self.assertEqual(call["files"]["file"], ("note.webm", b"webm-bytes", "audio/webm"))


if __name__ == "__main__":
    unittest.main()
