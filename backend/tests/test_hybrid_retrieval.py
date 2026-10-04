import pytest

from app.services.lexical_retriever import LexicalRetriever
from app.services.normalizer import tokens
from app.services.rank_fusion import lexical_first, rrf
from app.services.semantic_retriever import SemanticRetriever


def test_hybrid_synthetic(synthetic_db, synthetic_repo):
    lr = LexicalRetriever(synthetic_repo, 20)
    sr = SemanticRetriever(synthetic_repo, synthetic_db.parent, "hash", None, "test", 20)  # TEST DOUBLE
    q = "جلس الاب تحت الشجرة"
    for fuse in (rrf, lexical_first):
        out = fuse(lr.search(q), sr.search(q), k=60, top_n=5)
        assert out[0].passage.id == "synth:2:3"
        assert len({c.passage.id for c in out}) == len(out)  # deduplicated
        assert len(out) <= 5


@pytest.mark.real_corpus
def test_hybrid_real(real_db, real_repo):
    lr = LexicalRetriever(real_repo, 20)
    sr = SemanticRetriever(real_repo, real_db.parent, "local_lsa", "char-ngram-lsa-v1", "test", 20)
    w = real_repo.get("quran:4:58").metadata["publisher_aya_text_emlaey"].split()
    q = " ".join(w[1:9])
    exact = {p.id for p in real_repo.phrase_hits(tokens(q))}
    out = lexical_first(lr.search(q), sr.search(q), top_n=5, exact_ids=exact)
    assert out[0].passage.id == "quran:4:58" and out[0].exact_phrase
