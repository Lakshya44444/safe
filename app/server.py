"""HTTP API for Kachra Report Card.

Run locally:  uvicorn app.server:app --reload
"""

import contextlib
import logging
import re
import uuid
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import config, db, pipeline, scoring, stt, voice

logging.basicConfig(level=logging.INFO)
MAX_UPLOAD = 8 * 1024 * 1024
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


def match_bhawan(name: str | None) -> str | None:
    """Accepts 'govind', 'Govind Bhawan', 'GOVIND' ... returns the canonical name."""
    if not name:
        return None
    n = re.sub(r"\b(bhawan|bhavan|hostel)\b", "", name.lower()).strip()
    if len(n) < 3:
        return None
    for b in config.BHAWANS:
        if b.lower() == n or b.lower().startswith(n) or n.startswith(b.lower()):
            return b
    return None


def match_stream(name: str | None) -> str | None:
    if not name:
        return None
    n = name.lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {"geela": "wet", "gila": "wet", "organic": "wet", "sookha": "dry", "sukha": "dry",
               "recyclable": "dry", "special": "special_care", "hazardous": "special_care",
               "e_waste": "special_care"}
    n = aliases.get(n, n)
    return n if n in config.STREAMS else None


def public_report(r: dict) -> dict:
    r = dict(r)
    if r.get("photo_path"):
        r["photo_url"] = f"/api/photos/{Path(r['photo_path']).name}"
    r.pop("photo_path", None)
    return r


async def health(request: Request):
    return JSONResponse({"ok": True})


async def meta(request: Request):
    return JSONResponse({
        "bhawans": config.BHAWANS,
        "streams": config.STREAMS,
        "stream_labels_hi": config.STREAM_LABELS_HI,
        "grader": config.GRADER_PROVIDER,
        "tts": voice.tts_available(),
        "stt": bool(config.ELEVENLABS_API_KEY),
        "agent_id": config.ELEVENLABS_AGENT_ID or None,
        "workflows": bool(config.RENDER_WORKFLOW_SLUG),
    })


async def create_report(request: Request):
    form = await request.form()
    bhawan = match_bhawan(form.get("bhawan"))
    stream = match_stream(form.get("bin_stream"))
    if not bhawan:
        return err("Bhawan ka naam samajh nahi aaya")
    if not stream:
        return err("bin_stream must be one of: " + ", ".join(config.STREAMS))
    note = (form.get("note") or "").strip()[:1000] or None
    reporter = (form.get("reporter") or "").strip()[:80] or None

    photo_path = None
    photo = form.get("photo")
    if photo is not None and getattr(photo, "filename", ""):
        data = await photo.read()
        if len(data) > MAX_UPLOAD:
            return err("Photo 8 MB se chhoti honi chahiye", 413)
        ext = Path(photo.filename).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        config.ensure_dirs()
        p = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
        p.write_bytes(data)
        photo_path = str(p)

    if not photo_path and not note:
        return err("Photo ya voice note, kam se kam ek chahiye")

    rid = db.create_report(bhawan, stream, reporter, note, photo_path)
    if request.query_params.get("wait") == "1":
        report = pipeline.process_report(rid)
        return JSONResponse(public_report(report), status_code=201)
    pipeline.process_in_background(rid)
    return JSONResponse(public_report(db.get_report(rid)), status_code=202)


async def list_reports(request: Request):
    limit = min(int(request.query_params.get("limit", 50)), 200)
    bhawan = match_bhawan(request.query_params.get("bhawan"))
    return JSONResponse([public_report(r) for r in db.list_reports(limit, bhawan)])


async def get_report(request: Request):
    r = db.get_report(int(request.path_params["id"]))
    return JSONResponse(public_report(r)) if r else err("not found", 404)


async def photo(request: Request):
    name = Path(request.path_params["name"]).name
    p = config.UPLOAD_DIR / name
    return FileResponse(p) if p.exists() else err("not found", 404)


async def audio(request: Request):
    name = Path(request.path_params["name"]).name
    p = config.AUDIO_DIR / name
    return FileResponse(p, media_type="audio/mpeg") if p.exists() else err("not found", 404)


def _days(request: Request) -> int:
    return max(1, min(int(request.query_params.get("days", 7)), 90))


async def leaderboard(request: Request):
    return JSONResponse(scoring.bhawan_scores(_days(request)))


async def summary(request: Request):
    return JSONResponse(scoring.campus_summary(_days(request)))


async def briefing(request: Request):
    bhawan = match_bhawan(request.path_params["bhawan"])
    if not bhawan:
        return err("unknown bhawan", 404)
    rows = scoring.bhawan_scores(1)
    row = next((r for r in rows if r["bhawan"] == bhawan), None)
    text = voice.briefing_text(row, bhawan, len(rows) or 1)
    out = {"bhawan": bhawan, "text": text, "audio_url": None}
    if voice.tts_available():
        try:
            out["audio_url"] = f"/api/audio/{Path(voice.synthesize(text)).name}"
        except Exception as e:
            out["tts_error"] = str(e)[:200]
    return JSONResponse(out)


async def transcribe(request: Request):
    form = await request.form()
    f = form.get("audio")
    if f is None:
        return err("audio file missing")
    data = await f.read()
    if len(data) > MAX_UPLOAD:
        return err("audio too large", 413)
    try:
        text = stt.transcribe(data, f.filename or "note.webm", f.content_type)
    except Exception as e:
        return err(f"transcription failed: {e}", 502)
    return JSONResponse({"text": text})


# ---- ElevenLabs Agent server tools (webhooks the voice agent calls) ----

async def agent_report(request: Request):
    """Tool: file_report(bhawan, bin_stream, note, reporter). Voice-only report, graded from the words."""
    body = await request.json()
    bhawan = match_bhawan(body.get("bhawan"))
    stream = match_stream(body.get("bin_stream"))
    if not bhawan:
        return JSONResponse({"ok": False, "say": "Kaunsa Bhawan? Naam dobara boliye."})
    if not stream:
        return JSONResponse({"ok": False, "say": "Kaunsa dabba tha: geela, sookha, sanitary ya special care?"})
    rid = db.create_report(bhawan, stream, body.get("reporter"), (body.get("note") or "")[:1000], None)
    r = pipeline.process_report(rid)
    if r["status"] != "graded":
        return JSONResponse({"ok": False, "say": "Report save hui, lekin grade nahi ho payi."})
    return JSONResponse({"ok": True, "report_id": rid, "grade": r["grade"],
                         "say": f"Report darj ho gayi. {bhawan} ke {stream} dabbe ko grade {r['grade']} mila. {r['tag_hi']}"})


async def agent_score(request: Request):
    """Tool: get_score(bhawan). Lets the agent answer 'humare Bhawan ka score kya hai?'"""
    body = await request.json()
    bhawan = match_bhawan(body.get("bhawan"))
    rows = scoring.bhawan_scores(7)
    row = next((r for r in rows if r["bhawan"] == bhawan), None)
    if not row:
        return JSONResponse({"say": f"{bhawan or 'Is Bhawan'} ki is hafte koi report nahi hai."})
    return JSONResponse({"say": f"{bhawan} ka score {row['score']} hai, rank {row['rank']} out of {len(rows)}."})


routes = [
    Route("/api/health", health),
    Route("/api/meta", meta),
    Route("/api/reports", create_report, methods=["POST"]),
    Route("/api/reports", list_reports),
    Route("/api/reports/{id:int}", get_report),
    Route("/api/photos/{name}", photo),
    Route("/api/audio/{name}", audio),
    Route("/api/leaderboard", leaderboard),
    Route("/api/summary", summary),
    Route("/api/briefing/{bhawan}", briefing),
    Route("/api/transcribe", transcribe, methods=["POST"]),
    Route("/api/agent/report", agent_report, methods=["POST"]),
    Route("/api/agent/score", agent_score, methods=["POST"]),
]
if STATIC_DIR.exists():
    routes.append(Mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static"))

@contextlib.asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield


app = Starlette(
    routes=routes,
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
    lifespan=lifespan,
)
