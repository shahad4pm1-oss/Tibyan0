"""Claim-centric analyzer: two-stage pipeline, Level C scoping, micro-assertion minimal schema."""

import json

import pytest
from pydantic import ValidationError

from app.llm.base import LLMResult, LLMUsage
from app.schemas.claim_analysis import LLMMinimalOutput, minimal_json_schema, to_claim_output
from app.services.claim_analyzer import PromptSet
from app.services.content_level_router import Level, Policy, route

from .conftest import ask, good_minimal, good_output, make_pipeline

EXACT = "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ"
CLAIM = "النص يذكر أنه كتب ملخصا في دفتر"


class _RealLike:
    """A provider that is NOT a test double (like a real model), scripted for tests."""
    provider, model, is_test_double = "reallike", "reallike-1", False

    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), []

    def complete_json(self, system, user, json_schema, max_tokens=1024):
        self.calls.append({"system": system, "user": user, "schema": json_schema})
        return LLMResult(text=json.dumps(self.outputs.pop(0), ensure_ascii=False), usage=LLMUsage(10, 10),
                         latency_ms=1.0)


def test_pipeline_has_two_stages(synthetic_db):
    p = make_pipeline(synthetic_db, [good_minimal()])
    warnings, t = [], {}
    a = p.attribute(EXACT, warnings, t)
    assert a.status == "RESOLVED" and a.items and a.source_out is not None and len(p.llm.calls) == 0
    c = p.analyze_claim(EXACT, CLAIM, a, t)
    assert len(p.llm.calls) == 1 and c.final.relation == "SUPPORTED" and c.final.verdict == "correct"


@pytest.mark.parametrize(("verdict", "parts", "relation", "status"), [
    ("correct", [("كتب ملخصا", "E1: يذكر النص الكتابة.", "supported")], "SUPPORTED", "COMPLETED"),
    ("manipulated", [("كتب ملخصا", "E1: يذكر النص الكتابة.", "supported"),
                     ("في كل يوم", "E1: لا يذكر النص التكرار، فهذا تعميم.", "overstated")], "OVERSTATED", "COMPLETED"),
    ("manipulated", [("لم يكتب شيئا", "E1: يذكر النص أنه كتب.", "contradicted")], "CONTRADICTED", "COMPLETED"),
    ("unrelated", [("موضوع آخر", "لا يتناول الدليل هذا.", "not_in_evidence")], "INSUFFICIENT_EVIDENCE", "ABSTAINED"),
])
def test_minimal_output_end_to_end(synthetic_db, verdict, parts, relation, status):
    p = make_pipeline(synthetic_db, provider=_RealLike([good_minimal(verdict, parts)]))
    ca = ask(p, EXACT, CLAIM).claim_analysis
    assert (ca.relation, ca.status, ca.verdict) == (relation, status, verdict)
    assert [a.claim_part for a in ca.assertions] == [c for c, _, _ in parts]
    assert p.llm.calls[0]["schema"] == minimal_json_schema()
    assert "micro-assertion" in p.llm.calls[0]["system"]


def test_real_provider_must_use_minimal_schema(synthetic_db):
    p = make_pipeline(synthetic_db, provider=_RealLike([good_output(), good_output()]))
    ca = ask(p, EXACT, CLAIM).claim_analysis
    assert ca.status == "AI_OUTPUT_REJECTED" and "SCHEMA_INVALID" in ca.uncertainty_reason


@pytest.mark.parametrize("bad", [
    {"verdict": "correct", "assertions": [{"claim_part": "x", "evidence_context": "بلا معرف", "label": "supported"}]},
    {"verdict": "correct", "assertions": [{"claim_part": "x", "evidence_context": "E1", "label": "maybe"}]},
    {"verdict": "correct", "assertions": []},
    {"verdict": "fatwa", "assertions": [{"claim_part": "x", "evidence_context": "E1", "label": "supported"}]},
    {"verdict": "correct", "assertions": [{"claim_part": "x", "evidence_context": "E1", "label": "supported"}],
     "relation": "SUPPORTED"},
])
def test_minimal_schema_is_strict(bad):
    with pytest.raises(ValidationError):
        LLMMinimalOutput.model_validate(bad)


def test_all_parts_specialist_maps_to_referral():
    o = to_claim_output(LLMMinimalOutput.model_validate(good_minimal(
        "unrelated", [("هل هم كفار", "يحتاج إلى حكم مختص.", "requires_specialist")])))
    assert o.relation == "REQUIRES_SPECIALIST" and o.needs_specialist


def test_level_c_takfir_is_scoped_not_blocked():
    r = route("الآية تدل على تكفير هذه الجماعة")
    assert r.level is Level.C and r.policy is Policy.SCOPED and "NO_TAKFIR" in r.scope
    assert any(m.startswith("C.takfir") for m in r.matched)
    assert route("أفتوني في مسألة ميراثي").policy is Policy.BLOCKED


def test_level_c_ruling_from_model_is_rejected(synthetic_db):
    ruling = good_minimal("correct", [("هم كفار", "E1: يذكر النص ذلك، فهم كفار.", "supported")])
    p = make_pipeline(synthetic_db, provider=_RealLike([ruling, ruling]))
    ca = ask(p, EXACT, "النص يثبت تكفير من كتب في الدفتر").claim_analysis
    assert ca.content_level == "C" and ca.status == "AI_OUTPUT_REJECTED"
    assert "STANDALONE_RULING_LANGUAGE" in ca.uncertainty_reason


def test_level_c_scoped_prompt_guidance(synthetic_db):
    p = make_pipeline(synthetic_db, provider=_RealLike([good_minimal()]))
    ca = ask(p, EXACT, "النص يثبت أن هذا الفعل واجب").claim_analysis
    u = p.llm.calls[0]["user"]
    assert "CONTENT_LEVEL: C" in u and "SCOPED" in u and "fatwa" in u
    assert ca.level_policy == "SCOPED" and ca.referral and "LEVEL_C_SCOPED_TO_TEXT" in ca.safety_overrides


def test_v2_is_default_and_keeps_tafsir_directive():
    from app.core.config import Settings
    from app.services.evidence_builder import TAFSIR_SEPARATION_DIRECTIVE
    ps = PromptSet.load(Settings().prompt_version)
    assert ps.version == "claim_analysis_v2" and ps.minimal and TAFSIR_SEPARATION_DIRECTIVE in ps.system
    assert not PromptSet.load("claim_analysis_v1").minimal


@pytest.mark.parametrize(("verdict", "labels", "expected"), [
    ("correct", ["contradicted"], "manipulated"),
    ("correct", ["supported", "not_in_evidence"], "manipulated"),   # the claim adds meaning the text lacks
    ("manipulated", ["supported"], "correct"),
    ("unrelated", ["supported"], "correct"),
    ("correct", ["not_in_evidence"], "unrelated"),
])
def test_inconsistent_verdict_is_reconciled_not_dropped(verdict, labels, expected):
    parts = [("جزء", "E1: نص." if lbl != "not_in_evidence" else "لا يذكر.", lbl) for lbl in labels]
    o = to_claim_output(LLMMinimalOutput.model_validate(good_minimal(verdict, parts)))
    assert o.verdict == expected and o.notes == ["VERDICT_RECONCILED"]


def test_ids_next_to_arabic_letters_and_loose_labels_are_read():
    m = LLMMinimalOutput.model_validate({"verdict": "Manipulated", "assertions": [
        {"claim_part": "في كل زمان", "evidence_context": "يبين السياق وE2 والدليلE١٠ أن الأمر مقيد.", "label": "Over-stated"},
        {"claim_part": "غيرهم", "evidence_context": "لا يذكر", "label": "Not in evidence"}]})
    assert m.assertions[0].cited_ids == ["E2", "E10"] and m.assertions[1].label == "not_in_evidence"


def test_long_text_is_accepted_and_clipped_for_display():
    long_ctx = "E1: " + "يبين السياق أن الأمر مقيد بحال القتال. " * 30
    o = to_claim_output(LLMMinimalOutput.model_validate(good_minimal("correct", [("جزء", long_ctx, "supported")])))
    assert len(o.key_evidence[0].relevance) <= 400 and len(o.reason) <= 1200


def test_verdict_reconciliation_is_reported(synthetic_db):
    out = good_minimal("correct", [("كتب", "E1: يذكر.", "supported"), ("دائما", "لا يذكر التكرار.", "not_in_evidence")])
    ca = ask(make_pipeline(synthetic_db, provider=_RealLike([out])), EXACT, CLAIM).claim_analysis
    assert ca.status == "COMPLETED" and ca.verdict == "manipulated" and "VERDICT_RECONCILED" in ca.safety_overrides


class _Crashing(_RealLike):
    def complete_json(self, *a, **k):
        raise KeyError("boom")


def test_provider_crash_still_returns_verified_result(synthetic_db):
    r = ask(make_pipeline(synthetic_db, provider=_Crashing([])), EXACT, CLAIM)
    assert r.source is not None and r.claim_analysis.status == "ANALYSIS_UNAVAILABLE"
    assert r.claim_analysis.uncertainty_reason == "UNEXPECTED_KeyError"


def test_truncated_answer_is_named(synthetic_db):
    class _Cut(_RealLike):
        def complete_json(self, system, user, json_schema, max_tokens=1024):
            return LLMResult(text='{"verdict": "correct", "assertions": [{"claim_', usage=LLMUsage(1, 1),
                             latency_ms=1.0, stop_reason="max_tokens")
    ca = ask(make_pipeline(synthetic_db, provider=_Cut([])), EXACT, CLAIM).claim_analysis
    assert ca.status == "AI_OUTPUT_REJECTED" and "OUTPUT_TRUNCATED" in ca.uncertainty_reason


def test_provider_error_reason_is_visible(synthetic_db):
    from app.llm.base import LLMProviderError

    class _Http404(_RealLike):
        def complete_json(self, *a, **k):
            raise LLMProviderError("HTTP 404 NOT_FOUND")
    ca = ask(make_pipeline(synthetic_db, provider=_Http404([])), EXACT, CLAIM).claim_analysis
    assert ca.status == "ANALYSIS_UNAVAILABLE" and ca.uncertainty_reason == "PROVIDER_ERROR: HTTP 404 NOT_FOUND"
