from __future__ import annotations

import base64
import hashlib
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ImageInput:
    data: bytes
    mime: str = "image/jpeg"

    @classmethod
    def from_path(cls, path: str | Path) -> ImageInput:
        p = Path(path)
        mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
        return cls(data=p.read_bytes(), mime=mime)

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True)
class LLMRequest:
    task: str                       # short name, used for tracing and stats, e.g. "grade_bin_photo"
    prompt: str
    image: ImageInput | None = None
    system: str | None = None
    temperature: float = 0.0
    max_tokens: int = 500
    json_mode: bool = True
    # Free-form context. Never sent to the model; used by mock/replay providers and traces.
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def cache_key(self) -> str:
        h = hashlib.sha256()
        for part in (self.task, self.system or "", self.prompt, str(self.temperature), str(self.json_mode)):
            h.update(part.encode())
            h.update(b"\x00")
        if self.image:
            h.update(self.image.sha256.encode())
        return h.hexdigest()


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached: bool = False
    attempts: int = 1


class ProviderError(Exception):
    """Raised by a provider. `retryable` errors (timeouts, 429, 5xx) are retried, then fall back."""

    def __init__(self, message: str, *, provider: str, retryable: bool = False, status: int | None = None):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.retryable = retryable
        self.status = status


class Provider(Protocol):
    name: str
    model: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...
