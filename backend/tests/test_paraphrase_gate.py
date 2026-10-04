"""An uncalibrated (non-exact, semantic or fuzzy) match can never create a confident attribution.

PARAPHRASED stays in the schema as reserved/experimental. With the default PARAPHRASE_MODE=disabled,
and always in production, a non-exact match resolves to AMBIGUOUS (closest passages listed, nothing
attributed) or NOT_FOUND.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.lexical_retriever import LexicalRetriever
from app.services.quote_matcher import QuoteMatcher
from app.services.rank_fusion import lexical_first
from app.services.source_resolver import SourceResolver
from app.services.types import Candidate, MatchStatus, ResolutionStatus, SearchMode  # noqa: F401

NEAR = "لعب الاطفال بالكرة قرب النهر"  # one word differs from synth:2:2 (synthetic, non-religious)


def test_enum_still_exists():
    assert MatchStatus.PARAPHRASED.value == "PARAPHRASED"


def test_default_settings_disable_paraphrase():
    assert Settings().paraphrase_mode == "disabled"
    import inspect
    assert inspect.signature(QuoteMatcher.__init__).parameters["paraphrase_mode"].default == "disabled"


def test_unknown_mode_rejected(synthetic_repo):
    with pytest.raises(ValueError):
        QuoteMatcher(synthetic_repo, paraphrase_mode="on")


def test_top_semantic_score_cannot_create_attribution(synthetic_repo):
    """A candidate ranked first by semantic retrieval with a near-perfect score, but whose text does
    not contain the quote, must not be attributed."""
    target = synthetic_repo.get("synth:2:2")
    fake_semantic = [Candidate(passage=target, semantic_rank=1, semantic_score=0.999)]
    m = QuoteMatcher(synthetic_repo).match(NEAR, lexical_first([], fake_semantic, top_n=10))
    assert m.status is not MatchStatus.PARAPHRASED and m.passages == []
    unrelated = "اشترى المهندس حاسوبا جديدا للمختبر"
    m2 = QuoteMatcher(synthetic_repo).match(unrelated, lexical_first([], fake_semantic, top_n=10))
    assert m2.status is MatchStatus.NOT_FOUND


def test_near_match_does_not_resolve_a_source(synthetic_repo):
    cands = lexical_first(LexicalRetriever(synthetic_repo).search(NEAR), [], top_n=10)
    m = QuoteMatcher(synthetic_repo).match(NEAR, cands)
    r = SourceResolver(synthetic_repo).resolve(m)
    assert r.status is ResolutionStatus.AMBIGUOUS and r.passages == [] and r.source is None


def test_production_refuses_experimental_mode(synthetic_as_production):
    db = synthetic_as_production
    s = Settings(app_env="production", database_path=str(db), paraphrase_mode="experimental",
                 embedding_provider="none")
    p = AnalysisPipeline(s, db.parent)
    assert p.paraphrase_mode == "disabled" and p.matcher.paraphrase_mode == "disabled"


def test_api_never_returns_paraphrased_by_default(monkeypatch, synthetic_db):
    monkeypatch.setenv("DATABASE_PATH", str(synthetic_db))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("EMBEDDING_MODEL", "")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            j = c.post("/api/v1/analyze", json={"quote": NEAR, "claim": "ادعاء"}).json()
    finally:
        get_settings.cache_clear()
    assert j["quote_analysis"]["match_status"] == "AMBIGUOUS"
    assert j["quote_analysis"]["ambiguity_reason"] == "NEAR_MATCH_UNCONFIRMED"
    assert j["status"] == "AMBIGUOUS_SOURCE" and j["source"] is None and j["evidence"]["items"] == []
    assert "synth:2:2" in {u["passage_id"] for u in j["quote_analysis"]["alternatives"]}
    assert j["metadata"]["paraphrase_mode"] == "disabled"


@pytest.mark.real_corpus
def test_real_corpus_misquotes_never_attributed(real_repo):
    """Across many real one-word misquotes, the default matcher never emits PARAPHRASED or a source."""
    m = QuoteMatcher(real_repo)
    lr = LexicalRetriever(real_repo)
    for pid in ("quran:2:191", "quran:4:58", "quran:18:110", "quran:24:35", "quran:49:13", "quran:3:7"):
        w = real_repo.get(pid).metadata["publisher_aya_text_emlaey"].split()[:9]
        w[4] = "الكتاب" if w[4] != "الكتاب" else "الناس"
        q = " ".join(w)
        res = m.match(q, lexical_first(lr.search(q), [], top_n=10))
        assert res.status is not MatchStatus.PARAPHRASED and res.passages == []
