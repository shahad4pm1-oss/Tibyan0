"""The gate runs before the LLM; the LLM is called only on PASS."""

import pytest

from app.db.connection import connect
from app.services.content_level_router import Level
from app.services.evidence_gate import GateDecision, Strength, evaluate
from app.services.source_resolver import Resolution
from app.services.types import MatchStatus, QuoteMatch, ResolutionStatus

from .conftest import ask, good_output, make_pipeline

EXACT = "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ"
CLAIM = "النص يذكر أن الطالب كتب ملخصا"


def _called(p):
    return len(p.llm.calls)


def test_pass_calls_llm_once(synthetic_db):
    p = make_pipeline(synthetic_db, [good_output()])
    r = ask(p, EXACT, CLAIM)
    assert r.claim_analysis.gate.decision == "PASS" and _called(p) == 1
    assert r.evidence.strength == "SUFFICIENT"


@pytest.mark.parametrize("quote,reason", [
    ("اشترى المهندس حاسوبا جديدا للمختبر", "SOURCE_NOT_FOUND"),
    ("الى البيت قبل غروب الشمس", "SOURCE_AMBIGUOUS"),
    ("لعب الاطفال بالكرة قرب النهر", "NEAR_MATCH_UNCONFIRMED"),
    ("القطارات البرتقالية", "SOURCE_NOT_FOUND"),  # PENDING source text: never retrievable
])
def test_insufficient_and_llm_not_called(synthetic_db, quote, reason):
    p = make_pipeline(synthetic_db, [good_output()])
    r = ask(p, quote, CLAIM)
    assert r.claim_analysis.gate.decision == "INSUFFICIENT" and reason in r.claim_analysis.gate.reasons
    assert r.claim_analysis.relation == "INSUFFICIENT_EVIDENCE" and r.claim_analysis.status == "ABSTAINED"
    assert _called(p) == 0
    assert r.evidence.strength == "INSUFFICIENT"


def test_quote_too_short(synthetic_db):
    p = make_pipeline(synthetic_db, [good_output()])
    r = ask(p, "دفتره الازرق", CLAIM)  # 2 tokens: resolvable, too short to analyse
    assert "QUOTE_TOO_SHORT_FOR_ANALYSIS" in r.claim_analysis.gate.reasons and _called(p) == 0
    assert r.evidence.strength == "LIMITED"


def test_integrity_failure_blocks_llm(synthetic_copy):
    c = connect(synthetic_copy)
    c.execute("UPDATE passages SET original_text = original_text || ' ' WHERE id = 'synth:2:5'")
    c.commit()
    p = make_pipeline(synthetic_copy, [good_output()])
    assert p.corpus_integrity_ok is False
    r = ask(p, EXACT, CLAIM)
    assert "INTEGRITY_CHECK_FAILED" in r.claim_analysis.gate.reasons and _called(p) == 0
    assert r.evidence.strength == "INSUFFICIENT"


def test_level_d_specialist_required_before_llm(synthetic_db):
    p = make_pipeline(synthetic_db, [good_output()])
    r = ask(p, EXACT, "أنا في دولة كذا، هل يجوز لي فعل هذا؟")
    assert r.claim_analysis.gate.decision == "SPECIALIST_REQUIRED" and _called(p) == 0
    assert r.claim_analysis.relation == "REQUIRES_SPECIALIST"


def test_unit_missing_evidence_and_context():
    res = Resolution(ResolutionStatus.RESOLVED, source={"verification_status": "APPROVED"})
    m = QuoteMatch(MatchStatus.EXACT, "phrase")
    g = evaluate(Level.B, res, m, [], 0, True, 6, 3, 5)
    assert g.decision is GateDecision.INSUFFICIENT
    assert {"NO_EVIDENCE", "NO_CONTEXT"} <= set(g.reasons) and g.strength is Strength.INSUFFICIENT


def test_unit_source_not_approved():
    res = Resolution(ResolutionStatus.RESOLVED, source={"verification_status": "PENDING_REVIEW"})
    g = evaluate(Level.B, res, QuoteMatch(MatchStatus.EXACT, "phrase"), [], 1, True, 6, 3, 5)
    assert "SOURCE_NOT_APPROVED" in g.reasons


def test_paraphrased_never_passes():
    res = Resolution(ResolutionStatus.RESOLVED, source={"verification_status": "APPROVED"})
    g = evaluate(Level.B, res, QuoteMatch(MatchStatus.PARAPHRASED, "x"), [], 1, True, 6, 3, 5)
    assert g.decision is GateDecision.INSUFFICIENT and "NO_DIRECT_TEXTUAL_MATCH" in g.reasons
