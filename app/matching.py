"""Turn what people type or say into canonical values.

Workers speak Hindi, Hinglish or English, so the aliases include common Hindi words.
"""

from __future__ import annotations

import re

from . import config
from .db import ISSUE_KINDS

_BHAWAN_WORDS = re.compile(r"\b(bhawan|bhavan|hostel)\b")

STREAM_ALIASES = {
    "wet": "wet", "organic": "wet", "food": "wet", "green": "wet", "geela": "wet", "gila": "wet",
    "dry": "dry", "recyclable": "dry", "blue": "dry", "sookha": "dry", "sukha": "dry",
    "sanitary": "sanitary",
    "special_care": "special_care", "special": "special_care", "hazardous": "special_care",
    "e_waste": "special_care",
    # Devanagari, for the voice agent and Hindi keyboards
    "गीला": "wet", "गीले": "wet", "सूखा": "dry", "सूखे": "dry", "सैनिटरी": "sanitary",
    "स्पेशल": "special_care", "खतरनाक": "special_care",
}

BHAWAN_HI = {
    "आज़ाद": "Azad", "आजाद": "Azad", "कॉटली": "Cautley", "कौटली": "Cautley", "गंगा": "Ganga", "गोविंद": "Govind",
    "जवाहर": "Jawahar", "मालवीय": "Malviya", "राधाकृष्णन": "Radhakrishnan", "राजेंद्र": "Rajendra",
    "राजेन्द्र": "Rajendra", "राजीव": "Rajiv", "रवींद्र": "Ravindra", "रविन्द्र": "Ravindra", "हिमालय": "Himalaya",
    "इंदिरा": "Indira", "कस्तूरबा": "Kasturba", "सरोजिनी": "Sarojini", "विज्ञान": "Vigyan Kunj",
}

ISSUE_ALIASES = [
    ("overflow", "overflow"), ("full", "overflow"), ("bhar", "overflow"),
    ("missed", "missed_pickup"), ("pickup", "missed_pickup"), ("not come", "missed_pickup"),
    ("nahi aayi", "missed_pickup"), ("gaadi", "missed_pickup"),
    ("broken", "broken_bin"), ("damaged", "broken_bin"), ("toota", "broken_bin"),
]


def match_bhawan(name: str | None) -> str | None:
    """'govind', 'Govind Bhawan', 'GOVIND hostel' -> 'Govind'."""
    if not name:
        return None
    n = " ".join(_BHAWAN_WORDS.sub("", name.lower()).replace("भवन", "").split())
    for hi, en in BHAWAN_HI.items():
        if n.startswith(hi):
            return en
    if len(n) < 3:
        return None
    for b in config.BHAWANS:
        if n == b.lower():
            return b
    # A prefix ("raj") must point to exactly one Bhawan; "raj" could be Rajendra or Rajiv.
    hits = [b for b in config.BHAWANS if b.lower().startswith(n) or n.startswith(b.lower())]
    return hits[0] if len(hits) == 1 else None


def match_stream(name: str | None) -> str | None:
    if not name:
        return None
    n = re.sub(r"[\s\-]+", "_", name.lower().strip())
    return STREAM_ALIASES.get(n) or STREAM_ALIASES.get(n.split("_")[0])


def match_issue_kind(text: str | None) -> str:
    t = (text or "").lower().strip()
    if t in ISSUE_KINDS:
        return t
    for word, kind in ISSUE_ALIASES:
        if word in t:
            return kind
    return "other"
