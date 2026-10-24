"""Settings, all read from environment variables so the same code runs locally and on Render."""

from __future__ import annotations

import os
from pathlib import Path


def _list(name: str, default: str = "") -> list[str]:
    return [x.strip().lower() for x in os.getenv(name, default).split(",") if x.strip()]


DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "kachra.db"
UPLOAD_DIR = DATA_DIR / "uploads"
AUDIO_DIR = DATA_DIR / "audio"

# ---- LLM gateway ----
GRADER_PROVIDER = os.getenv("GRADER_PROVIDER", "mock").lower()   # gemini | anthropic | mock | replay
LLM_FALLBACKS = _list("LLM_FALLBACKS")                            # e.g. "anthropic" or "anthropic,mock"
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_REPLAY_FILE = os.getenv("LLM_REPLAY_FILE", "evals/recordings/grader.json")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# ---- ElevenLabs ----
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_STT_MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "")

# ---- Render Workflows ----
RENDER_API_KEY = os.getenv("RENDER_API_KEY", "")
RENDER_WORKFLOW_SLUG = os.getenv("RENDER_WORKFLOW_SLUG", "")

# ---- Domain ----
BHAWANS = [
    "Azad", "Cautley", "Ganga", "Govind", "Jawahar", "Malviya",
    "Radhakrishnan", "Rajendra", "Rajiv", "Ravindra",
    "Himalaya", "Indira", "Kasturba", "Sarojini", "Vigyan Kunj",
]

# The four streams required at source by India's Solid Waste Management Rules, 2026.
STREAMS = ["wet", "dry", "sanitary", "special_care"]
STREAM_NAMES = {"wet": "wet", "dry": "dry", "sanitary": "sanitary", "special_care": "special care"}
STREAM_CONTENTS = {
    "wet": "food scraps, peels and tea leaves",
    "dry": "plastic, paper, metal and glass",
    "sanitary": "diapers and sanitary pads",
    "special_care": "medicines, bulbs, batteries and paint",
}

# Grade cut-offs: share of visible items that belong in a different stream.
GRADE_A_MAX_PCT = 10
GRADE_B_MAX_PCT = 35
GRADE_POINTS = {"A": 100, "B": 60, "C": 20}

# Assumed weight of one full wet bin; only used for the dashboard's compost estimate.
KG_PER_WET_BIN = float(os.getenv("KG_PER_WET_BIN", "12"))

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
# Each report costs an LLM call: cap writes per client IP per minute.
WRITES_PER_MINUTE = int(os.getenv("WRITES_PER_MINUTE", "30"))
# Days, "today" and trends are counted in campus time, not UTC.
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")


def ensure_dirs() -> None:
    for d in (DATA_DIR, UPLOAD_DIR, AUDIO_DIR):
        d.mkdir(parents=True, exist_ok=True)
