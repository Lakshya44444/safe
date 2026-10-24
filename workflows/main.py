"""Render Workflows service for Kachra Report Card.

Tasks:
  grade_bin_task  - grade one bin photo or note through the LLM gateway (retried on API errors)
  briefing_for    - build one Bhawan's warden voice note (calls the web API)
  nightly_report  - fan out briefing_for over every Bhawan in parallel

Deploy: create a Workflow service on Render pointing at this repo,
  build:  pip install -r requirements-workflows.txt
  start:  python workflows/main.py
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
import tempfile

import requests
from render import Retry, TaskContext, Workflows

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import config, grader  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kachra.workflows")

app = Workflows(
    default_retry=Retry(max_retries=3, wait_duration_ms=2000, backoff_scaling=2.0),
    default_timeout=180,
)

_EXT = {"image/png": ".png", "image/webp": ".webp"}


@app.task
def grade_bin_task(ctx: TaskContext, photo_b64: str | None, mime: str | None,
                   stream: str, note: str | None) -> dict:
    path = None
    try:
        if photo_b64:
            fd, path = tempfile.mkstemp(suffix=_EXT.get(mime or "", ".jpg"))
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64decode(photo_b64))
        result = grader.grade_bin(path, stream, note)
        log.info("graded %s bin: %s (%s%%) via %s", stream, result.grade, result.contamination, result.provider)
        return result.to_dict()
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@app.task
def briefing_for(ctx: TaskContext, api_base: str, bhawan: str) -> dict:
    r = requests.get(f"{api_base.rstrip('/')}/api/briefing/{bhawan}", timeout=120)
    r.raise_for_status()
    data = r.json()
    return {"bhawan": bhawan, "audio_url": data.get("audio_url")}


@app.task
async def nightly_report(ctx: TaskContext, api_base: str) -> dict:
    """Runs every night, started by the Render cron job in scripts/nightly.py."""
    board = requests.get(f"{api_base.rstrip('/')}/api/leaderboard?days=1", timeout=60).json()
    bhawans = [row["bhawan"] for row in board] or config.BHAWANS
    results = await asyncio.gather(*[ctx.run(briefing_for, api_base, b) for b in bhawans])
    with_audio = sum(1 for r in results if r.get("audio_url"))
    log.info("nightly briefings: %d Bhawans, %d with audio", len(results), with_audio)
    return {"bhawans": len(results), "with_audio": with_audio, "top": board[0]["bhawan"] if board else None}


if __name__ == "__main__":
    app.start()
