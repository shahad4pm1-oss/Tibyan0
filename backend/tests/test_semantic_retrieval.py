"""Semantic retrieval.

- Synthetic tests use the HASH TEST DOUBLE (not a real model).
- Real-corpus tests use the REAL local LSA model built by scripts/build_embeddings.py.
"""

import json

import pytest

from app.services.embeddings import EmbeddingUnavailable, HashEmbedding, load_provider
from app.services.semantic_retriever import SemanticRetriever


def test_hash_double_is_deterministic_and_labelled():
    e = HashEmbedding()
    assert e.is_test_double
    a, b = e.embed(["ذهب الطالب"]), e.embed(["ذهب الطالب"])
    assert (a == b).all()


def test_hash_double_refused_in_production(tmp_path):
    with pytest.raises(EmbeddingUnavailable):
        load_provider("hash", None, tmp_path, "production")


def test_synthetic_semantic_test_double(synthetic_db, synthetic_repo):
    sr = SemanticRetriever(synthetic_repo, synthetic_db.parent, "hash", None, "test", 20)
    assert sr.available, sr.reason
    assert "TEST DOUBLE" in sr.model_label
    res = sr.search("قرأ كتابا عن البحار")
    assert res[0].passage.id == "synth:1:2"
    assert all(c.semantic_rank == i + 1 for i, c in enumerate(res))


def test_missing_index_is_unavailable_not_crash(synthetic_repo, tmp_path):
    sr = SemanticRetriever(synthetic_repo, tmp_path, "hash", None, "test", 20)
    assert not sr.available and "missing" in sr.reason


def test_stale_index_is_unavailable(synthetic_copy):
    from app.db.connection import connect
    from app.repositories.corpus import CorpusRepository
    meta_p = synthetic_copy.parent / "semantic_meta.json"
    m = json.loads(meta_p.read_text())
    m["original_text_sha256"] = "0" * 64
    meta_p.write_text(json.dumps(m))
    sr = SemanticRetriever(CorpusRepository(connect(synthetic_copy, readonly=True)), synthetic_copy.parent,
                           "hash", None, "test")
    assert not sr.available and "different corpus" in sr.reason


@pytest.mark.real_corpus
def test_real_model_loaded(real_db, real_repo):
    sr = SemanticRetriever(real_repo, real_db.parent, "local_lsa", "char-ngram-lsa-v1", "test", 20)
    assert sr.available, sr.reason
    assert sr.provider.is_test_double is False


@pytest.mark.real_corpus
@pytest.mark.parametrize("pid", ["quran:2:191", "quran:18:110", "quran:24:35"])
def test_real_non_exact_query_retrieves_correct_passage(real_db, real_repo, pid):
    """Non-exact query (two words dropped) must retrieve the right passage in the top 5."""
    sr = SemanticRetriever(real_repo, real_db.parent, "local_lsa", "char-ngram-lsa-v1", "test", 20)
    w = real_repo.get(pid).metadata["publisher_aya_text_emlaey"].split()[:12]
    q = " ".join(w[:3] + w[4:7] + w[8:])
    assert pid in [c.passage.id for c in sr.search(q)[:5]]
