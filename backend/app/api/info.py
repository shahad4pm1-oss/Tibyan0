"""Read-only information endpoints for the methodology and evaluation pages.

/api/v1/evaluation serves ONLY numbers already measured and saved under eval/results/. Guard-rail results
from scripted test doubles are labelled as such and never presented as model performance. LLM metrics are
reported as PENDING_REAL_MODEL_VALIDATION until a real-model evaluation file exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.services import normalizer
from app.services.evidence_gate import GateDecision

router = APIRouter(prefix="/api/v1")

PIPELINE_STEPS = [
    "input validation", "Quran retrieval (BM25 + LSA vector baseline, lexical_first)", "quote matching (deterministic)",
    "hadith retrieval if the Quran gives no verbatim match (separate BM25 index; Bukhari, Muslim)",
    "source resolution (re-read from approved corpus)",
    "context (Quran: ±2 ayat within the surah; hadith: the full hadith only)",
    "evidence objects (E1…En, canonical text from the database)",
    "tafsir commentary for the matched ayah (al-Tabari via Quran.com API, local Tafsir Mujahid as fallback; shown as a separate layer, never as Quran text)", "content level routing (A–D)",
    "evidence gate (LLM only on PASS; Quran results only)", "LLM claim analysis (only if configured)", "strict schema validation",
    "citation verification", "grounding verification", "safety checks", "response",
]


def _load(root: Path, name: str) -> dict | None:
    p = root / "eval" / "results" / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.get("/methodology")
def methodology(request: Request) -> dict:
    s = get_settings()
    p = getattr(request.app.state, "pipeline", None)
    src = None
    if p is not None:
        row = p.repo.conn.execute("SELECT id, title, edition, publisher, source_url, verification_status, "
                                  "metadata_json FROM sources WHERE id = 'quran'").fetchone()
        if row:
            meta = json.loads(row[6])
            src = {"id": row[0], "title": row[1], "edition": row[2], "publisher": row[3], "source_url": row[4],
                   "verification_status": row[5], "package_sha256": meta.get("package_sha256"),
                   "distribution": "Quranpedia / Quran.ws (quran-text repository), byte-identical KFGQPC package"}
    sources = []
    if p is not None:
        for r in p.repo.conn.execute("SELECT id, source_type, title, author, edition, publisher, source_url, "
                                     "verification_status, license_note, metadata_json FROM sources "
                                     "WHERE source_type NOT IN ('synthetic_fixture', 'dictionary') ORDER BY rowid"):
            m = json.loads(r[9])
            sources.append({"id": r[0], "source_type": r[1], "title": r[2], "author": r[3], "edition": r[4],
                            "publisher": r[5], "source_url": r[6], "verification_status": r[7],
                            "license_note": r[8], "provenance": m.get("provenance"),
                            "package_sha256": m.get("package_sha256"), "file_sha256": m.get("file_sha256"),
                            "gaps": len(m["gaps"]) if isinstance(m.get("gaps"), list) else None})
    t_src = getattr(p, "tafsir", None) if p is not None else None
    tafsirs = (t_src.describe_all() if hasattr(t_src, "describe_all") else [t_src.describe()]) if t_src else []
    tafsirs = [d for d in tafsirs if d]
    tafsir = next((d for d in tafsirs if not d.get("live_api")), None)  # local book: counted ayat
    for live in (d for d in tafsirs if d.get("live_api")):
        sources.append({"id": f"tafsir:{live['id']}", "source_type": "tafsir", "title": live["name"],
                        "author": live["author"]["name"], "edition": live["edition"], "publisher": live["nasher"],
                        "verification_status": "LIVE_COMMENTARY", "source_url": "https://quran.com",
                        "license_note": "Quran.com API v4 (live); not run against the live API in the build environment"})
    if tafsir:
        author = tafsir.get("author") or {}
        sources.append({"id": f"tafsir:{tafsir.get('id')}", "source_type": "tafsir", "title": tafsir.get("name"),
                        "author": author.get("ar_name") if isinstance(author, dict) else None,
                        "edition": tafsir.get("edition") or "", "publisher": tafsir.get("nasher"),
                        "source_url": "https://quranpedia.net", "verification_status": "LOCAL_COMMENTARY",
                        "license_note": "Quranpedia.net dump " + str(tafsir.get("dump_version")),
                        "provenance": "local JSON files, one per surah (data/json-data)",
                        "package_sha256": None, "file_sha256": None, "gaps": None})
    return {
        "llm_is_a_source": False,
        "sources": sources,
        "counts": {"by_source_type": p.repo.count_by_type() if p else {},
                   "tafsir_ayahs": tafsir.get("ayahs", 0) if tafsir else 0},
        "analysis_enabled_source_types": ["quran"],
        "source_status": {"quran": "PRODUCTION_ACTIVE", "hadith": "LIMITED_PRODUCTION"},
        "statement": "The language model is not a source of Islamic information. All religious text comes from the "
                     "approved corpus; the model only classifies the claim against that evidence.",
        "source": src,
        "versions": {"corpus": p.corpus_version if p else None, "pipeline": s.pipeline_version,
                     "retrieval": s.retrieval_version, "normalizer": normalizer.VERSION,
                     "prompt": s.prompt_version, "embedding_model": p.semantic.model_label if p else None,
                     "ranking_strategy": s.hybrid_strategy, "paraphrase_mode": "disabled"},
        "llm": {"configured": bool(p and p.llm), "provider": p.llm.provider if p and p.llm else None,
                "model": p.llm.model if p and p.llm else None},
        "pipeline": PIPELINE_STEPS,
        "gate_decisions": [d.value for d in GateDecision],
        "relations": ["SUPPORTED", "OVERSTATED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "REQUIRES_SPECIALIST"],
    }


@router.get("/evaluation")
def evaluation(request: Request) -> dict:
    root: Path = request.app.state.root
    dev, held = _load(root, "retrieval_comparison.json"), _load(root, "retrieval_comparison_heldout_seed777.json")
    safety = _load(root, "safety_eval.json")
    perf, load, tests = _load(root, "performance.json"), _load(root, "load_test.json"), _load(root, "test_suite.json")
    live = _load(root, "live_llm_eval.json")
    multi = _load(root, "multi_source_eval.json")

    def retr(d):
        if not d:
            return None
        return {"seed": d["seed"], "cases": d["cases_total"], "generated_at": d["generated_at"],
                "case_source": d["case_source"], "overall": d["overall"],
                "quote_matching_production": d["quote_matching_outcomes_by_pool"].get("production_lexical_first"),
                "not_found_synthetic": d["not_found_synthetic"]}

    return {
        "retrieval": {"development": retr(dev), "held_out": retr(held)},
        "guard_rails": None if not safety else {
            "label": "Guard-rail behaviour with SCRIPTED TEST-DOUBLE model outputs. Not model performance.",
            "generated_at": safety["generated_at"], "cases": safety["technical_cases"],
            "metrics": safety["safety_metrics"]},
        "llm": live or {"status": "PENDING_REAL_MODEL_VALIDATION"},
        "classification": {"status": "NOT_COMPUTED", "reviewed_cases": 0,
                           "reason": "no qualified-reviewer gold labels yet"},
        "multi_source": None if not multi else {k: multi.get(k) for k in (
            "generated_at", "seed", "cases_per_category", "case_source", "hadith_retrieval_bm25",
            "hadith_matching_full_pipeline", "quran_cases_full_pipeline_by_resolved_source",
            "not_found_synthetic_full_pipeline", "not_measured")},
        "performance": perf, "load_test": load, "test_suite": tests,
    }
