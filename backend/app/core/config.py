"""Runtime settings loaded from environment variables.

No secret has a default value. Retrieval thresholds below are configurable
starting values; they are NOT calibrated unless docs/METHODOLOGY.md says so.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
# The .env file is read from the REPOSITORY ROOT regardless of the working directory (the backend is
# started from backend/). TIBYAN_ENV_FILE overrides the path; an empty value disables the file (tests).
_ENV_FILE = os.environ.get("TIBYAN_ENV_FILE", str(REPO_ROOT / ".env")) or None


class Settings(BaseSettings):
    # env_parse_none_str="": an empty value in .env means "unset" (e.g. LLM_TEMPERATURE=)
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore",
                                      env_parse_none_str="")

    app_env: Literal["development", "test", "production"] = "development"
    database_path: str = Field(default="data/indexes/tibyan.sqlite3")
    faiss_index_path: str = Field(default="data/indexes/tibyan.faiss")
    corpus_version: str = Field(default="unbuilt")
    pipeline_version: str = Field(default="0.5.0-local-v1")
    retrieval_version: str = Field(default="r2.0")

    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    # Tibyan's own setting; empty = the provider's official endpoint. ANTHROPIC_*/GOOGLE_*/GEMINI_* env vars are never read
    llm_base_url: str | None = None
    llm_timeout_s: float = 30.0
    llm_temperature: float | None = None
    llm_max_tokens: int = 4096  # micro-assertion JSON in Arabic needs room; a cut-off answer is rejected
    llm_price_input_per_mtok: float | None = None  # operator-supplied; no built-in prices
    llm_price_output_per_mtok: float | None = None
    prompt_version: str = "claim_analysis_v2"
    gate_min_quote_tokens: int = 3
    strength_min_tokens_sufficient: int = 5

    embedding_provider: str | None = Field(default="local_lsa")
    embedding_model: str | None = Field(default="char-ngram-lsa-v1")
    embedding_api_key: SecretStr | None = None

    # Retrieval (uncalibrated starting values)
    lexical_top_k: int = 20
    semantic_top_k: int = 20
    hybrid_top_n: int = 5
    rrf_k: int = 60
    # lexical_first (default, evidence-backed) | rrf. See docs/METHODOLOGY.md §Retrieval results.
    hybrid_strategy: str = "lexical_first"
    # Quote matching / source resolution (uncalibrated starting values)
    # PARAPHRASED is reserved/experimental. "disabled" (default) never attributes a non-exact match.
    # "experimental" is refused when APP_ENV=production.
    paraphrase_mode: str = "disabled"
    paraphrase_min_coverage: float = 0.6
    paraphrase_min_margin: float = 0.1
    min_partial_tokens: int = 2
    max_span_ayat: int = 3
    context_window: int = 2
    # Local tafsir commentary (one JSON file per surah). Empty/missing directory = no commentary evidence.
    tafsir_enabled: bool = True
    tafsir_data_dir: str = "data/json-data"
    tafsir_max_chars: int = 4000
    # Tafsir provider: "tabari" (Quran.com API v4, resource 15, with the local files as fallback when an ayah
    # cannot be fetched), "tabari_only", or "local" (local files only; no network).
    tafsir_provider: str = "tabari"
    tafsir_api_base_url: str = "https://api.quran.com/api/v4"
    tafsir_api_resource_id: int = 15
    tafsir_api_timeout_s: float = 6.0

    cors_origins: str = Field(default="http://localhost:5173")
    # API hardening (documented in docs/SECURITY.md)
    rate_limit_per_minute: int = 30  # per client IP on POST /api/v1/analyze; 0 disables (tests/load tests only)
    trust_proxy_headers: bool = False  # use X-Forwarded-For (set true behind Render/Netlify proxies)
    max_body_bytes: int = 16384
    request_timeout_s: float = 45.0
    log_raw_input: bool = Field(default=False)  # SP-07: off by default

    @property
    def effective_request_timeout_s(self) -> float:
        """Whole-request budget. When an LLM is configured it must cover one call plus the single corrective
        retry (2 x LLM_TIMEOUT_S) and local processing, otherwise the API answers 504 before the model replies."""
        tafsir = ((self.tafsir_api_timeout_s + 1) * self.max_span_ayat
                  if self.tafsir_enabled and self.tafsir_provider.lower() != "local" else 0)
        if not self.llm_provider:
            return self.request_timeout_s + tafsir
        return max(self.request_timeout_s, 2 * self.llm_timeout_s + 15) + tafsir

    @property
    def cors_origin_list(self) -> list[str]:
        """Development/test: as configured. Production: explicit https origins only; '*' and localhost are dropped."""
        origins = [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]
        if self.app_env == "production":
            origins = [o for o in origins if o != "*" and o.startswith("https://")
                       and "localhost" not in o and "127.0.0.1" not in o]
        return origins

    def production_problems(self) -> list[str]:
        """Configuration that must never reach production. Empty list = OK."""
        if self.app_env != "production":
            return []
        p = []
        if (self.embedding_provider or "") == "hash":
            p.append("EMBEDDING_PROVIDER=hash is a test double")
        if (self.llm_provider or "").lower() in ("test_double", "scripted"):
            p.append("LLM_PROVIDER is a test double")
        if self.paraphrase_mode != "disabled":
            p.append("PARAPHRASE_MODE must be disabled")
        if self.rate_limit_per_minute <= 0:
            p.append("RATE_LIMIT_PER_MINUTE must be > 0")
        if not self.cors_origin_list:
            p.append("CORS_ORIGINS has no explicit https frontend origin")
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
