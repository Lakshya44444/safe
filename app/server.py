"""HTTP API and static front end for Kachra Report Card.

Run locally:  uvicorn app.server:app --reload
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import config, db, pipeline, scoring, voice
from .llm_gateway import get_gateway
from .matching import match_bhawan, match_issue_kind, match_stream

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kachra.api")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# ---------- helpers ----------

def fail(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


def public_report(r: dict) -> dict:
    r = dict(r)
    path = r.pop("photo_path", None)
    if path:
        r["photo_url"] = f"/api/photos/{Path(path).name}"
    return r


def int_param(request: Request, name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(request.query_params.get(name, default)), hi))
    except ValueError:
        raise HTTPException(400, f"{name} must be a number")


async def read_upload(f: UploadFile) -> bytes:
    data = await f.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File must be smaller than 8 MB")
    return data


def _is_image(data: bytes) -> bool:
    return (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"))


# ---------- basic ----------

async def health(request: Request):
    return JSONResponse({"ok": True})


async def meta(request: Request):
    return JSONResponse({
        "bhawans": config.BHAWANS,
        "streams": config.STREAMS,
        "stream_contents": config.STREAM_CONTENTS,
        "grade_cutoffs": {"A": config.GRADE_A_MAX_PCT, "B": config.GRADE_B_MAX_PCT},
        "llm_chain": get_gateway().chain,
        "tts": voice.tts_available(),
        "stt": voice.stt_available(),
        "agent_id": config.ELEVENLABS_AGENT_ID or None,
        "workflows": bool(config.RENDER_WORKFLOW_SLUG),
    })


async def llm_stats(request: Request):
    return JSONResponse(get_gateway().stats())


# ---------- reports ----------

async def create_report(request: Request):
    async with request.form() as form:
        return await _create_report(request, form)


async def _create_report(request: Request, form):
    bhawan = match_bhawan(form.get("bhawan"))
    stream = match_stream(form.get("bin_stream"))
    if not bhawan:
        return fail("Unknown Bhawan. Pick one from the list.")
    if not stream:
        return fail("bin_stream must be one of: " + ", ".join(config.STREAMS))
    note = (form.get("note") or "").strip()[:1000] or None
    reporter = (form.get("reporter") or "").strip()[:80] or None

    photo_path = None
    photo = form.get("photo")
    if isinstance(photo, UploadFile) and photo.filename:
        data = await read_upload(photo)
        if not _is_image(data):
            return fail("The photo must be a JPEG, PNG or WebP image.")
        ext = Path(photo.filename).suffix.lower()
        config.ensure_dirs()
        p = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{ext if ext in IMAGE_EXTS else '.jpg'}"
        p.write_bytes(data)
        photo_path = str(p)

    if not photo_path and not note:
        return fail("Add a photo of the bin or a short note.")

    rid = db.create_report(bhawan, stream, reporter, note, photo_path)
    if request.query_params.get("wait") == "1":
        return JSONResponse(public_report(pipeline.process_report(rid)), status_code=201)
    pipeline.process_in_background(rid)
    return JSONResponse(public_report(db.get_report(rid)), status_code=202)


async def list_reports(request: Request):
    limit = int_param(request, "limit", 50, 1, 200)
    bhawan = match_bhawan(request.query_params.get("bhawan"))
    return JSONResponse([public_report(r) for r in db.list_reports(limit, bhawan)])


async def get_report(request: Request):
    r = db.get_report(request.path_params["id"])
    return JSONResponse(public_report(r)) if r else fail("Report not found", 404)


async def photo(request: Request):
    p = config.UPLOAD_DIR / Path(request.path_params["name"]).name
    return FileResponse(p) if p.is_file() else fail("Not found", 404)


async def audio(request: Request):
    p = config.AUDIO_DIR / Path(request.path_params["name"]).name
    return FileResponse(p, media_type="audio/mpeg") if p.is_file() else fail("Not found", 404)


# ---------- scores ----------

async def leaderboard(request: Request):
    return JSONResponse(scoring.bhawan_scores(int_param(request, "days", 7, 1, 90)))


async def summary(request: Request):
    return JSONResponse(scoring.campus_summary(int_param(request, "days", 7, 1, 90)))


async def briefing(request: Request):
    bhawan = match_bhawan(request.path_params["bhawan"])
    if not bhawan:
        return fail("Unknown Bhawan", 404)
    rows = scoring.bhawan_scores(1)
    row = next((r for r in rows if r["bhawan"] == bhawan), None)
    text = voice.briefing_text(row, bhawan, len(rows) or 1)
    out: dict = {"bhawan": bhawan, "text": text, "audio_url": None}
    if voice.tts_available():
        try:
            out["audio_url"] = f"/api/audio/{Path(voice.synthesize(text)).name}"
        except voice.VoiceError as e:
            log.warning("briefing TTS failed: %s", e)
            out["tts_error"] = str(e)[:200]
    return JSONResponse(out)


async def transcribe(request: Request):
    async with request.form() as form:
        f = form.get("audio")
        if not isinstance(f, UploadFile):
            return fail("Send the recording as 'audio'.")
        data = await read_upload(f)
    try:
        return JSONResponse({"text": voice.transcribe(data, f.filename or "note.webm", f.content_type)})
    except voice.VoiceError as e:
        return fail(str(e), 502)


# ---------- collection issues ----------

class IssueIn(BaseModel):
    bhawan: str
    kind: str = "other"
    note: str | None = Field(default=None, max_length=500)
    reporter: str | None = Field(default=None, max_length=80)


async def _body(request: Request, model: type[BaseModel]):
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        try:
            raw = await request.json()
        except ValueError:
            raise HTTPException(400, "Body is not valid JSON")
    else:
        async with request.form() as form:
            raw = {k: v for k, v in form.items() if isinstance(v, str)}
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(400, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))


async def create_issue(request: Request):
    body: IssueIn = await _body(request, IssueIn)
    bhawan = match_bhawan(body.bhawan)
    if not bhawan:
        return fail("Unknown Bhawan. Pick one from the list.")
    iid = db.create_issue(bhawan, match_issue_kind(body.kind), (body.note or "").strip() or None,
                          (body.reporter or "").strip() or None)
    return JSONResponse({"id": iid, "bhawan": bhawan}, status_code=201)


async def list_issues(request: Request):
    status = request.query_params.get("status", "open")
    return JSONResponse(db.list_issues(None if status == "all" else status))


async def resolve_issue(request: Request):
    r = db.resolve_issue(request.path_params["id"])
    return JSONResponse(r) if r else fail("Issue not found", 404)


# ---------- ElevenLabs agent server tools ----------
# The voice agent calls these webhooks. Each returns a `say` field the agent reads back.

class AgentReportIn(BaseModel):
    bhawan: str = ""
    bin_stream: str = ""
    note: str = Field(default="", max_length=1000)
    reporter: str | None = None


class AgentIssueIn(BaseModel):
    bhawan: str = ""
    kind: str = ""
    note: str = Field(default="", max_length=500)
    reporter: str | None = None


class AgentScoreIn(BaseModel):
    bhawan: str = ""


async def agent_report(request: Request):
    body: AgentReportIn = await _body(request, AgentReportIn)
    bhawan, stream = match_bhawan(body.bhawan), match_stream(body.bin_stream)
    if not bhawan:
        return JSONResponse({"ok": False, "say": "Which Bhawan is this? Please say the name again."})
    if not stream:
        return JSONResponse({"ok": False, "say": "Which bin was it: wet, dry, sanitary or special care?"})
    if not body.note.strip():
        return JSONResponse({"ok": False, "say": "What did you see inside the bin?"})
    rid = db.create_report(bhawan, stream, body.reporter, body.note.strip(), None)
    r = pipeline.process_report(rid)
    if r["status"] != "graded":
        return JSONResponse({"ok": False, "say": r.get("error") or "Saved, but it could not be graded."})
    return JSONResponse({"ok": True, "report_id": rid, "grade": r["grade"],
                         "say": f"Report saved. {bhawan}'s {stream.replace('_', ' ')} bin got grade {r['grade']}. {r['tag']}"})


async def agent_issue(request: Request):
    body: AgentIssueIn = await _body(request, AgentIssueIn)
    bhawan = match_bhawan(body.bhawan)
    if not bhawan:
        return JSONResponse({"ok": False, "say": "Which Bhawan is this? Please say the name again."})
    kind = match_issue_kind(body.kind or body.note)
    iid = db.create_issue(bhawan, kind, body.note.strip() or None, body.reporter)
    label = {"overflow": "overflowing bin", "missed_pickup": "missed pickup",
             "broken_bin": "broken bin"}.get(kind, "complaint")
    return JSONResponse({"ok": True, "issue_id": iid, "say": f"Logged a {label} at {bhawan}. Complaint number {iid}."})


async def agent_score(request: Request):
    body: AgentScoreIn = await _body(request, AgentScoreIn)
    bhawan = match_bhawan(body.bhawan)
    rows = scoring.bhawan_scores(7)
    row = next((r for r in rows if r["bhawan"] == bhawan), None)
    if not row:
        return JSONResponse({"say": f"There are no reports for {bhawan or 'that Bhawan'} this week."})
    return JSONResponse({"say": f"{bhawan} scores {row['score']} out of 100 this week, rank {row['rank']} of {len(rows)}."})


# ---------- app ----------

async def http_error(request: Request, exc: HTTPException):
    return fail(exc.detail, exc.status_code)


routes = [
    Route("/api/health", health),
    Route("/api/meta", meta),
    Route("/api/llm/stats", llm_stats),
    Route("/api/reports", create_report, methods=["POST"]),
    Route("/api/reports", list_reports),
    Route("/api/reports/{id:int}", get_report),
    Route("/api/photos/{name}", photo),
    Route("/api/audio/{name}", audio),
    Route("/api/leaderboard", leaderboard),
    Route("/api/summary", summary),
    Route("/api/briefing/{bhawan}", briefing),
    Route("/api/transcribe", transcribe, methods=["POST"]),
    Route("/api/issues", create_issue, methods=["POST"]),
    Route("/api/issues", list_issues),
    Route("/api/issues/{id:int}/resolve", resolve_issue, methods=["POST"]),
    Route("/api/agent/report", agent_report, methods=["POST"]),
    Route("/api/agent/issue", agent_issue, methods=["POST"]),
    Route("/api/agent/score", agent_score, methods=["POST"]),
]
if STATIC_DIR.exists():
    routes.append(Mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static"))


@contextlib.asynccontextmanager
async def lifespan(app):
    db.init_db()
    log.info("LLM chain: %s", get_gateway().chain)
    yield


app = Starlette(
    routes=routes,
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
    exception_handlers={HTTPException: http_error},
    lifespan=lifespan,
)
