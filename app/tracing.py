"""Optional LangSmith tracing.

If the `langsmith` package is installed and LANGSMITH_TRACING=true (plus LANGSMITH_API_KEY),
every decorated function shows up as a run in LangSmith. Otherwise the decorator is a no-op,
so the app never depends on LangSmith being available.

Image bytes are stripped from traced inputs: traces should show the prompt and the
model's answer, not megabytes of base64.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

try:  # pragma: no cover - depends on optional package
    from langsmith import traceable as _ls_traceable
except ImportError:  # pragma: no cover
    _ls_traceable = None


def tracing_enabled() -> bool:
    flag = os.getenv("LANGSMITH_TRACING", os.getenv("LANGCHAIN_TRACING_V2", "")).lower()
    return _ls_traceable is not None and flag in {"1", "true", "yes"}


def _redact(inputs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in inputs.items():
        image = getattr(value, "image", None)
        if image is not None and hasattr(value, "prompt"):
            # LLMRequest: keep everything except the raw image.
            out[key] = {
                "task": value.task,
                "prompt": value.prompt,
                "image": f"<{image.mime}, {len(image.data)} bytes>",
                "metadata": value.metadata,
            }
        elif isinstance(value, (bytes, bytearray)):
            out[key] = f"<{len(value)} bytes>"
        else:
            out[key] = value
    return out


def traceable(name: str, run_type: str = "chain") -> Callable[[F], F]:
    """Decorator: trace to LangSmith when enabled, otherwise return the function unchanged."""

    def decorate(fn: F) -> F:
        if not tracing_enabled():
            return fn
        return _ls_traceable(name=name, run_type=run_type, process_inputs=_redact)(fn)  # type: ignore[misc]

    return decorate
