"""Multi-source retrieval: separate indexes, Quran first, hadith second, Quran results unchanged."""

import pytest

from tests.conftest import ask, make_pipeline

pytestmark = pytest.mark.real_corpus
LSA = {"embedding_provider": "local_lsa", "embedding_model": "char-ngram-lsa-v1"}


@pytest.fixture(scope="module")
def pipe(real_db):
    return make_pipeline(real_db, script=[], **LSA)


def test_indexes_are_separate(real_repo):
    c = real_repo.conn
    assert c.execute("SELECT count(*) FROM passages_fts").fetchone()[0] == 6236     # Quran index unchanged
    assert c.execute("SELECT count(*) FROM hadith_fts").fetchone()[0] == 10494
    q_rowids = {r[0] for r in c.execute("SELECT rowid_int FROM passages WHERE source_id='quran'")}
    assert {r[0] for r in c.execute("SELECT rowid FROM passages_fts")} == q_rowids


def test_quran_quote_resolves_to_quran_without_hadith_search(pipe, real_repo):
    q = real_repo.get("quran:1:2").metadata["publisher_aya_text_emlaey"]
    r = ask(pipe, q, "ادعاء")
    assert r.source.source_id == "quran" and r.sources_searched == ["quran"]


def test_hadith_quote_resolves_to_hadith(pipe, real_repo):
    words = real_repo.get("hadith:bukhari:7563").normalized_text.split()
    r = ask(pipe, " ".join(words[-14:]), "ادعاء")
    assert r.sources_searched == ["quran", "hadith"]
    assert r.source.source_type == "hadith" and r.source.source_id == "hadith:bukhari"
    assert r.quote_analysis.match_status == "PARTIAL"
    assert r.context.matched[0].passage_id == "hadith:bukhari:7563"


def test_text_repeated_across_hadith_is_not_attributed_to_one(pipe):
    r = ask(pipe, "سبحان الله وبحمده سبحان الله العظيم", "ادعاء")
    qa = r.quote_analysis
    assert r.source is None and qa.match_status == "AMBIGUOUS" and qa.ambiguity_reason == "MULTIPLE_LOCATIONS"
    assert all(a.source_type == "hadith" for a in qa.alternatives) and qa.alternatives_total >= 2


def test_unknown_saying_is_not_found(pipe):
    r = ask(pipe, "اطلبوا العلم ولو بالصين", "هذا حديث صحيح")
    assert r.quote_analysis.match_status == "NOT_FOUND" and r.source is None
    assert r.claim_analysis.relation == "INSUFFICIENT_EVIDENCE"


def test_near_hadith_is_never_confirmed(pipe, real_repo):
    words = real_repo.get("hadith:muslim:1907").normalized_text.split()[10:22]
    words[5] = "المدينة"
    r = ask(pipe, " ".join(words), "ادعاء")
    assert r.source is None and r.quote_analysis.match_status in ("AMBIGUOUS", "NOT_FOUND")
    if r.quote_analysis.match_status == "AMBIGUOUS":
        assert r.quote_analysis.ambiguity_reason == "NEAR_MATCH_UNCONFIRMED"
