"""Build corpus embeddings and the FAISS index OFFLINE (never at app startup).

Only APPROVED, eligible Quran passages are embedded (the LSA baseline stays Quran-only; hadith
retrieval is BM25 only, see docs/METHODOLOGY.md). Writes to the index directory:
lsa_model.npz (local_lsa only), semantic.faiss, semantic_ids.json, semantic_meta.json.

usage: python scripts/build_embeddings.py [--db PATH] [--out DIR] [--provider local_lsa|hash]
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import faiss
import numpy as np
from _common import DEFAULT_DB, INDEX_DIR

from app.db.connection import connect
from app.repositories.corpus import CorpusRepository
from app.services.embeddings import HashEmbedding, LocalLSAEmbedding


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(INDEX_DIR))
    ap.add_argument("--provider", default="local_lsa", choices=["local_lsa", "hash"])
    ap.add_argument("--model", default="char-ngram-lsa-v1")
    ap.add_argument("--dim", type=int, default=256)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    conn = connect(Path(a.db), readonly=True)
    repo = CorpusRepository(conn)
    rows = conn.execute(
        """SELECT p.rowid_int, p.normalized_text FROM passages p JOIN sources s ON s.id = p.source_id
           WHERE s.verification_status = 'APPROVED' AND (s.source_type != 'synthetic_fixture' OR ?)
             AND s.source_type IN ('quran', 'synthetic_fixture')
           ORDER BY p.rowid_int""", (1 if repo.allow_synthetic else 0,)).fetchall()
    ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    if not texts:
        print("no eligible passages")
        return 1

    if a.provider == "local_lsa":
        dim = min(a.dim, len(texts) - 1)
        model = LocalLSAEmbedding.fit(texts, a.model, n_components=dim)
        model.save(out / "lsa_model.npz")
    else:
        model = HashEmbedding()
    vecs = model.embed(texts).astype("float32")
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, str(out / "semantic.faiss"))
    (out / "semantic_ids.json").write_text(json.dumps(ids), encoding="utf-8")
    meta = {
        "provider": model.provider,
        "model": model.model_name,
        "is_test_double": model.is_test_double,
        "dim": int(vecs.shape[1]),
        "count": len(ids),
        "faiss_index": "IndexFlatIP (exact inner product on L2-normalized vectors)",
        "faiss_version": faiss.__version__,
        "input_field": "passages.normalized_text",
        "corpus_version": repo.info.get("corpus_version"),
        "original_text_sha256": repo.info.get("original_text_sha256"),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "numpy": np.__version__,
    }
    (out / "semantic_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"embedded {len(ids)} passages with {model.provider}:{model.model_name} dim={vecs.shape[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
