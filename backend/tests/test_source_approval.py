"""No ACTIVE production result can originate from PENDING_REVIEW or REJECTED sources."""

import pytest

from app.corpus.fts import build_fts
from app.db.connection import connect
from app.repositories.corpus import CorpusRepository
from app.services.lexical_retriever import LexicalRetriever
from app.services.semantic_retriever import SemanticRetriever

PENDING_Q = "القطارات البرتقالية"
REJECTED_Q = "الطائرات البنفسجية"


def ineligible_ids(repo):
    return {r[0] for r in repo.conn.execute(
        "SELECT p.id FROM passages p JOIN sources s ON s.id=p.source_id WHERE s.verification_status != 'APPROVED'")}


def test_fixture_really_contains_ineligible_rows(synthetic_repo):
    assert len(ineligible_ids(synthetic_repo)) == 2


def test_not_in_fts_index(synthetic_repo):
    bad_rowids = {r[0] for r in synthetic_repo.conn.execute(
        "SELECT p.rowid_int FROM passages p JOIN sources s ON s.id=p.source_id WHERE s.verification_status!='APPROVED'")}
    indexed = {r[0] for r in synthetic_repo.conn.execute("SELECT rowid FROM passages_fts")}
    assert not (bad_rowids & indexed)


@pytest.mark.parametrize("q", [PENDING_Q, REJECTED_Q])
def test_lexical_never_returns_ineligible(synthetic_repo, q):
    got = {c.passage.id for c in LexicalRetriever(synthetic_repo, 50).search(q)}
    assert not (got & ineligible_ids(synthetic_repo))


@pytest.mark.parametrize("q", [PENDING_Q, REJECTED_Q])
def test_semantic_never_returns_ineligible(synthetic_db, synthetic_repo, q):
    sr = SemanticRetriever(synthetic_repo, synthetic_db.parent, "hash", None, "test", 50)
    got = {c.passage.id for c in sr.search(q)}
    assert not (got & ineligible_ids(synthetic_repo))


def test_repository_guard_even_if_index_is_polluted(synthetic_copy):
    """Defense in depth: force ineligible rows INTO the FTS index; queries must still filter them."""
    c = connect(synthetic_copy)
    c.execute("""INSERT INTO passages_fts (rowid, normalized_text, normalized_text_alt)
                 SELECT p.rowid_int, p.normalized_text, '' FROM passages p JOIN sources s ON s.id=p.source_id
                 WHERE s.verification_status != 'APPROVED'""")
    c.commit()
    repo = CorpusRepository(connect(synthetic_copy, readonly=True))
    for q in (PENDING_Q, REJECTED_Q):
        assert not ({c.passage.id for c in LexicalRetriever(repo, 50).search(q)} & ineligible_ids(repo))
        assert not ({p.id for p in repo.phrase_hits(q.split())} & ineligible_ids(repo))
    for pid in ineligible_ids(repo):
        assert repo.get(pid) is None


def test_status_change_removes_from_results(synthetic_copy):
    c = connect(synthetic_copy)
    c.execute("UPDATE sources SET verification_status='PENDING_REVIEW' WHERE id='synth'")
    build_fts(c, production=False)
    c.commit()
    repo = CorpusRepository(connect(synthetic_copy, readonly=True))
    assert all(not c.passage.id.startswith("synth:") for c in LexicalRetriever(repo, 50).search("المكتبة"))


def test_synthetic_never_in_production_index(synthetic_copy):
    c = connect(synthetic_copy)
    n = build_fts(c, production=True)
    assert n == 0  # synthetic fixtures are excluded from any production index


@pytest.mark.real_corpus
def test_api_results_only_from_approved(real_repo):
    statuses = {r[0] for r in real_repo.conn.execute("SELECT verification_status FROM sources")}
    assert statuses == {"APPROVED"}
