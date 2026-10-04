"""Embedding providers behind one interface.

Providers (selected by EMBEDDING_PROVIDER / EMBEDDING_MODEL):

- local_lsa  REAL, local, classical model: character n-gram TF-IDF (char_wb 2-4) + truncated
             SVD (LSA), fitted OFFLINE on the approved corpus's normalized search text.
             It is not a neural sentence-embedding model; it captures surface/orthographic
             similarity, not deep paraphrase. Persisted without pickle (npz).
- sentence_transformers  Adapter for a neural model. WRITTEN BUT NOT RUNTIME-VERIFIED:
             the build environment cannot download model weights.
- hash       TEST DOUBLE ONLY: deterministic hashed character trigrams. Refused in production.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

import numpy as np


class EmbeddingProvider(Protocol):
    provider: str
    model_name: str
    is_test_double: bool

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _l2(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (x / n).astype("float32")


class HashEmbedding:
    provider = "hash"
    is_test_double = True

    def __init__(self, dim: int = 64):
        self._dim = dim
        self.model_name = f"hash-trigram-{dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self._dim), dtype="float32")
        for i, t in enumerate(texts):
            s = f"  {t}  "
            for j in range(len(s) - 2):
                h = int.from_bytes(hashlib.blake2b(s[j:j + 3].encode(), digest_size=4).digest(), "little")
                out[i, h % self._dim] += 1.0
        return _l2(out)


class LocalLSAEmbedding:
    provider = "local_lsa"
    is_test_double = False
    ANALYZER = "char_wb"
    NGRAM = (2, 4)

    def __init__(self, model_name: str, vocab: dict[str, int], idf: np.ndarray, components: np.ndarray):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.model_name = model_name
        self._vec = TfidfVectorizer(analyzer=self.ANALYZER, ngram_range=self.NGRAM, sublinear_tf=True,
                                    vocabulary=vocab, dtype=np.float32)
        self._vec.idf_ = idf
        self._components = components.astype("float32")

    @property
    def dim(self) -> int:
        return self._components.shape[0]

    @classmethod
    def fit(cls, texts: list[str], model_name: str, n_components: int = 256, seed: int = 0) -> LocalLSAEmbedding:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(analyzer=cls.ANALYZER, ngram_range=cls.NGRAM, sublinear_tf=True, min_df=2,
                              dtype=np.float32)
        x = vec.fit_transform(texts)
        svd = TruncatedSVD(n_components=n_components, random_state=seed, algorithm="randomized", n_iter=7)
        svd.fit(x)
        vocab = {k: int(v) for k, v in vec.vocabulary_.items()}
        return cls(model_name, vocab, vec.idf_.astype("float32"), svd.components_)

    def embed(self, texts: list[str]) -> np.ndarray:
        x = self._vec.transform(texts)
        return _l2(np.asarray(x @ self._components.T))

    def save(self, path: Path) -> None:
        terms = sorted(self._vec.vocabulary, key=self._vec.vocabulary.get)
        np.savez_compressed(path, terms=np.array(terms, dtype=object).astype(str), idf=self._vec.idf_,
                            components=self._components,
                            config=np.array(json.dumps({"model_name": self.model_name, "analyzer": self.ANALYZER,
                                                        "ngram": list(self.NGRAM)})))

    @classmethod
    def load(cls, path: Path) -> LocalLSAEmbedding:
        z = np.load(path, allow_pickle=False)
        cfg = json.loads(str(z["config"]))
        vocab = {t: i for i, t in enumerate(z["terms"].tolist())}
        return cls(cfg["model_name"], vocab, z["idf"], z["components"])


class SentenceTransformersEmbedding:  # pragma: no cover - not runtime-verified
    provider = "sentence_transformers"
    is_test_double = False

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # optional dependency

        self.model_name = model_name
        self._m = SentenceTransformer(model_name)

    @property
    def dim(self) -> int:
        return int(self._m.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        return _l2(np.asarray(self._m.encode(texts, normalize_embeddings=True)))


class EmbeddingUnavailable(RuntimeError):
    pass


def load_provider(provider: str | None, model: str | None, index_dir: Path, app_env: str) -> EmbeddingProvider:
    """Load a provider for QUERY time. Never fits a model at application startup."""
    if provider in (None, "", "none"):
        raise EmbeddingUnavailable("no embedding provider configured")
    if provider == "hash":
        if app_env == "production":
            raise EmbeddingUnavailable("hash test double is refused in production")
        return HashEmbedding()
    if provider == "local_lsa":
        p = Path(index_dir) / "lsa_model.npz"
        if not p.exists():
            raise EmbeddingUnavailable(f"model file missing: {p.name} (run scripts/build_embeddings.py)")
        m = LocalLSAEmbedding.load(p)
        if model and m.model_name != model:
            raise EmbeddingUnavailable(f"model mismatch: configured {model}, built {m.model_name}")
        return m
    if provider == "sentence_transformers":
        try:
            return SentenceTransformersEmbedding(model or "")
        except Exception as e:
            raise EmbeddingUnavailable(f"sentence_transformers unavailable: {type(e).__name__}") from e
    raise EmbeddingUnavailable(f"unknown provider {provider!r}")
