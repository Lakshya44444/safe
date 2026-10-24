"""LLM providers behind the gateway: Gemini, Anthropic, an offline mock and a replay provider."""

from __future__ import annotations

import hashlib
import json
import re
import logging
import time
from pathlib import Path

import requests

from .types import LLMRequest, LLMResponse, ProviderError

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


def _post(provider: str, url: str, *, headers: dict, payload: dict, timeout: float) -> dict:
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.Timeout as e:
        raise ProviderError("timeout", provider=provider, retryable=True) from e
    except requests.RequestException as e:
        raise ProviderError(f"network error: {e}", provider=provider, retryable=True) from e
    if r.status_code >= 400:
        body = r.text[:300].replace("\n", " ")
        raise ProviderError(f"HTTP {r.status_code}: {body}", provider=provider,
                            retryable=r.status_code in RETRYABLE_STATUS, status=r.status_code)
    try:
        return r.json()
    except ValueError as e:
        raise ProviderError("response was not JSON", provider=provider, retryable=True) from e


log = logging.getLogger("kachra.llm")


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float = 60):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def complete(self, request: LLMRequest) -> LLMResponse:
        parts: list[dict] = [{"text": request.prompt}]
        if request.image:
            parts.append({"inline_data": {"mime_type": request.image.mime, "data": request.image.b64}})
        payload: dict = {
            "contents": [{"role": "user", "parts": parts}],
            # Gemini 2.5 "thinks" by default and the thinking tokens count against maxOutputTokens,
            # which cut the JSON off mid-object. Grading needs no long reasoning: turn thinking off
            # on Flash models and leave head-room for the answer.
            "generationConfig": {"temperature": request.temperature, "maxOutputTokens": max(request.max_tokens, 2048)},
        }
        if "flash" in self.model:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        if request.json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if request.system:
            payload["systemInstruction"] = {"parts": [{"text": request.system}]}

        t0 = time.perf_counter()
        data = _post(self.name,
                     f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                     headers={"x-goog-api-key": self.api_key}, payload=payload, timeout=self.timeout)
        try:
            cand = data["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"])
            if cand.get("finishReason") == "MAX_TOKENS":
                log.warning("gemini reply hit the token limit; JSON may be cut off")
        except (KeyError, IndexError) as e:
            cands = data.get("candidates") or [{}]
            reason = data.get("promptFeedback", {}).get("blockReason") or cands[0].get("finishReason")
            raise ProviderError(f"no text in response ({reason})", provider=self.name) from e
        usage = data.get("usageMetadata", {})
        return LLMResponse(text=text, provider=self.name, model=self.model,
                           latency_ms=int((time.perf_counter() - t0) * 1000),
                           input_tokens=usage.get("promptTokenCount"),
                           output_tokens=usage.get("candidatesTokenCount"))


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float = 60):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def complete(self, request: LLMRequest) -> LLMResponse:
        content: list[dict] = []
        if request.image:
            content.append({"type": "image", "source": {"type": "base64", "media_type": request.image.mime,
                                                        "data": request.image.b64}})
        prompt = request.prompt
        if request.json_mode:
            prompt += "\n\nRespond with a single JSON object and nothing else."
        content.append({"type": "text", "text": prompt})
        payload: dict = {"model": self.model, "max_tokens": request.max_tokens,
                         "temperature": request.temperature,
                         "messages": [{"role": "user", "content": content}]}
        if request.system:
            payload["system"] = request.system

        t0 = time.perf_counter()
        data = _post(self.name, "https://api.anthropic.com/v1/messages",
                     headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                     payload=payload, timeout=self.timeout)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        if not text:
            raise ProviderError(f"no text in response (stop_reason={data.get('stop_reason')})", provider=self.name)
        usage = data.get("usage", {})
        return LLMResponse(text=text, provider=self.name, model=self.model,
                           latency_ms=int((time.perf_counter() - t0) * 1000),
                           input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"))


class MockProvider:
    """Offline, deterministic stand-in for demos and tests.

    Text requests: reads the worker's note (metadata["note"]) for words that signal
    wrong items. Image requests: a stable pseudo-score from the image hash.
    It never sees or follows instructions inside the note.
    """

    name = "mock"
    model = "mock-heuristic-v1"

    HINTS = {
        # English
        "plastic bag": "plastic bag", "polythene": "plastic bag", "plastic": "plastic", "wrapper": "wrapper",
        "packet": "chips packet", "bottle": "bottle", "tin can": "metal can", "food": "food scraps",
        "peel": "vegetable peels", "paper": "paper", "cardboard": "cardboard", "pad": "sanitary pad",
        "diaper": "diaper", "medicine": "medicine strip", "battery": "battery", "bulb": "bulb",
        "glass": "glass",
        # Hindi / Hinglish words workers commonly use
        "khaana": "food scraps", "khana": "food scraps", "kaagaz": "paper", "dawai": "medicine strip",
    }
    CLEAN_WORDS = ("clean", "fine", "ok", "correct", "saaf", "sahi", "theek")

    def complete(self, request: LLMRequest) -> LLMResponse:
        if request.image is not None:
            seed = int(request.image.sha256[:8], 16)
            out = {"readable": True, "contamination_pct": seed % 60, "wrong_items": [], "confidence": 0.3}
        else:
            note = str(request.metadata.get("note", "")).lower()
            items = sorted({v for k, v in self.HINTS.items() if re.search(rf"\b{re.escape(k)}", note)})
            # "plastic bag" already covers "plastic"
            if "plastic bag" in items and "plastic" in items:
                items.remove("plastic")
            if items:
                out = {"readable": True, "contamination_pct": min(80, 20 + 15 * len(items)),
                       "wrong_items": items, "confidence": 0.6}
            elif any(re.search(rf"\b{w}\b", note) for w in self.CLEAN_WORDS):
                out = {"readable": True, "contamination_pct": 5, "wrong_items": [], "confidence": 0.6}
            else:
                out = {"readable": False, "contamination_pct": 0, "wrong_items": [], "confidence": 0.2}
        return LLMResponse(text=json.dumps(out), provider=self.name, model=self.model)


class ReplayProvider:
    """Plays back recorded model outputs by case id. Makes LLM evals deterministic and free in CI.

    Recording file: {"<case_id>": "<raw model text>", ...}
    """

    name = "replay"

    def __init__(self, recordings: dict[str, str] | str | Path, model: str = "replay"):
        if not isinstance(recordings, dict):
            recordings = json.loads(Path(recordings).read_text())
        self.recordings = recordings
        self.model = model

    def complete(self, request: LLMRequest) -> LLMResponse:
        case_id = request.metadata.get("case_id")
        if case_id not in self.recordings:
            raise ProviderError(f"no recording for case {case_id!r}", provider=self.name)
        return LLMResponse(text=self.recordings[case_id], provider=self.name, model=self.model)


def prompt_fingerprint(request: LLMRequest) -> str:
    """Short hash of the prompt, stored with eval results to know which prompt version was tested."""
    return hashlib.sha256(request.prompt.encode()).hexdigest()[:10]
