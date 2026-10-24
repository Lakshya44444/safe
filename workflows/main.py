"""Render Workflows service for Kachra Report Card.

Tasks:
  grade_bin_task   - grade one bin photo with the vision model (retries on API errors)
  briefing_for     - build one Bhawan's warden voice note (calls the web API)
  nightly_report   - fan out briefing_for over every Bhawan in parallel

Deploy: create a Workflow service on Render pointing at this repo,
  build:  pip install -r requirements-workflows.txt
  start:  python workflows/main.py
"""

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
        g = grader.grade_bin(path, stream, note)
        log.info("graded %s bin: %s (%s%%) via %s", stream, g.grade, g.contamination, g.provider)
        return {"grade": g.grade, "contamination": g.contamination, "found_items": g.found_items,
                "tag_hi": g.tag_hi, "provider": g.provider}
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@app.task
def briefing_for(ctx: TaskContext, api_base: str, bhawan: str) -> dict:
    r = requests.get(f"{api_base.rstrip('/')}/api/briefing/{bhawan}", timeout=120)
    r.raise_for_status()
    data = r.json()
    return {"bhawan": bhawan, "audio_url": data.get("audio_url"), "text": data.get("text", "")[:120]}


@app.task
async def nightly_report(ctx: TaskContext, api_base: str) -> dict:
    """Runs every night (triggered by the Render cron job in scripts/nightly.py)."""
    lb = requests.get(f"{api_base.rstrip('/')}/api/leaderboard?days=1", timeout=60).json()
    bhawans = [row["bhawan"] for row in lb] or config.BHAWANS
    results = await asyncio.gather(*[ctx.run(briefing_for, api_base, b) for b in bhawans])
    done = [r for r in results if r.get("audio_url")]
    log.info("nightly briefings: %d bhawans, %d with audio", len(results), len(done))
    return {"bhawans": len(results), "with_audio": len(done),
            "top": lb[0]["bhawan"] if lb else None}


if __name__ == "__main__":
    app.start()
