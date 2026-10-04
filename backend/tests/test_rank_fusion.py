from app.services.rank_fusion import STRATEGIES, lexical_first, rrf
from app.services.types import Candidate, Passage


def P(i: str, seq: int = 0) -> Passage:
    return Passage(id=i, rowid=seq, source_id="s", reference=i, sequence=seq, parent_id=None,
                   original_text=i, normalized_text=i, normalized_text_alt=None, metadata={})


def lex(*ids):
    return [Candidate(passage=P(x, n), lexical_rank=n + 1, lexical_score=-1.0) for n, x in enumerate(ids)]


def sem(*ids):
    return [Candidate(passage=P(x, n), semantic_rank=n + 1, semantic_score=0.5) for n, x in enumerate(ids)]


def test_rrf_formula_and_dedup():
    out = rrf(lex("a", "b"), sem("b", "c"), k=60, top_n=10)
    scores = {c.passage.id: c.rrf_score for c in out}
    assert abs(scores["b"] - (1 / 62 + 1 / 61)) < 1e-12
    assert abs(scores["a"] - 1 / 61) < 1e-12
    assert len(out) == 3 and out[0].passage.id == "b"


def test_rrf_k_is_configurable():
    a = rrf(lex("a"), [], k=10)[0].rrf_score
    b = rrf(lex("a"), [], k=60)[0].rrf_score
    assert a == 1 / 11 and b == 1 / 61


def test_rrf_top_n():
    assert len(rrf(lex("a", "b", "c"), sem("d", "e"), top_n=2)) == 2


def test_exact_priority_overrides_score():
    out = rrf(lex("a", "b"), sem("a"), top_n=5, exact_ids={"b"})
    assert out[0].passage.id == "b" and out[0].exact_phrase


def test_lexical_only_equals_bm25_order():
    assert [c.passage.id for c in rrf(lex("x", "y", "z"), [])] == ["x", "y", "z"]


def test_lexical_first_never_displaces_bm25():
    out = lexical_first(lex("a", "b"), sem("c", "a", "d"), top_n=10)
    assert [c.passage.id for c in out] == ["a", "b", "c", "d"]
    assert out[0].rrf_score > 0  # scores still attached


def test_lexical_first_exact_first():
    out = lexical_first(lex("a", "b"), sem("c"), top_n=10, exact_ids={"b"})
    assert [c.passage.id for c in out][:2] == ["b", "a"]


def test_strategies_registry():
    assert set(STRATEGIES) == {"rrf", "lexical_first"}
