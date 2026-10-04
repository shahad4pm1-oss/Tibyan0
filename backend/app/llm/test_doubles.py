"""TEST DOUBLES. Their output is never a real model result and is labelled "(TEST DOUBLE)" everywhere.
All are refused when APP_ENV=production (see factory.py).
"""

from __future__ import annotations

import json
from collections.abc import Callable

from app.llm.base import LLMError, LLMResult, LLMUsage


class ScriptedProvider:
    """Returns pre-scripted outputs in order. An item may be a string (returned as model text),
    a dict (JSON-encoded), an Exception (raised), or a callable(system, user) -> str|dict."""

    provider = "scripted"
    is_test_double = True

    def __init__(self, script: list, model: str = "scripted-v1"):
        self.model = model
        self._script = list(script)
        self.calls: list[dict] = []

    def complete_json(self, system: str, user: str, json_schema: dict, max_tokens: int = 1024) -> LLMResult:
        self.calls.append({"system": system, "user": user, "schema": json_schema})
        if not self._script:
            raise LLMError("script exhausted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(system, user)
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return LLMResult(text=text, usage=LLMUsage(len(system) // 4 + len(user) // 4, len(text) // 4), latency_ms=1.0)


class AbstainingTestDouble:
    """For running the app without a real model (LLM_PROVIDER=test_double, non-production only).
    Always abstains, so it can never produce a substantive verdict."""

    provider = "test_double"
    model = "always-insufficient-v1"
    is_test_double = True

    def complete_json(self, system: str, user: str, json_schema: dict, max_tokens: int = 1024) -> LLMResult:
        if "verdict" in json_schema.get("properties", {}):  # claim-centric minimal schema
            out = {"verdict": "unrelated", "assertions": [{
                "claim_part": "مخرجات اختبارية", "label": "not_in_evidence",
                "evidence_context": "TEST DOUBLE: no real language model is configured; هذه استجابة من بديل اختباري."}]}
            return LLMResult(text=json.dumps(out, ensure_ascii=False), usage=LLMUsage(None, None), latency_ms=0.0)
        out = {
            "relation": "INSUFFICIENT_EVIDENCE",
            "summary": "مخرجات اختبارية: لم يُستخدم نموذج حقيقي، فلا يصدر حكم على الادعاء.",
            "reason": "هذه استجابة من بديل اختباري وليست تحليلًا.",
            "evidence_ids": [],
            "key_evidence": [],
            "needs_specialist": False,
            "uncertainty_reason": "TEST DOUBLE: no real language model is configured.",
        }
        return LLMResult(text=json.dumps(out, ensure_ascii=False), usage=LLMUsage(None, None), latency_ms=0.0)


Responder = Callable[[str, str], str | dict]
