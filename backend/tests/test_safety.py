"""Safety service: output lint, final routing, privacy of logs."""

import json
import logging

import pytest

from app.schemas.claim_analysis import LLMClaimOutput
from app.services import safety
from app.services.content_level_router import Level
from app.services.evidence_gate import GateDecision, GateResult

from .conftest import ask, good_output, make_pipeline

EXACT = "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ"


@pytest.mark.parametrize("text,code", [
    ("يجوز لك أن تفعل ذلك وفق E1", "PERSONAL_RULING_LANGUAGE"),
    ("فلا يجوز لك هذا", "PERSONAL_RULING_LANGUAGE"),
    ("صاحب الادعاء كاذب", "PERSON_JUDGMENT_LANGUAGE"),
    ("الكاتب يتعمد التحريف", "PERSON_JUDGMENT_LANGUAGE"),
    ("يبدو أن عقيدتك مختلفة", "USER_PROFILING_LANGUAGE"),
    ("وهذا ثابت بالإجماع", "UNSUPPORTED_CERTAINTY"),
    ("قطعًا يدل E1 على ذلك", "UNSUPPORTED_CERTAINTY"),
])
def test_output_lint(text, code):
    assert code in safety.lint_output(LLMClaimOutput.model_validate(good_output(reason=text)))


def test_lint_allows_neutral_text():
    o = good_output(reason="الادعاء أوسع مما يدل عليه E1 في سياقه، إذ يقيد E1 الحكم بشرط.")
    assert safety.lint_output(LLMClaimOutput.model_validate(o)) == []


class _Out:
    def __init__(self, status, output=None):
        self.status, self.output, self.error_category, self.last_issues = status, output, "X", ["Y"]


def test_finalize_level_d_and_gate():
    f = safety.finalize(Level.D, GateResult(GateDecision.SPECIALIST_REQUIRED, ["PERSONAL_CASE_LEVEL_D"]), None)
    assert f.relation == "REQUIRES_SPECIALIST" and f.referral and f.summary_source == "system_template"
    f = safety.finalize(Level.B, GateResult(GateDecision.INSUFFICIENT, ["SOURCE_NOT_FOUND"]), None)
    assert f.relation == "INSUFFICIENT_EVIDENCE" and f.summary == "لم نعثر على مرجع كافٍ في المصادر المتاحة."
    assert "مكذوب" not in f.summary


def test_finalize_level_c_is_scoped_to_text():
    o = LLMClaimOutput.model_validate(good_output("CONTRADICTED"))
    f = safety.finalize(Level.C, GateResult(GateDecision.PASS), _Out("OK", o))
    # SCOPED: the text-context verdict is kept, flagged, and always carries a referral
    assert f.relation == "CONTRADICTED" and "LEVEL_C_SCOPED_TO_TEXT" in f.safety_overrides
    assert f.referral and f.summary_source == "ai" and f.uncertainty_reason == "LEVEL_C_TEXT_SCOPE_ONLY"


@pytest.mark.parametrize("text", ["فهو كافر بنص الآية", "وعليه فهم كفار", "الحكم الشرعي أن هذا محرم"])
def test_lint_rejects_standalone_ruling(text):
    o = LLMClaimOutput.model_validate(good_output("SUPPORTED", reason=f"E1 يذكر ذلك، {text}"))
    assert "STANDALONE_RULING_LANGUAGE" in safety.lint_output(o)


def test_finalize_level_c_keeps_abstention():
    o = LLMClaimOutput.model_validate(good_output("INSUFFICIENT_EVIDENCE"))
    assert safety.finalize(Level.C, GateResult(GateDecision.PASS), _Out("OK", o)).relation == "INSUFFICIENT_EVIDENCE"


def test_finalize_provider_failure_has_no_verdict():
    f = safety.finalize(Level.B, GateResult(GateDecision.PASS), _Out("PROVIDER_ERROR"))
    assert f.relation is None and f.status == "ANALYSIS_UNAVAILABLE"


def test_logs_contain_no_raw_user_text(synthetic_db, caplog):
    p = make_pipeline(synthetic_db, [good_output()])
    claim = "ادعاء سري لا يجوز تسجيله في السجلات"
    with caplog.at_level(logging.DEBUG):
        ask(p, EXACT, claim)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert claim not in blob and "ملخصا قصيرا" not in blob
    audit = [json.loads(r.getMessage()) for r in caplog.records if r.name == "tibyan.audit"]
    assert len(audit) == 1
    a = audit[0]
    for k in ("request_id", "ts", "status", "retrieved_ids", "evidence_ids", "content_level", "relation",
              "llm_provider", "llm_model", "prompt_version", "latency_ms", "error_category"):
        assert k in a
    assert "quote" not in a and "claim" not in a


def test_test_double_refused_in_production(synthetic_as_production):
    from app.llm.test_doubles import ScriptedProvider
    p = make_pipeline(synthetic_as_production, provider=ScriptedProvider([good_output()]), app_env="production",
                      embedding_provider="none")
    assert p.llm is None and "production" in p.llm_unavailable_reason


@pytest.mark.parametrize("text", ["يذكر E1 أحوال الجاهلية قبل الإسلام.", "يتحدث E1 عن الدين كله لله."])
def test_lint_no_false_positive_on_common_words(text):
    assert safety.lint_output(LLMClaimOutput.model_validate(good_output(reason=text))) == []


def test_audit_line_emitted_by_app_logging_config(synthetic_db):
    """The app's own handler (not pytest's capture) emits the audit line, without user text."""
    import io

    from app.main import configure_logging, log
    configure_logging()
    h = next(h for h in log.handlers if getattr(h, "_tibyan", False))
    buf = io.StringIO()
    old = h.setStream(buf)
    try:
        p = make_pipeline(synthetic_db, [good_output()])
        ask(p, EXACT, "ادعاء خاص جدا للاختبار")
    finally:
        h.setStream(old)
    out = buf.getvalue()
    assert "tibyan.audit" in out and '"request_id"' in out
    assert "ادعاء خاص جدا للاختبار" not in out
