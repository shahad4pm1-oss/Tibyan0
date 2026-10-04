from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.llm.base import LLMProvider


@dataclass
class ProviderStatus:
    provider: LLMProvider | None
    reason: str | None  # why no provider is available (never contains the key)


def build_provider(s: Settings) -> ProviderStatus:
    name = (s.llm_provider or "").strip().lower()
    if not name or name == "none":
        return ProviderStatus(None, "LLM_PROVIDER not set")
    if name in ("test_double", "scripted"):
        if s.app_env == "production":
            return ProviderStatus(None, "test doubles are refused in production")
        from app.llm.test_doubles import AbstainingTestDouble
        return ProviderStatus(AbstainingTestDouble(), None)
    if name in ("anthropic", "gemini", "google"):
        key = s.llm_api_key.get_secret_value() if s.llm_api_key else ""
        if not s.llm_model:
            return ProviderStatus(None, "LLM_MODEL not set")
        if not key:
            return ProviderStatus(None, "LLM_API_KEY not set")
        base = (s.llm_base_url or "").strip()
        if name == "anthropic":
            from app.llm.anthropic_provider import AnthropicProvider
            return ProviderStatus(AnthropicProvider(model=s.llm_model, api_key=key,
                                                    base_url=base or "https://api.anthropic.com",
                                                    timeout_s=s.llm_timeout_s, temperature=s.llm_temperature), None)
        from app.llm.gemini_provider import DEFAULT_BASE_URL, GeminiProvider
        if "anthropic.com" in base:  # an old .env may still carry the Anthropic default: not a Gemini endpoint
            base = ""
        return ProviderStatus(GeminiProvider(model=s.llm_model, api_key=key, base_url=base or DEFAULT_BASE_URL,
                                             timeout_s=s.llm_timeout_s, temperature=s.llm_temperature), None)
    return ProviderStatus(None, f"unknown LLM_PROVIDER {name!r}")
