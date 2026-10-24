"""ElevenLabs speech-to-text (Scribe) for the worker's voice note."""

import os

import requests

from . import config

STT_MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")


def transcribe(audio_bytes: bytes, filename: str, content_type: str) -> str:
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set")
    r = requests.post(
        "https://api.elevenlabs.io/v1/speech-to-text",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        data={"model_id": STT_MODEL},
        files={"file": (filename, audio_bytes, content_type or "audio/webm")},
        timeout=90,
    )
    r.raise_for_status()
    return r.json().get("text", "").strip()
