"""Choosing between Quran and hadith results (deterministic priority rule)."""

import pytest

from app.services.analysis_pipeline import _strength_rank
from app.services.source_resolver import Resolution
from app.services.types import AmbiguityReason, MatchStatus, QuoteMatch, ResolutionStatus
from tests.conftest import ask, make_pipeline


def _m(status, reason=None, cov=1.0):
    return QuoteMatch(status=status, method="x", reason=reason, coverage=cov)


def test_strength_order():
    resolved = (_m(MatchStatus.PARTIAL), Resolution(ResolutionStatus.RESOLVED))
    verbatim_many = (_m(MatchStatus.AMBIGUOUS, AmbiguityReason.MULTIPLE_LOCATIONS), Resolution(ResolutionStatus.AMBIGUOUS))
    near = (_m(MatchStatus.AMBIGUOUS, AmbiguityReason.NEAR_MATCH_UNCONFIRMED, 0.7), Resolution(ResolutionStatus.AMBIGUOUS))
    none = (_m(MatchStatus.NOT_FOUND), Resolution(ResolutionStatus.NOT_FOUND))
    ranks = [_strength_rank(*x) for x in (resolved, verbatim_many, near, none)]
    assert ranks == sorted(ranks, reverse=True) and len(set(ranks)) == 4


@pytest.mark.real_corpus
def test_quran_text_quoted_inside_a_hadith_stays_quran(real_db, real_repo):
    """Hadith often quote ayat verbatim; such a quote is attributed to the Quran, never to the hadith."""
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    q = real_repo.get("quran:9:80").metadata["publisher_aya_text_emlaey"].split()[:10]
    r = ask(p, " ".join(q), "ادعاء")
    assert r.source.source_type == "quran" and r.sources_searched == ["quran"]


@pytest.mark.real_corpus
def test_personal_fatwa_with_hadith_still_routes_to_specialist(real_db, real_repo):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    words = real_repo.get("hadith:bukhari:1").normalized_text.split()[-12:]
    r = ask(p, " ".join(words), "هل يجوز لي أن أطلق زوجتي بهذه النية؟")
    assert r.claim_analysis.relation == "REQUIRES_SPECIALIST" and r.claim_analysis.status == "REFERRED"
    assert r.claim_analysis.attempts == 0
