import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.analyze import router as analyze_router
from app.api.health import router as health_router
from app.api.info import router as info_router
from app.core.config import get_settings
from app.core.errors import error
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RateLimiter,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from app.services.analysis_pipeline import AnalysisPipeline, CorpusNotAvailable

ROOT = Path(__file__).resolve().parents[2]  # repository root
log = logging.getLogger("tibyan")


def configure_logging() -> None:
    """Give the 'tibyan' logger tree its own stderr handler at INFO, so the audit line (ids and codes only,
    never user text) is emitted under any server, independent of uvicorn's or the root logger's config."""
    if not any(getattr(h, "_tibyan", False) for h in log.handlers):
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        h._tibyan = True
        log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False  # avoid duplicate lines through the root logger


def load_pipeline(app: FastAPI) -> None:
    settings = get_settings()
    for problem in settings.production_problems():
        log.error("production configuration problem: %s", problem)
    try:
        app.state.pipeline = AnalysisPipeline(settings, ROOT)
        app.state.pipeline_error = None
    except CorpusNotAvailable as e:
        app.state.pipeline = None
        app.state.pipeline_error = str(e)
        log.error("corpus not available: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_pipeline(app)
    yield


def _rid(request: Request) -> str:
    return request.scope.get("state", {}).get("request_id") or "unknown"


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    prod = settings.app_env == "production"
    app = FastAPI(title="Tibyan API", version=settings.pipeline_version, lifespan=lifespan, debug=False,
                  docs_url=None if prod else "/docs", redoc_url=None, openapi_url=None if prod else "/openapi.json")
    app.state.pipeline = None
    app.state.pipeline_error = "not loaded"
    app.state.root = ROOT

    # Middleware order: outermost added last. Request id -> body limit -> rate limit -> CORS -> app.
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"], expose_headers=["X-Request-ID", "Retry-After"])
    app.add_middleware(RateLimitMiddleware, limiter=RateLimiter(settings.rate_limit_per_minute),
                       paths=("/api/v1/analyze",), trust_proxy=settings.trust_proxy_headers)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(x) for x in e.get("loc", [])[1:]), "issue": e.get("type")}
                   for e in exc.errors()]
        return error("INVALID_INPUT", 422, _rid(request), details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INTERNAL_ERROR")
        return error(code, exc.status_code if code != "INTERNAL_ERROR" else 500, _rid(request))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error %s", _rid(request))
        return error("INTERNAL_ERROR", 500, _rid(request))

    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(info_router)
    return app


app = create_app()
