"""Anthropic Messages API adapter (plain HTTP, no SDK).

Structured output: `output_config.format = {"type": "json_schema", "schema": ...}` (no beta header),
per https://platform.claude.com/docs/en/build-with-claude/structured-outputs (read 2026-10-01).

The base URL comes ONLY from Tibyan's own setting LLM_BASE_URL (default https://api.anthropic.com).
The adapter never reads ANTHROPIC_* environment variables, so it cannot pick up credentials or
endpoints that belong to other tools on the same machine.

Only `text` content blocks are read. Any other block type (e.g. reasoning blocks some models emit)
is discarded and never stored, logged or shown.

Status: unit-tested with an HTTP mock transport. NOT validated against the live API (no API key).
"""

from __future__ import annotations

import time

import httpx

from app.llm.base import LLMEmptyResponse, LLMProviderError, LLMResult, LLMTimeout, LLMUsage

API_VERSION = "2023-06-01"


class AnthropicProvider:
    provider = "anthropic"
    is_test_double = False

    def __init__(self, model: str, api_key: str, base_url: str = "https://api.anthropic.com",
                 timeout_s: float = 30.0, temperature: float | None = None,
                 transport: httpx.BaseTransport | None = None):
        if not model or not api_key:
            raise ValueError("model and api_key are required")
        self.model = model
        self._key = api_key
        self._temperature = temperature
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport)

    def __repr__(self) -> str:  # never expose the key
        return f"AnthropicProvider(model={self.model!r})"

    def complete_json(self, system: str, user: str, json_schema: dict, max_tokens: int = 1024) -> LLMResult:
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": json_schema}},
        }
        if self._temperature is not None:
            body["temperature"] = self._temperature
        headers = {"x-api-key": self._key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        t0 = time.perf_counter()
        try:
            r = self._client.post("/v1/messages", json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise LLMTimeout("provider timeout") from e
        except httpx.HTTPError as e:
            raise LLMProviderError(f"transport error: {type(e).__name__}") from e
        latency = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            raise LLMProviderError(f"HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise LLMProviderError("non-JSON provider response") from e
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        if not text:
            raise LLMEmptyResponse("empty model output")
        u = data.get("usage") or {}
        return LLMResult(text=text, usage=LLMUsage(u.get("input_tokens"), u.get("output_tokens")),
                         latency_ms=latency, stop_reason=data.get("stop_reason"))
