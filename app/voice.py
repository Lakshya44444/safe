"""ElevenLabs: turns the daily Bhawan report into a short Hinglish voice note for the warden."""

import hashlib

import requests

from . import config


def briefing_text(row: dict | None, bhawan: str, total_bhawans: int) -> str:
    """Script for the warden's 20-30 second voice note."""
    if not row:
        return (f"Namaste. {bhawan} Bhawan ki aaj koi report nahi aayi. "
                f"Kripya safai team se dabbon ki photo bhejne ko kahiye.")
    parts = [
        f"Namaste. Ye {bhawan} Bhawan ka aaj ka kachra report card hai.",
        f"Segregation score {row['score']} pratishat hai, aur campus mein rank {row['rank']} "
        f"out of {total_bhawans} hai.",
        f"Kul {row['reports']} dabbe check hue: {row['grades']['A']} ekdum saaf, "
        f"{row['grades']['B']} thode mixed, aur {row['grades']['C']} poore mixed.",
    ]
    if row["top_wrong_items"]:
        parts.append("Sabse zyada galat cheezein mili: " + ", ".join(row["top_wrong_items"]) + ".")
    if row.get("trend") is not None:
        if row["trend"] > 0:
            parts.append(f"Kal se {row['trend']} point behtar. Shabash!")
        elif row["trend"] < 0:
            parts.append(f"Kal se {abs(row['trend'])} point neeche. Thoda dhyan dijiye.")
    if row["score"] >= 80:
        parts.append("Bahut badhiya. Aise hi chalte rahiye.")
    else:
        parts.append("Kripya students ko geela aur sookha kachra alag rakhne ki yaad dilaiye.")
    return " ".join(parts)


def tts_available() -> bool:
    return bool(config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID)


def synthesize(text: str) -> str:
    """Returns the path of an mp3 made by ElevenLabs. Cached by text, so repeats are free."""
    if not tts_available():
        raise RuntimeError("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set")
    config.ensure_dirs()
    key = hashlib.sha1(f"{config.ELEVENLABS_VOICE_ID}|{config.ELEVENLABS_MODEL}|{text}".encode()).hexdigest()[:16]
    out = config.AUDIO_DIR / f"{key}.mp3"
    if out.exists():
        return str(out)
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY, "accept": "audio/mpeg"},
        json={"text": text, "model_id": config.ELEVENLABS_MODEL},
        timeout=90,
    )
    r.raise_for_status()
    out.write_bytes(r.content)
    return str(out)
