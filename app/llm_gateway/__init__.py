"""One entry point for every LLM call in the app.

    from app.llm_gateway import get_gateway, LLMRequest
    result, response = get_gateway().complete_json(LLMRequest(...), schema=MyModel)

The gateway handles provider choice and fallback, retries with backoff, JSON
extraction and schema validation (with one repair attempt), a small response
cache, usage/latency stats and LangSmith tracing.
"""

from .gateway import LLMGateway, build_gateway, get_gateway, reset_gateway
from .types import ImageInput, LLMRequest, LLMResponse, ProviderError

__all__ = [
    "ImageInput",
    "LLMGateway",
    "LLMRequest",
    "LLMResponse",
    "ProviderError",
    "build_gateway",
    "get_gateway",
    "reset_gateway",
]
