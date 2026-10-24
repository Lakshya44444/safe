"""LLM gateway: parsing, schema validation, repair, retries, fallback, caching, stats."""

from tests import _env  # noqa: F401  (must be first)

import unittest

from pydantic import ValidationError

from app.llm_gateway import LLMGateway, LLMRequest, LLMResponse, ProviderError
from app.llm_gateway.gateway import extract_json
from app.models import BinAssessment


class ScriptedProvider:
    """Returns (or raises) the scripted items in order, and counts calls."""

    def __init__(self, name, script, model="m"):
        self.name, self.model, self.script, self.calls = name, model, list(script), 0

    def complete(self, request):
        self.calls += 1
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return LLMResponse(text=item, provider=self.name, model=self.model, latency_ms=5,
                           input_tokens=10, output_tokens=3)


def req(prompt="p", task="t"):
    return LLMRequest(task=task, prompt=prompt)


GOOD = '{"readable": true, "contamination_pct": 20, "wrong_items": ["bottle"], "confidence": 0.8}'


class ExtractJson(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_fenced(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_chatter_around(self):
        self.assertEqual(extract_json('Sure! Here it is: {"a": {"b": "}"}} hope that helps'), {"a": {"b": "}"}})

    def test_escaped_quote_in_string(self):
        self.assertEqual(extract_json(r'{"a": "say \"hi\" {"}'), {"a": 'say "hi" {'})

    def test_skips_broken_first_object(self):
        self.assertEqual(extract_json('{not json} then {"ok": true}'), {"ok": True})

    def test_none(self):
        with self.assertRaises(ValueError):
            extract_json("no json here")


class Schema(unittest.TestCase):
    def test_coercions(self):
        a = BinAssessment.model_validate({"contamination_pct": "35%", "wrong_items": [" Plastic  Bag ", "plastic bag"],
                                          "confidence": 80})
        self.assertEqual(a.contamination_pct, 35)
        self.assertEqual(a.wrong_items, ["plastic bag"])
        self.assertEqual(a.confidence, 0.8)

    def test_clamps_and_caps(self):
        a = BinAssessment.model_validate({"contamination_pct": 140, "wrong_items": [str(i) for i in range(10)]})
        self.assertEqual(a.contamination_pct, 100)
        self.assertEqual(len(a.wrong_items), 6)

    def test_missing_required(self):
        with self.assertRaises(ValidationError):
            BinAssessment.model_validate({"readable": True})


class Gateway(unittest.TestCase):
    def test_retries_retryable_then_succeeds(self):
        p = ScriptedProvider("p1", [ProviderError("429", provider="p1", retryable=True), GOOD])
        gw = LLMGateway([p], max_retries=2, backoff_s=0)
        resp = gw.complete(req())
        self.assertEqual(resp.attempts, 2)
        self.assertEqual(gw.stats()["tasks"]["t"]["retries"], 1)

    def test_non_retryable_falls_back_to_next_provider(self):
        bad = ScriptedProvider("bad", [ProviderError("401", provider="bad", retryable=False)])
        good = ScriptedProvider("good", [GOOD])
        gw = LLMGateway([bad, good], backoff_s=0)
        self.assertEqual(gw.complete(req()).provider, "good")
        self.assertEqual(bad.calls, 1)  # no pointless retries on auth errors

    def test_all_fail(self):
        bad = ScriptedProvider("bad", [ProviderError("down", provider="bad", retryable=True)])
        gw = LLMGateway([bad], max_retries=1, backoff_s=0)
        with self.assertRaises(ProviderError):
            gw.complete(req())
        self.assertEqual(bad.calls, 2)
        self.assertEqual(gw.stats()["tasks"]["t"]["failures"], 1)

    def test_cache(self):
        p = ScriptedProvider("p", [GOOD])
        gw = LLMGateway([p])
        gw.complete(req("same"))
        second = gw.complete(req("same"))
        self.assertTrue(second.cached)
        self.assertEqual(p.calls, 1)
        gw.complete(req("different"))
        self.assertEqual(p.calls, 2)

    def test_complete_json_repairs_once(self):
        p = ScriptedProvider("p", ["I think it is mostly clean", GOOD])
        gw = LLMGateway([p])
        out, _ = gw.complete_json(req(), BinAssessment)
        self.assertEqual(out.contamination_pct, 20)
        self.assertEqual(p.calls, 2)
        self.assertEqual(gw.stats()["tasks"]["t"]["repairs"], 1)

    def test_complete_json_gives_up_after_repair(self):
        p = ScriptedProvider("p", ["nope"])
        gw = LLMGateway([p])
        with self.assertRaises((ValueError, ValidationError)):
            gw.complete_json(req(), BinAssessment)

    def test_stats_tokens_and_latency(self):
        gw = LLMGateway([ScriptedProvider("p", [GOOD])])
        gw.complete(req("a"))
        gw.complete(req("b"))
        s = gw.stats()["tasks"]["t"]
        self.assertEqual((s["calls"], s["input_tokens"], s["output_tokens"], s["avg_latency_ms"]), (2, 20, 6, 5))


if __name__ == "__main__":
    unittest.main()
