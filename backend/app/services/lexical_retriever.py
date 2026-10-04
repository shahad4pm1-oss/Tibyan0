from __future__ import annotations

from app.repositories.corpus import CorpusRepository
from app.services.normalizer import tokens
from app.services.types import Candidate


class LexicalRetriever:
    """quote -> normalize_for_search -> FTS5/BM25 (OR over tokens, both search columns) -> top k."""

    def __init__(self, repo: CorpusRepository, k: int = 20, tokenize=tokens):
        self.repo = repo
        self.k = k
        self.tokenize = tokenize

    def search(self, quote: str, k: int | None = None) -> list[Candidate]:
        toks = self.tokenize(quote)
        hits = self.repo.bm25(toks, k or self.k)
        return [Candidate(passage=p, lexical_rank=i + 1, lexical_score=s) for i, (p, s) in enumerate(hits)]
