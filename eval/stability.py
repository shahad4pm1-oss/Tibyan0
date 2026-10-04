"""Stability test (Task 23): run each critical case N times (default 3) with the REAL configured provider
and report label fluctuation honestly (every run recorded; nothing cherry-picked).

Requires LLM_PROVIDER/LLM_MODEL/LLM_API_KEY for a real (non-test-double) provider.
Without one it writes eval/results/stability.json with status BLOCKED_BY_LLM_ACCESS and exits 2.

usage: python eval/stability.py [--runs 3]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from run_safety_eval import build_quote, load

from app.core.config import Settings
from app.llm.factory import build_provider
from app.schemas.analyze import AnalyzeRequest
from app.services.analysis_pipeline import AnalysisPipeline

OUT = ROOT / "eval/results/stability.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    s = Settings(database_path=str(ROOT / "data/indexes/tibyan.sqlite3"))
    st = build_provider(s)
    OUT.parent.mkdir(exist_ok=True)
    if st.provider is None or st.provider.is_test_double:
        OUT.write_text(json.dumps({"status": "BLOCKED_BY_LLM_ACCESS", "reason": st.reason or "test double",
                                   "generated_at": datetime.now(UTC).isoformat(timespec="seconds")}, indent=1))
        print("BLOCKED_BY_LLM_ACCESS:", st.reason)
        return 2
    p = AnalysisPipeline(s, ROOT, provider=st.provider)
    cases = [c for c in load("technical_cases.jsonl") if c["critical"] and c["expected"].get("llm_calls", 0) > 0]
    cases += [c for c in load("candidate_cases_pending.jsonl") if c["critical"]]
    rows = []
    for c in cases:
        q = build_quote(p.repo, c["quote_spec"])
        labels = [p.analyze(AnalyzeRequest(quote=q, claim=c["claim"])).claim_analysis.relation for _ in range(a.runs)]
        rows.append({"id": c["id"], "labels": labels, "stable": len(set(labels)) == 1, "counts": Counter(labels)})
    rep = {"status": "COMPLETED", "provider": st.provider.provider, "model": st.provider.model, "runs": a.runs,
           "cases": len(rows), "stable_cases": sum(r["stable"] for r in rows), "rows": rows,
           "generated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=dict), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("model", "runs", "cases", "stable_cases")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
