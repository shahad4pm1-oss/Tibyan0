from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str  # ok | degraded | unavailable
    app_env: str
    corpus_version: str
    pipeline_version: str
    app_version: str | None = None
    corpus_available: bool
    llm_mode: str = "LLM_UNAVAILABLE"   # REAL_LLM | LLM_UNAVAILABLE | TEST_DOUBLE_NON_PRODUCTION (never in production)
    search_mode: str | None = None
    embedding_model: str | None = None
    components: dict = {}
    config_problems: list[str] = []
