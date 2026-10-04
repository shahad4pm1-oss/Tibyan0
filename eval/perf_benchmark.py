"""Per-stage latency benchmark of the no-LLM pipeline on the production corpus (Phase 4).

Queries are taken from the verified corpus (seeded sample of ayat: full imla'i text, a 4-word excerpt, and a
non-Quran sentence), never typed. Each stage is timed in isolation; the full request is timed through the
FastAPI app in-process (TestClient, no network). Writes eval/results/performance.json.

usage: backend/.venv/bin/python eval/perf_benchmark.py [--n 300] [--seed 4242]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")
for k in ("LLM_PROVIDER", "LLM_API_KEY"):
    os.environ.pop(k, None)

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import normalizer
from app.services.analysis_pipeline import STRATEGIES, AnalysisPipeline
from app.services.source_resolver import ResolutionStatus

NOT_QURAN = ["من جد وجد ومن زرع حصد", "العلم في الصغر كالنقش على الحجر", "الوقت كالسيف ان لم تقطعه قطعك"]


def summarize(xs: list[float]) -> dict:
    xs = sorted(xs)
    p95 = xs[min(len(xs) - 1, round(0.95 * (len(xs) - 1)))]
    return {"n": len(xs), "avg_ms": round(statistics.fmean(xs), 3), "p50_ms": round(statistics.median(xs), 3),
            "p95_ms": round(p95, 3), "max_ms": round(xs[-1], 3)}


def timed(fn, *a, **kw):
    t = time.perf_counter()
    out = fn(*a, **kw)
    return out, (time.perf_counter() - t) * 1000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=4242)
    args = ap.parse_args()

    s = Settings(database_path=str(ROOT / "data/indexes/tibyan.sqlite3"))
    p = AnalysisPipeline(s, ROOT, provider=None)
    rng = random.Random(args.seed)
    ids = [r[0] for r in p.repo.conn.execute("SELECT id FROM passages WHERE source_id='quran' ORDER BY id")]
    queries = []
    for pid in rng.sample(ids, args.n):
        words = p.repo.get(pid).metadata["publisher_aya_text_emlaey"].split()
        queries.append(" ".join(words) if rng.random() < 0.5 else " ".join(words[:4]))
    queries += [rng.choice(NOT_QURAN) for _ in range(max(1, args.n // 10))]

    # warm-up
    for q in queries[:10]:
        p.lexical.search(q)
        if p.semantic.available:
            p.semantic.search(q)

    st: dict[str, list[float]] = {k: [] for k in ("db_lookup", "bm25_search", "semantic_search", "hybrid_fusion_and_match",
                                                  "context_expansion", "pipeline_no_llm")}
    for q in queries:
        lex, ms = timed(p.lexical.search, q)
        st["bm25_search"].append(ms)
        sem = []
        if p.semantic.available:
            sem, ms = timed(p.semantic.search, q)
            st["semantic_search"].append(ms)

        def fuse_match(q=q, lex=lex, sem=sem):
            exact = {x.id for x in p.repo.phrase_hits(normalizer.tokens(q))}
            fused = STRATEGIES[s.hybrid_strategy](lex, sem, k=s.rrf_k, top_n=max(s.hybrid_top_n, 10), exact_ids=exact)
            return p.resolver.resolve(p.matcher.match(q, fused))
        res, ms = timed(fuse_match)
        st["hybrid_fusion_and_match"].append(ms)
        if res.status is ResolutionStatus.RESOLVED:
            _, ms = timed(p.expander.expand, res.passages, res.source)
            st["context_expansion"].append(ms)
        _, ms = timed(p.repo.get, rng.choice(ids))
        st["db_lookup"].append(ms)

    from app.schemas.analyze import AnalyzeRequest
    for q in queries:
        _, ms = timed(p.analyze, AnalyzeRequest(quote=q, claim="هذا النص من القرآن"))
        st["pipeline_no_llm"].append(ms)

    client = TestClient(create_app())
    http: list[float] = []
    with client:
        for q in queries:
            r, ms = timed(client.post, "/api/v1/analyze", json={"quote": q, "claim": "هذا النص من القرآن"})
            assert r.status_code == 200, r.status_code
            http.append(ms)
    st["full_request_no_llm_http_inprocess"] = http

    out = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": args.seed, "queries": len(queries),
        "query_mix": "50% full ayah (imla'i), 50% first 4 words, plus ~10% non-Quran sentences; sampled from the corpus",
        "environment": {"python": platform.python_version(), "machine": platform.machine(),
                        "cpu_count": str(os.cpu_count()), "note": "development container, single process; not a "
                        "production host measurement", "corpus_version": p.corpus_version,
                        "semantic_index": p.semantic.model_label if p.semantic.available else "unavailable",
                        "llm": "not configured (no LLM time included)"},
        "stages": {k: summarize(v) for k, v in st.items() if v},
    }
    dst = ROOT / "eval/results/performance.json"
    dst.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for k, v in out["stages"].items():
        print(f"{k:38s} n={v['n']:4d} avg={v['avg_ms']:8.2f} p50={v['p50_ms']:8.2f} p95={v['p95_ms']:8.2f} ms")
    print(f"wrote {dst.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
