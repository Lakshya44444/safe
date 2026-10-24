"""Grades one bin.

The LLM only *describes* the bin (contamination %, wrong items) through the gateway.
The grade and the feedback tag are decided here in plain code, so the rule is the same
for every Bhawan and easy to explain.
"""

from __future__ import annotations

import re

from . import config, prompts
from .llm_gateway import ImageInput, LLMRequest, get_gateway
from .models import BinAssessment, Grade, GradeResult
from .tracing import traceable


class UnreadableBinError(ValueError):
    """The photo or note does not show the bin's contents; the worker should try again."""


def grade_from_contamination(pct: int) -> Grade:
    if pct <= config.GRADE_A_MAX_PCT:
        return "A"
    if pct <= config.GRADE_B_MAX_PCT:
        return "B"
    return "C"


def make_tag(grade: Grade, stream: str, items: list[str]) -> str:
    """The digital 'Good job / Oops' tag left on the bin."""
    name = config.STREAM_NAMES[stream]
    belongs = config.STREAM_CONTENTS[stream]
    if grade == "A":
        return f"Good job! The {name} bin is clean. Keep it up."
    found = ", ".join(items[:3]) if items else "items from other streams"
    if grade == "B":
        return f"Needs attention: found {found} in the {name} bin. Only {belongs} go here."
    return f"Oops! The {name} bin is mixed: {found}. Only {belongs} go here."


def _sanitize_note(note: str) -> str:
    # Keep the note inside its <worker_note> fence and bounded in size.
    return re.sub(r"[<>]", " ", note).strip()[:1000]


@traceable(name="assess_photo")
def assess_photo(photo_path: str, stream: str) -> tuple[BinAssessment, dict]:
    req = LLMRequest(task="grade_bin_photo", system=prompts.SYSTEM, prompt=prompts.photo_prompt(stream),
                     image=ImageInput.from_path(photo_path),
                     metadata={"stream": stream, "prompt_version": prompts.PROMPT_VERSION})
    assessment, resp = get_gateway().complete_json(req, BinAssessment)
    return assessment, {"provider": resp.provider, "model": resp.model, "latency_ms": resp.latency_ms}


@traceable(name="assess_note")
def assess_note(note: str, stream: str, case_id: str | None = None) -> tuple[BinAssessment, dict]:
    clean = _sanitize_note(note)
    meta = {"stream": stream, "note": clean, "prompt_version": prompts.PROMPT_VERSION}
    if case_id:
        meta["case_id"] = case_id
    req = LLMRequest(task="grade_bin_note", system=prompts.SYSTEM,
                     prompt=prompts.note_prompt(stream, clean), metadata=meta)
    assessment, resp = get_gateway().complete_json(req, BinAssessment)
    return assessment, {"provider": resp.provider, "model": resp.model, "latency_ms": resp.latency_ms}


@traceable(name="grade_bin")
def grade_bin(photo_path: str | None, stream: str, note: str | None = None) -> GradeResult:
    """Grade from the photo when there is one, otherwise from the worker's note."""
    if stream not in config.STREAMS:
        raise ValueError(f"unknown stream {stream!r}")
    if photo_path:
        assessment, info = assess_photo(photo_path, stream)
        source = "photo"
    elif note and note.strip():
        assessment, info = assess_note(note, stream)
        source = "note"
    else:
        raise ValueError("a photo or a note is required")

    if not assessment.readable:
        raise UnreadableBinError(
            "Could not see the bin's contents. Take the photo again from above, in good light."
            if source == "photo" else
            "The note doesn't say what is in the bin. Say what you see, e.g. 'plastic bag in the wet bin'."
        )

    grade = grade_from_contamination(assessment.contamination_pct)
    return GradeResult(
        grade=grade,
        contamination=assessment.contamination_pct,
        found_items=assessment.wrong_items,
        tag=make_tag(grade, stream, assessment.wrong_items),
        confidence=assessment.confidence,
        source=source,
        **info,
    )
