"""The gateway: retries, provider fallback, JSON validation with repair, caching and stats."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import OrderedDict, defaultdict
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .. import config
from ..tracing import traceable
from .providers import AnthropicProvider, GeminiProvider, MockProvider, ReplayProvider
from .types import LLMRequest, LLMResponse, Provider, ProviderError

log = logging.getLogger("kachra.llm")
T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of model text (handles ```json fences and chatter around it)."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for chunk in candidates:
        start = chunk.find("{")
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(chunk)):
                c = chunk[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(chunk[start:i + 1])
                        except json.JSONDecodeError:
                            break
                        if isinstance(obj, dict):
                            return obj
                        break
            start = chunk.find("{", start + 1)
    raise ValueError(f"no JSON object in model output: {text[:160]!r}")


class LLMGateway:
    def __init__(self, providers: list[Provider], *, max_retries: int = 2, backoff_s: float = 0.6,
                 cache_size: int = 256):
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self._cache: OrderedDict[str, LLMResponse] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self._stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    # ---------- public ----------

    @property
    def chain(self) -> list[str]:
        return [f"{p.name}:{p.model}" for p in self.providers]

    @traceable(name="llm_gateway.complete", run_type="llm")
    def complete(self, request: LLMRequest) -> LLMResponse:
        key = request.cache_key()
        with self._lock:
            hit = self._cache.get(key)
            if hit:
                self._cache.move_to_end(key)
                self._stats[request.task]["cache_hits"] += 1
                return LLMResponse(**{**hit.__dict__, "cached": True})

        errors: list[str] = []
        for provider in self.providers:
            try:
                resp = self._call_with_retries(provider, request)
            except ProviderError as e:
                errors.append(str(e))
                log.warning("provider failed, trying next: %s", e)
                continue
            self._record(request.task, resp)
            with self._lock:
                self._cache[key] = resp
                if len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
            return resp

        with self._lock:
            self._stats[request.task]["failures"] += 1
        raise ProviderError("all providers failed: " + " | ".join(errors), provider="gateway")

    @traceable(name="llm_gateway.complete_json", run_type="chain")
    def complete_json(self, request: LLMRequest, schema: type[T]) -> tuple[T, LLMResponse]:
        """Call the model and return a validated `schema` object.

        If the output is not valid JSON for the schema, ask once more with the error attached.
        """
        resp = self.complete(request)
        try:
            return schema.model_validate(extract_json(resp.text)), resp
        except (ValueError, ValidationError) as first_error:
            with self._lock:
                self._stats[request.task]["repairs"] += 1
            repair = LLMRequest(
                task=request.task + ".repair",
                prompt=(request.prompt + "\n\nYour previous reply could not be used: "
                        f"{str(first_error)[:300]}\nReply again with only a valid JSON object."),
                image=request.image, system=request.system, temperature=0.0,
                max_tokens=request.max_tokens, json_mode=True, metadata=request.metadata,
            )
            resp = self.complete(repair)
            return schema.model_validate(extract_json(resp.text)), resp

    def stats(self) -> dict:
        with self._lock:
            out = {}
            for task, s in self._stats.items():
                calls = int(s["calls"])
                out[task] = {
                    "calls": calls,
                    "cache_hits": int(s["cache_hits"]),
                    "failures": int(s["failures"]),
                    "repairs": int(s["repairs"]),
                    "retries": int(s["retries"]),
                    "avg_latency_ms": round(s["latency_ms"] / calls) if calls else None,
                    "input_tokens": int(s["input_tokens"]),
                    "output_tokens": int(s["output_tokens"]),
                }
            return {"chain": self.chain, "tasks": out}

    # ---------- internals ----------

    def _call_with_retries(self, provider: Provider, request: LLMRequest) -> LLMResponse:
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = provider.complete(request)
                resp.attempts = attempt
                return resp
            except ProviderError as e:
                if not e.retryable or attempt > self.max_retries:
                    raise
                with self._lock:
                    self._stats[request.task]["retries"] += 1
                time.sleep(self.backoff_s * (2 ** (attempt - 1)))

    def _record(self, task: str, resp: LLMResponse) -> None:
        with self._lock:
            s = self._stats[task]
            s["calls"] += 1
            s["latency_ms"] += resp.latency_ms
            s["input_tokens"] += resp.input_tokens or 0
            s["output_tokens"] += resp.output_tokens or 0


# ---------- factory ----------

def _make_provider(name: str) -> Provider:
    name = name.strip().lower()
    if name == "gemini":
        return GeminiProvider(config.GEMINI_API_KEY, config.GEMINI_MODEL)
    if name == "anthropic":
        return AnthropicProvider(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL)
    if name == "mock":
        return MockProvider()
    if name == "replay":
        return ReplayProvider(config.LLM_REPLAY_FILE)
    raise ValueError(f"unknown LLM provider {name!r}")


def build_gateway(provider_names: list[str] | None = None) -> LLMGateway:
    """Primary provider first, then fallbacks. Providers with missing keys are skipped with a warning."""
    names = provider_names or [config.GRADER_PROVIDER, *config.LLM_FALLBACKS]
    providers: list[Provider] = []
    for n in dict.fromkeys(x for x in names if x):  # de-duplicate, keep order
        try:
            providers.append(_make_provider(n))
        except ValueError as e:
            log.warning("skipping provider %s: %s", n, e)
    if not providers:
        log.warning("no LLM provider configured; using the offline mock provider")
        providers = [MockProvider()]
    return LLMGateway(providers, max_retries=config.LLM_MAX_RETRIES)


_gateway: LLMGateway | None = None
_gateway_lock = threading.Lock()


def get_gateway() -> LLMGateway:
    global _gateway
    with _gateway_lock:
        if _gateway is None:
            _gateway = build_gateway()
        return _gateway


def reset_gateway(gateway: LLMGateway | None = None) -> None:
    """Swap the shared gateway (tests and evals use this to inject mock/replay providers)."""
    global _gateway
    with _gateway_lock:
        _gateway = gateway
