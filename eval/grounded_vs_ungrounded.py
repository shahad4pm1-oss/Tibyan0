"""Grounded vs ungrounded experiment (Task 24). EVALUATION ONLY; the ungrounded mode is not a product mode.

A: the model gets only quote + claim (eval/prompts/ungrounded_baseline_v1.txt), no evidence.
B: the Tibyan grounded pipeline (gate + evidence + verifiers).
Measured per arm: output validity (strict schema), unsupported citation attempts (source/reference mentions
and quotations, detected with the same verifiers against an EMPTY evidence set for A), abstention rate.
No superiority is claimed unless these measurements show it.

Requires a real provider; otherwise writes status BLOCKED_BY_LLM_ACCESS and exits 2.
usage: python eval/grounded_vs_ungrounded.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from pydantic import ValidationError
from run_safety_eval import build_quote, load

from app.core.config import Settings
from app.llm.base import LLMError
from app.llm.factory import build_provider
from app.schemas.analyze import AnalyzeRequest
from app.schemas.claim_analysis import LLMClaimOutput, provider_json_schema
from app.services import citation_verifier
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.claim_analyzer import escape_user_data, parse_output
from app.services.grounding_verifier import GroundingVerifier

OUT = ROOT / "eval/results/grounded_vs_ungrounded.json"


def main() -> int:
    s = Settings(database_path=str(ROOT / "data/indexes/tibyan.sqlite3"))
    st = build_provider(s)
    OUT.parent.mkdir(exist_ok=True)
    if st.provider is None or st.provider.is_test_double:
        OUT.write_text(json.dumps({"status": "BLOCKED_BY_LLM_ACCESS", "reason": st.reason or "test double",
                                   "generated_at": datetime.now(UTC).isoformat(timespec="seconds")}, indent=1))
        print("BLOCKED_BY_LLM_ACCESS:", st.reason)
        return 2
    prov = st.provider
    p = AnalysisPipeline(s, ROOT, provider=prov)
    gv = GroundingVerifier(p.repo)
    system_a = (ROOT / "eval/prompts/ungrounded_baseline_v1.txt").read_text(encoding="utf-8")
    cases = [c for c in load("technical_cases.jsonl") if c["expected"].get("llm_calls", 0) > 0]
    cases += load("candidate_cases_pending.jsonl")
    a = {"n": 0, "valid": 0, "unsupported_citation_attempts": 0, "abstained": 0, "errors": 0}
    b = {"n": 0, "displayed_ai": 0, "rejected": 0, "abstained_or_referred": 0, "unavailable": 0}
    for c in cases:
        q = build_quote(p.repo, c["quote_spec"])
        a["n"] += 1
        try:
            res = prov.complete_json(system_a, f"QUOTE: {escape_user_data(q)}\nCLAIM: {escape_user_data(c['claim'])}",
                                     provider_json_schema(), 1024)
            o = LLMClaimOutput.model_validate(parse_output(res.text))
            a["valid"] += 1
            issues = citation_verifier.verify(o, []) + gv.verify(o, [], q, c["claim"])
            a["unsupported_citation_attempts"] += int(bool(issues))
            a["abstained"] += int(o.relation in ("INSUFFICIENT_EVIDENCE", "REQUIRES_SPECIALIST"))
        except (LLMError, ValidationError, ValueError, TypeError):
            a["errors"] += 1
        r = p.analyze(AnalyzeRequest(quote=q, claim=c["claim"])).claim_analysis
        b["n"] += 1
        b["displayed_ai"] += int(r.summary_source == "ai")
        b["rejected"] += int(r.status == "AI_OUTPUT_REJECTED")
        b["abstained_or_referred"] += int(r.relation in ("INSUFFICIENT_EVIDENCE", "REQUIRES_SPECIALIST"))
        b["unavailable"] += int(r.status == "ANALYSIS_UNAVAILABLE")
    rep = {"status": "COMPLETED", "provider": prov.provider, "model": prov.model, "A_ungrounded": a, "B_grounded": b,
           "note": "Descriptive counts only; no superiority claim without review of the outputs.",
           "generated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
