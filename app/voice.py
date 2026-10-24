"""ElevenLabs: speech-to-text for workers' voice notes, text-to-speech for the warden's daily briefing."""

from __future__ import annotations

import hashlib

import requests

from . import config
from .tracing import traceable

ELEVENLABS = "https://api.elevenlabs.io/v1"


class VoiceError(RuntimeError):
    pass


def tts_available() -> bool:
    return bool(config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID)


def stt_available() -> bool:
    return bool(config.ELEVENLABS_API_KEY)


def briefing_text(row: dict | None, bhawan: str, total_bhawans: int) -> str:
    """Script for the warden's 20-30 second voice note."""
    if not row:
        return (f"Good evening. No bins were checked at {bhawan} Bhawan today. "
                "Please ask the cleaning team to photograph the bins during pickup.")
    g = row["grades"]
    parts = [
        f"Good evening. Here is today's waste report card for {bhawan} Bhawan.",
        f"The segregation score is {row['score']} out of 100, rank {row['rank']} of {total_bhawans} on campus.",
        f"{row['reports']} bins were checked: {g['A']} clean, {g['B']} slightly mixed and {g['C']} mixed.",
    ]
    if row["top_wrong_items"]:
        parts.append("The most common wrong items were " + ", ".join(row["top_wrong_items"]) + ".")
    trend = row.get("trend")
    if trend:
        parts.append(f"That is {abs(trend)} points {'better' if trend > 0 else 'worse'} than earlier this week.")
    parts.append("Great work, keep it going." if row["score"] >= 80 else
                 "Please remind residents to keep food waste and dry waste in separate bins.")
    return " ".join(parts)


@traceable(name="elevenlabs.tts", run_type="tool")
def synthesize(text: str) -> str:
    """Returns the path of an mp3 made by ElevenLabs. Cached by text, so repeats cost nothing."""
    if not tts_available():
        raise VoiceError("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set")
    config.ensure_dirs()
    key = hashlib.sha1(f"{config.ELEVENLABS_VOICE_ID}|{config.ELEVENLABS_MODEL}|{text}".encode()).hexdigest()[:16]
    out = config.AUDIO_DIR / f"{key}.mp3"
    if out.exists():
        return str(out)
    try:
        r = requests.post(
            f"{ELEVENLABS}/text-to-speech/{config.ELEVENLABS_VOICE_ID}",
            headers={"xi-api-key": config.ELEVENLABS_API_KEY, "accept": "audio/mpeg"},
            json={"text": text, "model_id": config.ELEVENLABS_MODEL},
            timeout=90,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        raise VoiceError(f"text-to-speech failed: {e}") from e
    tmp = out.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.replace(out)  # atomic: a half-written file is never served
    return str(out)


@traceable(name="elevenlabs.stt", run_type="tool")
def transcribe(audio: bytes, filename: str, content_type: str | None) -> str:
    if not stt_available():
        raise VoiceError("ELEVENLABS_API_KEY not set")
    try:
        r = requests.post(
            f"{ELEVENLABS}/speech-to-text",
            headers={"xi-api-key": config.ELEVENLABS_API_KEY},
            data={"model_id": config.ELEVENLABS_STT_MODEL},
            files={"file": (filename, audio, content_type or "audio/webm")},
            timeout=90,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        raise VoiceError(f"speech-to-text failed: {e}") from e
    return r.json().get("text", "").strip()
