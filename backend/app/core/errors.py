"""User-safe error responses. Never include stack traces, internal messages or user input."""

from __future__ import annotations

from fastapi.responses import JSONResponse

from app.schemas.analyze import ErrorResponse

MESSAGES = {
    "INVALID_INPUT": ("المدخلات غير صالحة. أدخل اقتباسًا عربيًا وادعاءً مصاحبًا.",
                      "Invalid input. Provide an Arabic quote and its associated claim."),
    "CORPUS_NOT_AVAILABLE": ("قاعدة المصادر غير متاحة حاليًا. حاول لاحقًا.",
                             "The source corpus is not available right now. Please try later."),
    "INTERNAL_ERROR": ("حدث خطأ داخلي. لم يُحفظ نص طلبك. حاول مرة أخرى.",
                       "An internal error occurred. Please try again."),
    "RATE_LIMITED": ("وصلت إلى الحد المسموح من الطلبات. انتظر قليلًا ثم أعد المحاولة.",
                     "Too many requests. Please wait and try again."),
    "PAYLOAD_TOO_LARGE": ("حجم الطلب أكبر من المسموح. اختصر الاقتباس أو الادعاء.",
                          "Request too large. Shorten the quote or claim."),
    "TIMEOUT": ("استغرق التحقق وقتًا أطول من المسموح. أعد المحاولة بعد قليل.",
                "The request took too long. Please try again."),
    "NOT_FOUND": ("المسار غير موجود.", "Not found."),
    "METHOD_NOT_ALLOWED": ("طريقة الطلب غير مسموحة لهذا المسار.", "Method not allowed."),
}


def error(code: str, status: int, request_id: str, details: list[dict] | None = None,
          headers: dict[str, str] | None = None) -> JSONResponse:
    ar, en = MESSAGES[code]
    body = ErrorResponse(request_id=request_id,
                         error={"code": code, "message_ar": ar, "message_en": en, "details": details})
    h = {"X-Request-ID": request_id, **(headers or {})}
    return JSONResponse(status_code=status, content=body.model_dump(), headers=h)
