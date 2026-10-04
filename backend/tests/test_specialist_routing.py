"""Level C/D routing and specialist referral."""

import pytest

from .conftest import ask, good_output, make_pipeline

EXACT = "ثُمَّ كَتَبَ مُلَخَّصًا قَصِيرًا فِي دَفْتَرِهِ الأَزْرَقِ"


@pytest.mark.parametrize("claim", [
    "أنا في دولة كذا، هل يجوز لي فعل هذا في زواجي؟",
    "طلقني زوجي، فهل يدل هذا النص على وقوع الطلاق؟",
    "أفتوني في حالتي",
])
def test_personal_cases_never_reach_llm(synthetic_db, claim):
    p = make_pipeline(synthetic_db, [good_output()])
    r = ask(p, EXACT, claim)
    ca = r.claim_analysis
    assert len(p.llm.calls) == 0
    assert ca.content_level == "D" and ca.relation == "REQUIRES_SPECIALIST" and ca.status == "REFERRED"
    assert ca.referral and ca.needs_specialist and ca.summary_source == "system_template"
    assert r.source is not None  # general information: the verified text is still shown


@pytest.mark.parametrize("model_relation", ["SUPPORTED", "OVERSTATED", "CONTRADICTED"])
def test_level_c_substantive_verdict_scoped(synthetic_db, model_relation):
    p = make_pipeline(synthetic_db, [good_output(model_relation)])
    r = ask(p, EXACT, "يدل النص على أن هذا الفعل واجب بإجماع العلماء")
    ca = r.claim_analysis
    assert len(p.llm.calls) == 1  # level C is analysed (scoped), no longer blocked
    assert ca.content_level == "C" and ca.level_policy == "SCOPED" and ca.relation == model_relation
    assert "LEVEL_C_SCOPED_TO_TEXT" in ca.safety_overrides and ca.referral
    assert "NO_STANDALONE_RULING" in ca.level_scope


def test_level_c_prompt_carries_guidance(synthetic_db):
    p = make_pipeline(synthetic_db, [good_output("REQUIRES_SPECIALIST")])
    ask(p, EXACT, "كل المسلمين يتفقون على معنى هذا النص")
    assert "CONTENT_LEVEL: C" in p.llm.calls[0]["user"] and "REQUIRES_SPECIALIST" in p.llm.calls[0]["user"]


def test_model_requested_specialist_is_referred(synthetic_db):
    p = make_pipeline(synthetic_db, [good_output("REQUIRES_SPECIALIST")])
    r = ask(p, EXACT, "النص يدل على معنى عميق يحتاج نظرا")
    assert r.claim_analysis.relation == "REQUIRES_SPECIALIST" and r.claim_analysis.referral


def test_level_b_verdict_passes_through(synthetic_db):
    p = make_pipeline(synthetic_db, [good_output("OVERSTATED")])
    r = ask(p, EXACT, "الطالب يكتب ملخصات في كل الكتب دائما")
    assert r.claim_analysis.content_level == "B" and r.claim_analysis.relation == "OVERSTATED"
