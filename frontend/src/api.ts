import type { AnalyzeResponse, ApiError } from "./types";

export const API = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type ErrorCode =
  | "NETWORK" | "INVALID_INPUT" | "CORPUS_NOT_AVAILABLE" | "INTERNAL_ERROR" | "RATE_LIMITED"
  | "PAYLOAD_TOO_LARGE" | "TIMEOUT" | "UNKNOWN";

export const ERROR_TEXT: Record<ErrorCode, { title: string; next: string }> = {
  NETWORK: { title: "تعذّر الوصول إلى خادم تبيان.", next: "تحقّق من اتصالك بالإنترنت ثم أعد المحاولة." },
  INVALID_INPUT: { title: "المدخلات غير صالحة.", next: "أدخل اقتباسًا يحتوي على نص عربي، والادعاء المصاحب له." },
  CORPUS_NOT_AVAILABLE: { title: "قاعدة المصادر غير متاحة حاليًا.", next: "لا يمكن التحقق دون قاعدة المصادر. أعد المحاولة لاحقًا." },
  INTERNAL_ERROR: { title: "حدث خطأ داخلي في الخادم.", next: "لم يُحفظ نص طلبك. أعد المحاولة بعد قليل." },
  RATE_LIMITED: { title: "وصلت إلى الحد المسموح من الطلبات.", next: "انتظر دقيقة ثم أعد المحاولة." },
  PAYLOAD_TOO_LARGE: { title: "النص أطول من المسموح.", next: "اختصر الاقتباس أو الادعاء إلى ٢٠٠٠ حرف أو أقل." },
  TIMEOUT: { title: "استغرق التحقق وقتًا أطول من المسموح.", next: "أعد المحاولة بعد قليل." },
  UNKNOWN: { title: "حدث خطأ غير متوقع.", next: "أعد المحاولة بعد قليل." },
};

export type AnalyzeResult =
  | { ok: true; data: AnalyzeResponse }
  | { ok: false; code: ErrorCode; requestId?: string; retryAfter?: number };

export async function analyze(quote: string, claim: string, signal?: AbortSignal): Promise<AnalyzeResult> {
  let res: Response;
  try {
    res = await fetch(`${API}/api/v1/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quote, claim, language: "ar" }),
      signal,
    });
  } catch {
    return { ok: false, code: "NETWORK" };
  }
  if (res.ok) {
    try {
      return { ok: true, data: (await res.json()) as AnalyzeResponse };
    } catch {
      return { ok: false, code: "UNKNOWN" };
    }
  }
  let code: ErrorCode = "UNKNOWN";
  let requestId: string | undefined;
  try {
    const err = (await res.json()) as ApiError;
    requestId = err.request_id;
    code = (err.error.code in ERROR_TEXT ? err.error.code : "UNKNOWN") as ErrorCode;
  } catch {
    code = res.status >= 500 ? "INTERNAL_ERROR" : "UNKNOWN";
  }
  const ra = Number(res.headers.get("Retry-After"));
  return { ok: false, code, requestId, retryAfter: Number.isFinite(ra) && ra > 0 ? ra : undefined };
}

export async function getJson<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${API}${path}`);
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}
