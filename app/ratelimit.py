"""Small in-memory guard for write endpoints: request size and per-client rate.

Every report costs an LLM call, so an open endpoint needs a cap. This is per process,
which is enough for one Render instance; use Redis or Render's edge for more.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class WriteGuard:
    def __init__(self, app: ASGIApp, *, max_body: int, per_minute: int, prefixes: tuple[str, ...] = ("/api/",)):
        self.app = app
        self.max_body = max_body
        self.per_minute = per_minute
        self.prefixes = prefixes
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def client_ip(scope: Scope) -> str:
        headers = dict(scope.get("headers") or [])
        fwd = headers.get(b"x-forwarded-for", b"").decode()
        if fwd:  # Render puts the real client first
            return fwd.split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] == "http" and scope["method"] in ("POST", "PUT", "PATCH")
                and scope["path"].startswith(self.prefixes)):
            headers = dict(scope.get("headers") or [])
            try:
                length = int(headers.get(b"content-length", b"0"))
            except ValueError:
                length = 0
            if length > self.max_body:
                await JSONResponse({"error": "Request is too large (max 8 MB)."}, 413)(scope, receive, send)
                return
            if not self.allow(self.client_ip(scope)):
                await JSONResponse({"error": "Too many requests. Wait a minute and try again."}, 429,
                                   headers={"Retry-After": "60"})(scope, receive, send)
                return
        await self.app(scope, receive, send)
