"""What happens after a report comes in: grade it, then store the grade.

Two ways to run the grading step:
  * inline (default): in a background thread of the web service.
  * Render Workflows: if RENDER_WORKFLOW_SLUG is set, the photo is sent to the
    `grade_bin_task` durable task (see workflows/main.py), which retries on model
    errors; the web service stores the result it returns.
"""

import base64
import logging
import mimetypes
import threading

from . import config, db, grader

log = logging.getLogger("kachra.pipeline")


def _grade_inline(report: dict) -> dict:
    g = grader.grade_bin(report["photo_path"], report["bin_stream"], report["note"])
    return {"grade": g.grade, "contamination": g.contamination,
            "found_items": g.found_items, "tag_hi": g.tag_hi, "provider": g.provider}


def _grade_on_render(report: dict) -> dict:
    from render import Render  # only needed when Workflows is configured

    photo_b64, mime = None, None
    if report["photo_path"]:
        mime = mimetypes.guess_type(report["photo_path"])[0] or "image/jpeg"
        with open(report["photo_path"], "rb") as f:
            photo_b64 = base64.b64encode(f.read()).decode()
    run = Render().workflows.run_task(
        f"{config.RENDER_WORKFLOW_SLUG}/grade_bin_task",
        {"photo_b64": photo_b64, "mime": mime, "stream": report["bin_stream"], "note": report["note"]},
    )
    result = run.results
    if isinstance(result, list):
        result = result[0]
    return result


def process_report(report_id: int) -> dict | None:
    report = db.get_report(report_id)
    if not report:
        return None
    try:
        if config.RENDER_WORKFLOW_SLUG and config.RENDER_API_KEY:
            try:
                res = _grade_on_render(report)
            except ImportError:
                res = _grade_inline(report)
        else:
            res = _grade_inline(report)
        db.save_grade(report_id, res["grade"], int(res["contamination"]),
                      list(res.get("found_items") or []), res["tag_hi"])
    except Exception as e:  # keep the report, show the error in the UI
        log.exception("grading failed for report %s", report_id)
        db.mark_failed(report_id, str(e))
    return db.get_report(report_id)


def process_in_background(report_id: int) -> None:
    threading.Thread(target=process_report, args=(report_id,), daemon=True).start()
