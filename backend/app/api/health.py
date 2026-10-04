from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Component readiness. 'ok' = corpus and lexical search ready. A missing LLM or semantic index is
    reported but is not a failure: the product runs in LLM_UNAVAILABLE / LEXICAL_ONLY mode. No secrets."""
    s = get_settings()
    p = getattr(request.app.state, "pipeline", None)
    problems = s.production_problems()
    if p is None:
        return HealthResponse(
            status="unavailable", app_env=s.app_env, corpus_version="unavailable", pipeline_version=s.pipeline_version,
            corpus_available=False, search_mode=None, embedding_model=None,
            components={"database": {"ready": False, "reason": request.app.state.pipeline_error},
                        "corpus": {"ready": False}, "lexical_search": {"ready": False},
                        "semantic_index": {"ready": False}, "llm": {"configured": False}},
            config_problems=problems)
    llm_prov, llm_model = (p.llm.provider, p.llm.model) if p.llm else (None, None)
    llm_mode = ("LLM_UNAVAILABLE" if p.llm is None
                else "TEST_DOUBLE_NON_PRODUCTION" if p.llm.is_test_double else "REAL_LLM")
    by_type = p.repo.count_by_type()
    hadith_by_source = {r[0]: r[1] for r in p.repo.conn.execute(
        "SELECT p.source_id, count(*) FROM passages p JOIN sources s ON s.id = p.source_id "
        "WHERE s.source_type = 'hadith' AND s.verification_status = 'APPROVED' GROUP BY 1")}
    return HealthResponse(
        status="ok" if p.corpus_integrity_ok else "degraded",
        app_env=s.app_env, corpus_version=p.corpus_version, pipeline_version=s.pipeline_version,
        app_version=s.pipeline_version, corpus_available=True, llm_mode=llm_mode,
        search_mode="HYBRID" if p.semantic.available else "LEXICAL_ONLY",
        embedding_model=p.semantic.model_label,
        components={
            "database": {"ready": True},
            "corpus": {"ready": True, "version": p.corpus_version, "passages": p.repo.count_eligible(),
                       "by_source_type": p.repo.count_by_type(),
                       "integrity_ok": p.corpus_integrity_ok},
            "quran_corpus": {"ready": by_type.get("quran", 0) > 0, "passages": by_type.get("quran", 0),
                             "status": "PRODUCTION_ACTIVE"},
            "hadith_corpus": {"ready": by_type.get("hadith", 0) > 0, "passages": by_type.get("hadith", 0),
                              "by_collection": hadith_by_source, "status": "LIMITED_PRODUCTION"},
            "lexical_search": {"ready": True, "indexes": {
                ix: p.repo.conn.execute(f"SELECT count(*) FROM {ix}").fetchone()[0]
                for ix in ("passages_fts", "hadith_fts")}},
            "semantic_index": {"ready": p.semantic.available, "model": p.semantic.model_label,
                               "reason": None if p.semantic.available else p.semantic.reason},
            "llm": {"configured": p.llm is not None, "provider": llm_prov, "model": llm_model,
                    "mode": llm_mode,
                    "reason": p.llm_unavailable_reason, "prompt_version": p.prompts.version},
        },
        config_problems=problems)
