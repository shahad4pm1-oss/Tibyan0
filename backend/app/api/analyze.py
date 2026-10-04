from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import MESSAGES, error  # noqa: F401  (re-exported for callers)
from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse, ErrorResponse

router = APIRouter(prefix="/api/v1")
log = logging.getLogger("tibyan.api")


@router.post("/analyze", response_model=AnalyzeResponse,
             responses={413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 429: {"model": ErrorResponse},
                        500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def analyze(body: AnalyzeRequest, request: Request):
    rid = request.scope.get("state", {}).get("request_id") or "unknown"
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        return error("CORPUS_NOT_AVAILABLE", 503, rid)
    try:
        return await asyncio.wait_for(run_in_threadpool(pipeline.analyze, body, rid),
                                      timeout=get_settings().effective_request_timeout_s)
    except TimeoutError:
        log.warning("request timeout %s", rid)
        return error("TIMEOUT", 504, rid)
    except Exception:
        log.exception("internal error in analyze %s", rid)
        return error("INTERNAL_ERROR", 500, rid)
