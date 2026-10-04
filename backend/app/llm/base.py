"""Vendor-neutral LLM provider interface.

Business logic depends only on `LLMProvider` and `LLMResult`. Concrete adapters live in this package
and are selected by `factory.build_provider` from LLM_PROVIDER / LLM_MODEL / LLM_API_KEY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LLMError(RuntimeError):
    """Base class. `category` is a short, loggable error class (never contains user text or secrets)."""

    category = "PROVIDER_ERROR"


class LLMTimeout(LLMError):
    category = "TIMEOUT"


class LLMProviderError(LLMError):
    category = "PROVIDER_ERROR"


class LLMEmptyResponse(LLMError):
    category = "EMPTY_RESPONSE"


class LLMNotConfigured(LLMError):
    category = "NOT_CONFIGURED"


@dataclass
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class LLMResult:
    text: str  # the model's final text output only; no hidden reasoning is requested or kept
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: float = 0.0
    stop_reason: str | None = None


class LLMProvider(Protocol):
    provider: str
    model: str
    is_test_double: bool

    def complete_json(self, system: str, user: str, json_schema: dict, max_tokens: int = 1024) -> LLMResult:
        """Return a single JSON object as text, constrained to `json_schema` where the vendor supports it."""
        ...


def label(p: LLMProvider | None) -> tuple[str | None, str | None]:
    if p is None:
        return None, None
    suffix = " (TEST DOUBLE)" if p.is_test_double else ""
    return p.provider + suffix, p.model
