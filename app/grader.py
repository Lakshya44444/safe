"""Grades a photo of one bin: how much of what is inside belongs to a different stream.

The vision model only *describes* the bin (contamination %, wrong items it can see).
The grade and the Shabash/Oops message are decided here in plain code, so the rule
is the same for every Bhawan and easy to explain to judges and wardens.
"""

import base64
import hashlib
import json
import mimetypes
import re
from dataclasses import dataclass, field

import requests

from . import config

# Contamination thresholds for the grade (percent of items in the wrong bin).
A_MAX = 10
B_MAX = 35

PROMPT = """You are auditing source segregation in an Indian college hostel under the
Solid Waste Management Rules 2026, which require four streams:
- wet: food scraps, vegetable peels, tea leaves, garden waste
- dry: plastic, paper, cardboard, metal, glass, packets, bottles
- sanitary: diapers, sanitary pads, tampons, tissues soiled with body fluids
- special_care: medicines, batteries, bulbs/tubelights, paint, e-waste, sharps

This photo is of the **{stream}** bin. Look only at what is visible.
Estimate what percentage of the visible contents does NOT belong in a {stream} bin,
and list the wrong items you can see (short English names, max 6).
If the photo is not a waste bin or is unreadable, set "readable" to false.

Reply with JSON only:
{{"readable": true, "contamination_pct": 0-100, "wrong_items": ["..."], "confidence": 0.0-1.0}}"""


@dataclass
class GradeResult:
    grade: str
    contamination: int
    found_items: list[str] = field(default_factory=list)
    tag_hi: str = ""
    confidence: float = 1.0
    provider: str = "mock"


def grade_from_contamination(pct: int) -> str:
    if pct <= A_MAX:
        return "A"
    if pct <= B_MAX:
        return "B"
    return "C"


def make_tag(grade: str, stream: str, items: list[str]) -> str:
    """The digital 'Oops / Shabash' tag, in simple Hinglish."""
    label = config.STREAM_LABELS_HI.get(stream, stream)
    if grade == "A":
        return f"Shabash! {stream} dabba ekdum sahi hai. Aise hi rakho."
    shown = ", ".join(items[:3]) if items else "galat cheezein"
    if grade == "B":
        return f"Thoda dhyan do: {stream} dabbe mein {shown} mila. Isme sirf {label} daalo."
    return f"Oops! {stream} dabba mixed hai: {shown}. Isme sirf {label} daalo."


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"model did not return JSON: {text[:200]}")
    return json.loads(m.group(0))


def _image_b64(path: str) -> tuple[str, str]:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return mime, base64.b64encode(f.read()).decode()


def _ask_gemini(path: str, stream: str) -> dict:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    mime, data = _image_b64(path)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{config.GEMINI_MODEL}:generateContent")
    body = {
        "contents": [{"parts": [
            {"text": PROMPT.format(stream=stream)},
            {"inline_data": {"mime_type": mime, "data": data}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    r = requests.post(url, params={"key": config.GEMINI_API_KEY}, json=body, timeout=60)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json(text)


def _ask_anthropic(path: str, stream: str) -> dict:
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    mime, data = _image_b64(path)
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={
            "model": config.ANTHROPIC_MODEL,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}},
                {"type": "text", "text": PROMPT.format(stream=stream)},
            ]}],
        },
        timeout=60,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"])
    return _parse_json(text)


# Words a worker might say that hint at contamination, for the offline mock grader.
_MOCK_HINTS = {
    "polythene": "plastic bag", "plastic": "plastic", "packet": "chips packet",
    "bottle": "bottle", "khaana": "food scraps", "khana": "food scraps", "food": "food scraps",
    "pad": "sanitary pad", "diaper": "diaper", "dawai": "medicine strip", "battery": "battery",
    "bulb": "bulb", "kaagaz": "paper", "paper": "paper", "mixed": "mixed waste",
}


def _ask_mock(path: str | None, stream: str, note: str | None) -> dict:
    """Offline grader for demos and tests: uses the worker's words, else a stable hash of the photo."""
    text = (note or "").lower()
    items = sorted({v for k, v in _MOCK_HINTS.items() if k in text})
    if any(w in text for w in ("saaf", "sahi", "clean", "theek")) and not items:
        return {"readable": True, "contamination_pct": 5, "wrong_items": [], "confidence": 0.6}
    if items:
        pct = min(80, 20 + 15 * len(items))
        return {"readable": True, "contamination_pct": pct, "wrong_items": items, "confidence": 0.6}
    seed = hashlib.sha256((path or stream).encode()).digest()[0]
    return {"readable": True, "contamination_pct": seed % 60, "wrong_items": [], "confidence": 0.3}


def grade_bin(photo_path: str | None, stream: str, note: str | None = None) -> GradeResult:
    provider = config.GRADER_PROVIDER
    if photo_path and provider == "gemini":
        raw = _ask_gemini(photo_path, stream)
    elif photo_path and provider == "anthropic":
        raw = _ask_anthropic(photo_path, stream)
    else:
        provider = "mock"
        raw = _ask_mock(photo_path, stream, note)

    if raw.get("readable") is False:
        raise ValueError("Photo mein dabba saaf nahi dikh raha. Dobara photo lo.")

    pct = max(0, min(100, int(round(float(raw.get("contamination_pct", 0))))))
    items = [str(i) for i in (raw.get("wrong_items") or [])][:6]
    grade = grade_from_contamination(pct)
    return GradeResult(
        grade=grade,
        contamination=pct,
        found_items=items,
        tag_hi=make_tag(grade, stream, items),
        confidence=float(raw.get("confidence", 1.0) or 1.0),
        provider=provider,
    )
