"""AI text cannot carry religious text that is not in the cited evidence.
Real-corpus cases read all Quran text from the database (never typed)."""

import pytest

from app.schemas.claim_analysis import LLMClaimOutput
from app.services.context_expander import ContextExpander
from app.services.evidence_builder import EvidenceBuilder
from app.services.grounding_verifier import GroundingVerifier

from .conftest import good_output


def evidence_for(repo, pid, src):
    return EvidenceBuilder().build(ContextExpander(repo, 2).expand([repo.get(pid)], repo.source(src)), repo.source(src))


def check(repo, ev, quote="q", claim="c", **over):
    return GroundingVerifier(repo).verify(LLMClaimOutput.model_validate(good_output(**over)), ev, quote, claim)


def test_quote_from_cited_evidence_allowed(synthetic_repo):
    ev = evidence_for(synthetic_repo, "synth:1:3", "synth")
    assert check(synthetic_repo, ev, reason="E1 يقول «ملخصا قصيرا في دفتره».") == []


def test_quote_not_in_cited_evidence_rejected(synthetic_repo):
    ev = evidence_for(synthetic_repo, "synth:1:3", "synth")
    assert "UNSUPPORTED_QUOTATION" in check(synthetic_repo, ev, reason="E1 يقول «ملخصا طويلا جدا».")


def test_quote_of_uncited_supplied_evidence_rejected(synthetic_repo):
    ev = evidence_for(synthetic_repo, "synth:1:3", "synth")  # E2 = synth:1:1 supplied but not cited
    assert "UNSUPPORTED_QUOTATION" in check(synthetic_repo, ev, reason="E1 مثل «ذهب الطالب الى المكتبة».")


def test_quoting_the_users_own_words_allowed(synthetic_repo):
    ev = evidence_for(synthetic_repo, "synth:1:3", "synth")
    assert check(synthetic_repo, ev, claim="الطالب كتب ملخصا طويلا", reason="الادعاء «كتب ملخصا طويلا» لا يرد في E1.") == []


def test_scripture_formatting_rejected(synthetic_repo):
    ev = evidence_for(synthetic_repo, "synth:1:3", "synth")
    assert "SCRIPTURE_FORMATTED_TEXT" in check(synthetic_repo, ev, summary="نص بخط ٱلرسم")


@pytest.mark.real_corpus
def test_real_other_ayah_from_memory_rejected(real_repo):
    ev = evidence_for(real_repo, "quran:2:191", "quran")
    other = real_repo.get("quran:9:5").metadata["publisher_aya_text_emlaey"]  # read from DB
    issues = check(real_repo, ev, reason="E1 وكذلك قوله " + " ".join(other.split()[:7]))
    assert "UNSUPPORTED_SCRIPTURE" in issues


@pytest.mark.real_corpus
def test_real_quoting_cited_ayah_without_marks_allowed(real_repo):
    ev = evidence_for(real_repo, "quran:2:191", "quran")
    frag = " ".join(real_repo.get("quran:2:190").metadata["publisher_aya_text_emlaey"].split()[:5])
    assert check(real_repo, ev, ids=("E3",), reason=f"E3 يقول «{frag}».") == []  # E3 = 2:190
