"""What happens after a report comes in: grade it, then store the grade.

Two ways to run the grading step:
  * inline (default): in a background thread of the web service.
  * Render Workflows: if RENDER_WORKFLOW_SLUG and RENDER_API_KEY are set, the photo is
    sent to the durable `grade_bin_task` (workflows/main.py), which retries on model
    errors; the web service stores the result it returns.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from concurrent.futures import ThreadPoolExecutor

from . import config, db, grader
from .models import GradeResult

log = logging.getLogger("kachra.pipeline")
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="grade")


def _grade_on_render(report: dict) -> GradeResult:
    from render import Render  # imported lazily: only needed when Workflows is configured

    photo_b64 = mime = None
    if report["photo_path"]:
        mime = mimetypes.guess_type(report["photo_path"])[0] or "image/jpeg"
        with open(report["photo_path"], "rb") as f:
            photo_b64 = base64.b64encode(f.read()).decode()
    run = Render().workflows.run_task(
        f"{config.RENDER_WORKFLOW_SLUG}/grade_bin_task",
        {"photo_b64": photo_b64, "mime": mime, "stream": report["bin_stream"], "note": report["note"]},
    )
    result = run.results[0] if isinstance(run.results, list) else run.results
    return GradeResult(**result)


def _use_workflows() -> bool:
    if not (config.RENDER_WORKFLOW_SLUG and config.RENDER_API_KEY):
        return False
    try:
        import render  # noqa: F401
    except ImportError:
        log.warning("RENDER_WORKFLOW_SLUG is set but the render SDK is not installed; grading inline")
        return False
    return True


def process_report(report_id: int) -> dict | None:
    report = db.get_report(report_id)
    if not report:
        return None
    try:
        if _use_workflows():
            result = _grade_on_render(report)
        else:
            result = grader.grade_bin(report["photo_path"], report["bin_stream"], report["note"])
        db.save_grade(report_id, result)
    except grader.UnreadableBinError as e:
        db.mark_failed(report_id, str(e))
    except Exception as e:  # keep the report and show the error in the UI
        log.exception("grading failed for report %s", report_id)
        db.mark_failed(report_id, f"Grading failed: {e}")
    return db.get_report(report_id)


def process_in_background(report_id: int) -> None:
    _pool.submit(process_report, report_id)

