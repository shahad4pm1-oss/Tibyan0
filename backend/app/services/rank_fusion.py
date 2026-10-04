"""Reciprocal Rank Fusion.

score(d) = sum over lists L containing d of 1 / (k + rank_L(d)),  k = RRF_K (default 60).
No per-retriever weights are applied (no empirical basis for weights yet).

Exact canonical priority: candidates flagged `exact_phrase` (the whole normalized quote
occurs as a contiguous token phrase in the passage) are placed before all others,
keeping RRF order within each group. This is a deterministic rule, not a weight.
"""

from __future__ import annotations

from app.services.types import Candidate


def rrf(lexical: list[Candidate], semantic: list[Candidate], k: int = 60, top_n: int = 5,
        exact_ids: set[str] | None = None) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for c in lexical:
        m = merged.setdefault(c.passage.id, Candidate(passage=c.passage))
        m.lexical_rank, m.lexical_score = c.lexical_rank, c.lexical_score
        m.rrf_score += 1.0 / (k + c.lexical_rank)
    for c in semantic:
        m = merged.setdefault(c.passage.id, Candidate(passage=c.passage))
        m.semantic_rank, m.semantic_score = c.semantic_rank, c.semantic_score
        m.rrf_score += 1.0 / (k + c.semantic_rank)
    exact_ids = exact_ids or set()
    for pid, m in merged.items():
        m.exact_phrase = pid in exact_ids
    ranked = sorted(merged.values(), key=lambda c: (not c.exact_phrase, -c.rrf_score, c.passage.sequence))
    return ranked[:top_n]


def lexical_first(lexical: list[Candidate], semantic: list[Candidate], k: int = 60, top_n: int = 5,
                  exact_ids: set[str] | None = None) -> list[Candidate]:
    """Evidence-backed default (see eval/results/retrieval_comparison.json, docs/METHODOLOGY.md).

    Order: exact-phrase candidates first, then remaining BM25 candidates in BM25 order, then
    semantic-only candidates in semantic order (they widen the candidate pool, never displace a
    BM25 candidate). RRF scores are still computed and attached for transparency.
    """
    scored = {c.passage.id: c for c in rrf(lexical, semantic, k=k, top_n=10**6, exact_ids=exact_ids)}
    order: list[str] = []
    for c in lexical:
        if c.passage.id in (exact_ids or set()):
            order.append(c.passage.id)
    for c in lexical:
        if c.passage.id not in order:
            order.append(c.passage.id)
    for c in semantic:
        if c.passage.id not in order:
            order.append(c.passage.id)
    return [scored[i] for i in order][:top_n]


STRATEGIES = {"rrf": rrf, "lexical_first": lexical_first}
