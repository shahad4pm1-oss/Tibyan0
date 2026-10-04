"""Semantic (dense vector) retrieval over a FAISS index built OFFLINE.

Artifacts in the index directory (written by scripts/build_embeddings.py):
  semantic.faiss        FAISS IndexFlatIP over L2-normalized vectors
  semantic_ids.json     FAISS row -> passages.rowid_int
  semantic_meta.json    provider, model, dim, corpus original_text_sha256, counts
If anything is missing or stale, the retriever reports itself unavailable and the
pipeline runs LEXICAL_ONLY (degraded mode).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.repositories.corpus import CorpusRepository
from app.services.embeddings import EmbeddingProvider, EmbeddingUnavailable, load_provider
from app.services.normalizer import normalize_for_search
from app.services.types import Candidate


class SemanticRetriever:
    def __init__(self, repo: CorpusRepository, index_dir: Path, provider: str | None, model: str | None,
                 app_env: str, k: int = 20):
        self.repo = repo
        self.k = k
        self.available = False
        self.reason: str | None = None
        self.provider: EmbeddingProvider | None = None
        self.meta: dict = {}
        try:
            import faiss

            index_dir = Path(index_dir)
            meta_p, ids_p, idx_p = (index_dir / n for n in ("semantic_meta.json", "semantic_ids.json", "semantic.faiss"))
            for p in (meta_p, ids_p, idx_p):
                if not p.exists():
                    raise EmbeddingUnavailable(f"missing {p.name}")
            self.meta = json.loads(meta_p.read_text(encoding="utf-8"))
            if self.meta.get("original_text_sha256") != repo.info.get("original_text_sha256"):
                raise EmbeddingUnavailable("semantic index was built for a different corpus")
            if self.meta.get("provider") != provider:
                raise EmbeddingUnavailable(f"index built with {self.meta.get('provider')}, configured {provider}")
            self.provider = load_provider(provider, model, index_dir, app_env)
            self._ids: list[int] = json.loads(ids_p.read_text(encoding="utf-8"))
            self._index = faiss.read_index(str(idx_p))
            if self._index.ntotal != len(self._ids) or self._index.d != self.provider.dim:
                raise EmbeddingUnavailable("index/id map/dimension mismatch")
            self.available = True
        except Exception as e:  # noqa: BLE001 - any failure means degraded mode, never a crash
            self.reason = f"{type(e).__name__}: {e}"

    @property
    def model_label(self) -> str | None:
        if not self.available or not self.provider:
            return None
        return f"{self.provider.provider}:{self.provider.model_name}" + (" (TEST DOUBLE)" if self.provider.is_test_double else "")

    def search(self, quote: str, k: int | None = None) -> list[Candidate]:
        if not self.available:
            raise EmbeddingUnavailable(self.reason or "semantic retrieval unavailable")
        q = normalize_for_search(quote)
        vec = self.provider.embed([q])
        scores, rows = self._index.search(np.asarray(vec, dtype="float32"), k or self.k)
        rowids = [self._ids[r] for r in rows[0] if r >= 0]
        found = self.repo.by_rowids(rowids)  # re-applies APPROVED filter
        out: list[Candidate] = []
        for s, r in zip(scores[0], rows[0]):
            if r < 0:
                continue
            p = found.get(self._ids[r])
            if p is None:
                continue
            out.append(Candidate(passage=p, semantic_rank=len(out) + 1, semantic_score=float(s)))
        return out
