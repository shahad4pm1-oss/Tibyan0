"""Minimal real-provider health check (run before any real-model evaluation).

One structured-output call through the existing LLMProvider adapter, configured ONLY from Tibyan's
settings (LLM_PROVIDER / LLM_MODEL / LLM_API_KEY, via environment or .env). Never a test double.
Checks: provider configured, authentication, model exists, request succeeds, structured JSON received,
latency recorded. Never prints the API key. Writes eval/results/provider_health.json.

Exit codes: 0 OK, 2 BLOCKED (not configured / test double), 1 FAILED (call failed).
usage: python eval/provider_health.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.llm.base import LLMError
from app.llm.factory import build_provider

OUT = ROOT / "eval/results/provider_health.json"
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}, "lang": {"type": "string"}},
          "required": ["ok", "lang"], "additionalProperties": False}


def write(rep: dict) -> None:
    rep["checked_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False))


def main() -> int:
    s = Settings()
    st = build_provider(s)
    if st.provider is None:
        write({"status": "BLOCKED_BY_LLM_ACCESS", "reason": st.reason, "llm_provider": s.llm_provider,
               "llm_model": s.llm_model, "api_key_present": bool(s.llm_api_key)})
        return 2
    p = st.provider
    if p.is_test_double:
        write({"status": "BLOCKED_BY_LLM_ACCESS", "reason": "configured provider is a test double", "llm_provider": p.provider})
        return 2
    try:
        r = p.complete_json("Return a JSON object only.", 'Reply with {"ok": true, "lang": "ar"}.', SCHEMA, 64)
        obj = json.loads(r.text)
        ok = obj == {"ok": True, "lang": "ar"}
        write({"status": "OK" if ok else "UNEXPECTED_OUTPUT", "llm_provider": p.provider, "llm_model": p.model,
               "latency_ms": round(r.latency_ms, 1), "input_tokens": r.usage.input_tokens,
               "output_tokens": r.usage.output_tokens, "structured_output_parsed": True})
        return 0 if ok else 1
    except LLMError as e:
        write({"status": "FAILED", "error_category": e.category, "detail": str(e), "llm_provider": p.provider,
               "llm_model": p.model})
        return 1
    except (ValueError, TypeError):
        write({"status": "FAILED", "error_category": "INVALID_JSON", "llm_provider": p.provider, "llm_model": p.model})
        return 1


if __name__ == "__main__":
    sys.exit(main())
