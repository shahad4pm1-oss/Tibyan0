"""Google Gemini API adapter (plain HTTP, no SDK), for API keys created in Google AI Studio.

Request: POST {base}/v1beta/models/{model}:generateContent with header `x-goog-api-key`.
Structured output: generationConfig.responseMimeType = "application/json" plus
generationConfig.responseJsonSchema (JSON Schema). If the service rejects the schema itself (HTTP 400 that
names the schema), the call is repeated once with JSON mode only; Tibyan validates every output against
its own strict schema afterwards in any case, so nothing unvalidated is ever shown.

The base URL comes ONLY from Tibyan's own setting LLM_BASE_URL (default
https://generativelanguage.googleapis.com). The adapter never reads GOOGLE_* / GEMINI_* environment
variables. Only the model's answer text is read: parts marked as thoughts are discarded, never stored,
logged or shown. Error messages carry only the HTTP status and Google's error codes (never the key and
never user text).

Gemma models served through the same API (model ids starting with "gemma-", e.g. gemma-3-27b-it) accept
neither a system instruction nor JSON mode / a response schema. For them the system text is sent at the
top of the user turn and the answer is requested as plain text; Tibyan's parser and strict validator then
apply as for every model.

Status: unit-tested with an HTTP mock transport. NOT validated against the live API from the build
environment (no network route to Google there); validate with eval/provider_health.py.
"""

from __future__ import annotations

import time

import httpx

from app.llm.base import LLMEmptyResponse, LLMProviderError, LLMResult, LLMTimeout, LLMUsage

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
# Gemini "thinking" models count their internal reasoning against maxOutputTokens; keep headroom so the
# visible JSON answer is not cut off. Tibyan never requests or keeps the reasoning itself.
MIN_OUTPUT_TOKENS = 8192


def _error_detail(r: httpx.Response) -> str:
    """HTTP status plus Google's machine-readable codes only (e.g. INVALID_ARGUMENT / API_KEY_INVALID)."""
    parts = [f"HTTP {r.status_code}"]
    try:
        err = (r.json() or {}).get("error") or {}
    except ValueError:
        return parts[0]
    if isinstance(err.get("status"), str):
        parts.append(err["status"])
    for d in err.get("details") or []:
        reason = d.get("reason") if isinstance(d, dict) else None
        if isinstance(reason, str) and reason.replace("_", "").isalnum():
            parts.append(reason)
    return " ".join(parts)


def _plain_mode_hint(r: httpx.Response) -> bool:
    """400 errors that mean 'this model does not support system instructions / JSON mode' (Gemma)."""
    try:
        msg = str(((r.json() or {}).get("error") or {}).get("message", "")).lower()
    except ValueError:
        return False
    return "developer instruction" in msg or "json mode" in msg or "system instruction" in msg


def _mentions_schema(r: httpx.Response) -> bool:
    try:
        msg = str(((r.json() or {}).get("error") or {}).get("message", ""))
    except ValueError:
        return False
    return "schema" in msg.lower()


class GeminiProvider:
    provider = "gemini"
    is_test_double = False

    def __init__(self, model: str, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 timeout_s: float = 30.0, temperature: float | None = None,
                 transport: httpx.BaseTransport | None = None):
        if not model or not api_key:
            raise ValueError("model and api_key are required")
        self.model = model.strip().removeprefix("models/")
        self._key = api_key
        self._temperature = temperature
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport)
        self.plain_mode = self.model.lower().startswith("gemma")

    def __repr__(self) -> str:  # never expose the key
        return f"GeminiProvider(model={self.model!r})"

    def _diagnose_404(self) -> str:
        """A 404 means this key cannot see the model id. List the models the key CAN use (names only) so the
        banner says what to put in LLM_MODEL. A failing list call means the key itself is the problem."""
        try:
            r = self._client.get("/v1beta/models", params={"pageSize": 1000},
                                 headers={"x-goog-api-key": self._key})
        except httpx.HTTPError as e:
            return f"model list unavailable ({type(e).__name__})"
        if r.status_code != 200:
            return f"model list refused ({_error_detail(r)}): check LLM_API_KEY is a Google AI Studio key"
        try:
            models = [m for m in (r.json() or {}).get("models") or [] if isinstance(m, dict)]
        except ValueError:
            return "model list unreadable"
        names = [str(m.get("name", "")).removeprefix("models/") for m in models
                 if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        family = "gemma" if self.model.lower().startswith("gemma") else "gemini"
        close = [n for n in names if n.lower().startswith(family)] or names
        if not close:
            return f"model '{self.model}' not available; this key lists no usable models"
        return f"model '{self.model}' not available to this key; available: {', '.join(close[:8])}"

    def _google_message(self, r: httpx.Response) -> str:
        """Google's error message for a 404 (it names the model id only: no user text), key scrubbed."""
        try:
            msg = str(((r.json() or {}).get("error") or {}).get("message", "")).strip()
        except ValueError:
            return ""
        return f"; Google: {msg.replace(self._key, '***')[:300]}" if msg else ""

    @staticmethod
    def _to_plain(body: dict, system: str, user: str) -> None:
        """No system instruction and no JSON mode: system text leads the user turn; JSON asked for in words."""
        body.pop("systemInstruction", None)
        gen = body["generationConfig"]
        gen.pop("responseMimeType", None)
        gen.pop("responseJsonSchema", None)
        text = (f"{system}\n\n=== END OF SYSTEM RULES ===\n\n{user}\n\n"
                "Reply with the JSON object only: no code fence, no text before or after it.")
        body["contents"] = [{"role": "user", "parts": [{"text": text}]}]

    def _post(self, body: dict) -> httpx.Response:
        headers = {"x-goog-api-key": self._key, "content-type": "application/json"}
        try:
            return self._client.post(f"/v1beta/models/{self.model}:generateContent", json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise LLMTimeout("provider timeout") from e
        except httpx.HTTPError as e:
            raise LLMProviderError(f"transport error: {type(e).__name__}") from e

    def complete_json(self, system: str, user: str, json_schema: dict, max_tokens: int = 1024) -> LLMResult:
        gen: dict = {
            "responseMimeType": "application/json",
            "responseJsonSchema": json_schema,
            "maxOutputTokens": max(max_tokens, MIN_OUTPUT_TOKENS),
        }
        if self._temperature is not None:
            gen["temperature"] = self._temperature
        body: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen,
        }
        if self.plain_mode:
            self._to_plain(body, system, user)
        t0 = time.perf_counter()
        r = self._post(body)
        if r.status_code == 400 and not self.plain_mode and _plain_mode_hint(r):
            self.plain_mode = True  # remembered for later calls
            self._to_plain(body, system, user)
            r = self._post(body)
        if r.status_code == 400 and _mentions_schema(r):
            # schema feature not accepted for this model: JSON mode only; Tibyan's validator still applies
            gen.pop("responseJsonSchema", None)
            r = self._post(body)
        latency = (time.perf_counter() - t0) * 1000
        if r.status_code == 404:
            # Google's own 404 text says when a still-listed model id is retired and names its replacement
            raise LLMProviderError(_error_detail(r) + "; " + self._diagnose_404() + self._google_message(r))
        if r.status_code != 200:
            raise LLMProviderError(_error_detail(r))
        try:
            data = r.json()
        except ValueError as e:
            raise LLMProviderError("non-JSON provider response") from e
        cands = data.get("candidates") or []
        first = cands[0] if cands else {}
        parts = ((first.get("content") or {}).get("parts")) or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
        if not text:
            reason = first.get("finishReason") or (data.get("promptFeedback") or {}).get("blockReason") or "none"
            raise LLMEmptyResponse(f"empty model output (finish reason {reason})")
        u = data.get("usageMetadata") or {}
        return LLMResult(text=text, usage=LLMUsage(u.get("promptTokenCount"), u.get("candidatesTokenCount")),
                         latency_ms=latency, stop_reason=first.get("finishReason"))
