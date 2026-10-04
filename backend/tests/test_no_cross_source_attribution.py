"""No attribution across sources: spans never cross sources or hadith; AI text never becomes source text."""

import pytest

from app.services.analysis_pipeline import AnalysisPipeline
from tests.conftest import ask, make_pipeline

pytestmark = pytest.mark.real_corpus


def test_hadith_matcher_never_spans(real_db):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    assert p.matcher_hadith.max_span == 1


def test_quote_joining_two_hadith_is_not_attributed(real_db, real_repo):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    a = real_repo.get("hadith:bukhari:1").normalized_text.split()[-5:]
    b = real_repo.get("hadith:bukhari:2").normalized_text.split()[:5]
    r = ask(p, " ".join(a + b), "ادعاء")
    assert r.source is None


def test_quote_joining_quran_and_hadith_is_not_attributed(real_db, real_repo):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    a = real_repo.get("quran:114:6").metadata["publisher_aya_text_emlaey"].split()
    b = real_repo.get("hadith:bukhari:1").normalized_text.split()[:5]
    r = ask(p, " ".join(a + b), "ادعاء")
    assert r.source is None


def test_hadith_result_has_no_ai_text(real_db, real_repo):
    p = make_pipeline(real_db, script=[], embedding_provider="local_lsa", embedding_model="char-ngram-lsa-v1")
    r = ask(p, " ".join(real_repo.get("hadith:bukhari:1").normalized_text.split()[-10:]), "ادعاء")
    ca = r.claim_analysis
    assert ca.summary_source == "system_template" and ca.reason is None and ca.key_evidence == []
    # every displayed religious text is read from the corpus
    for u in r.context.matched:
        assert u.text == real_repo.get(u.passage_id).original_text


def test_pipeline_limitations_state_coverage_honestly():
    from app.services.analysis_pipeline import LIMITATIONS
    joined = " ".join(LIMITATIONS)
    assert "Tafsir" in joined and "not ingested" in joined and "Muslim 1-99" in joined
    assert isinstance(AnalysisPipeline, type)
