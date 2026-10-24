"""All settings come from environment variables, so the same code runs locally and on Render."""

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "kachra.db"
UPLOAD_DIR = DATA_DIR / "uploads"
AUDIO_DIR = DATA_DIR / "audio"

GRADER_PROVIDER = os.getenv("GRADER_PROVIDER", "mock").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "")

RENDER_API_KEY = os.getenv("RENDER_API_KEY", "")
RENDER_WORKFLOW_SLUG = os.getenv("RENDER_WORKFLOW_SLUG", "")

# IIT Roorkee hostels ("Bhawans").
BHAWANS = [
    "Azad", "Cautley", "Ganga", "Govind", "Jawahar", "Malviya",
    "Radhakrishnan", "Rajendra", "Rajiv", "Ravindra",
    "Himalaya", "Indira", "Kasturba", "Sarojini", "Vigyan Kunj",
]

# Four streams mandated at source by India's Solid Waste Management Rules, 2026.
STREAMS = ["wet", "dry", "sanitary", "special_care"]

STREAM_LABELS_HI = {
    "wet": "geela kachra (khaana, sabzi ke chhilke)",
    "dry": "sookha kachra (plastic, kaagaz, metal)",
    "sanitary": "sanitary kachra (diaper, pad)",
    "special_care": "special care kachra (dawai, bulb, battery, paint)",
}

# Grade -> points used for the Bhawan score.
GRADE_POINTS = {"A": 100, "B": 60, "C": 20}


def ensure_dirs() -> None:
    for d in (DATA_DIR, UPLOAD_DIR, AUDIO_DIR):
        d.mkdir(parents=True, exist_ok=True)
