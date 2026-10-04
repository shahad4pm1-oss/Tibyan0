"""Small load test against a RUNNING backend (Phase 4). Not a capacity claim for any production host.

Start the server with the rate limit disabled for the run, e.g.
  RATE_LIMIT_PER_MINUTE=0 backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000
then:  backend/.venv/bin/python eval/load_test.py --url http://127.0.0.1:8000 --pid <uvicorn pid>

Queries are sampled from the corpus DB (never typed). Writes eval/results/load_test.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sqlite3
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def rss_mb(pid: int | None) -> float | None:
    if not pid:
        return None
    for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)
    return None


async def run(url: str, queries: list[str], concurrency: int) -> tuple[list[float], dict[int, int], float]:
    sem = asyncio.Semaphore(concurrency)
    lat: list[float] = []
    codes: dict[int, int] = {}
    async with httpx.AsyncClient(base_url=url, timeout=60) as c:
        async def one(q: str):
            async with sem:
                t = time.perf_counter()
                try:
                    r = await c.post("/api/v1/analyze", json={"quote": q, "claim": "هذا النص من القرآن"})
                    code = r.status_code
                except httpx.HTTPError:
                    code = 0
                lat.append((time.perf_counter() - t) * 1000)
                codes[code] = codes.get(code, 0) + 1
        t0 = time.perf_counter()
        await asyncio.gather(*(one(q) for q in queries))
        wall = time.perf_counter() - t0
    return lat, codes, wall


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--requests", type=int, default=400)
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 10, 25])
    ap.add_argument("--seed", type=int, default=99)
    args = ap.parse_args()

    con = sqlite3.connect((ROOT / "data/indexes/tibyan.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    rows = con.execute("SELECT metadata_json FROM passages WHERE source_id='quran'").fetchall()
    rng = random.Random(args.seed)
    texts = [json.loads(r[0])["publisher_aya_text_emlaey"] for r in rng.sample(rows, args.requests)]
    queries = [t if i % 2 else " ".join(t.split()[:4]) for i, t in enumerate(texts)]

    h = httpx.get(args.url + "/health", timeout=10).json()
    rounds = []
    rss_before = rss_mb(args.pid)
    for c in args.concurrency:
        lat, codes, wall = asyncio.run(run(args.url, queries, c))
        lat.sort()
        ok = codes.get(200, 0)
        rounds.append({
            "concurrency": c, "requests": len(queries), "succeeded": ok, "failed": len(queries) - ok,
            "status_codes": {str(k): v for k, v in sorted(codes.items())},
            "latency_ms": {"avg": round(statistics.fmean(lat), 1), "p50": round(statistics.median(lat), 1),
                           "p95": round(lat[round(0.95 * (len(lat) - 1))], 1), "max": round(lat[-1], 1)},
            "throughput_rps": round(len(queries) / wall, 1), "rss_mb_after": rss_mb(args.pid),
        })
        print(json.dumps(rounds[-1]))
    worst = max(rounds, key=lambda r: r["concurrency"])
    out = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "server": {"workers": 1, "search_mode": h.get("search_mode"), "llm_mode": h["components"]["llm"]["mode"],
                   "rate_limit": "disabled for this run", "host": "development container (loopback)"},
        "rounds": rounds,
        # flat summary of the highest-concurrency round, for the evaluation page
        "concurrency": worst["concurrency"], "requests": worst["requests"], "succeeded": worst["succeeded"],
        "failed": worst["failed"], "latency_ms": worst["latency_ms"], "throughput_rps": worst["throughput_rps"],
        "rss_mb": {"before": rss_before, "after": rss_mb(args.pid)},
        "note": "Single uvicorn worker; synchronous pipeline runs in the threadpool. Not a production-host capacity claim.",
    }
    dst = ROOT / "eval/results/load_test.json"
    dst.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {dst.relative_to(ROOT)}")
    return 0 if all(r["failed"] == 0 for r in rounds) else 1


if __name__ == "__main__":
    sys.exit(main())
