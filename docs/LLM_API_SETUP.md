# LLM API key setup (optional) — إعداد مفتاح النموذج اللغوي (اختياري)

Arabic step-by-step version: `docs/RUN_WINDOWS.md`, sections 8–16. This file contains placeholders only — never a real key.

## 1. Purpose
Tibyan works fully without a key (`LLM_UNAVAILABLE`): quote matching, source, canonical text, context and evidence all come from the local corpus. A key enables only **claim analysis** (SUPPORTED / OVERSTATED / CONTRADICTED / INSUFFICIENT_EVIDENCE / REQUIRES_SPECIALIST), which runs:
- only for Quran results (hadith results show `CLAIM_ANALYSIS_NOT_ENABLED_FOR_SOURCE_TYPE`);
- only after the evidence gate passes;
- on backend evidence only, with citation, grounding and safety verification of the output.

The model is never a source of religious text. Supported providers:

| `LLM_PROVIDER` | Key from | Endpoint used (default) |
|---|---|---|
| `gemini` (alias `google`) | Google AI Studio → Get API key | `https://generativelanguage.googleapis.com` (`v1beta/models/<model>:generateContent`, key in the `x-goog-api-key` header) |
| `anthropic` | Anthropic console → API Keys | `https://api.anthropic.com` (Messages API) |

Neither adapter has been called against the live service from the build environment (no key there); both are tested with a mocked HTTP transport. Validate your key with step 5.

## 2. Where the key goes
One file only: **`.env` in the project root** (Windows: `C:\tibyan\.env`), next to `.env.example`. The backend always reads it from the project root, whatever folder it is started from. In a hosted deployment, use the host's secret store instead.

If `.env` does not exist (setup normally creates it):
```powershell
cd C:\tibyan
Copy-Item .env.example .env      # only if .env is missing — never overwrite an existing .env
```

## 3. Variables
Open with `notepad .env` and edit the existing lines (do not add duplicates: the last occurrence of a variable wins).

Gemini (Google AI Studio key):
```
LLM_PROVIDER=gemini
LLM_MODEL=<GEMINI_MODEL_ID>
LLM_API_KEY=<PASTE_YOUR_API_KEY_HERE>
LLM_TIMEOUT_S=60          (edit the existing line; default 30)
REQUEST_TIMEOUT_S=150     (edit the existing line; default 45 — covers one retry)
```

Anthropic:
```
LLM_PROVIDER=anthropic
LLM_MODEL=<REAL_MODEL_ID>
LLM_API_KEY=<PASTE_YOUR_API_KEY_HERE>
```

**Gemini model id:** in Google AI Studio pick the model and open "Get code"; the id is the text after `models/` (for example `gemini-3.8-flash`, as listed on Google's models page on 2026-10-03 — this changes over time). Write it without the `models/` prefix (the adapter strips it anyway). Google lists the 2.5 models as limited-access and the 2.0 models as shut down.
| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `gemini` or `anthropic`. Empty = claim analysis off. |
| `LLM_MODEL` | The exact model id available in your provider account (copy it from the provider's model list; Tibyan ships no hardcoded model name). |
| `LLM_API_KEY` | The secret. Read server-side only; never printed, logged, returned by `/health`, or sent to the browser. |
| `LLM_BASE_URL` | Empty = the provider's official endpoint (table above). An old `.env` that still says `https://api.anthropic.com` is ignored when the provider is `gemini`. |
| `LLM_TIMEOUT_S` | Per-call timeout, default 30 (60 recommended for Gemini thinking models). |
| `LLM_MAX_TOKENS` | Default 1024. For Gemini the adapter requests at least 8192 output tokens, because thinking tokens count against that limit; the thoughts themselves are never requested, stored or shown. |
| `LLM_TEMPERATURE` | Empty = provider default. |

No quotes, no spaces around `=`, no `< >`.

## 4. Restart
`.env` is read at startup:
```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```
The start screen then shows `LLM mode : REAL_LLM (gemini / <model>)` (or `anthropic / <model>`), and `http://localhost:8000/health` shows `"llm_mode":"REAL_LLM"` and `components.llm.configured: true`. This means *configured*, not *verified*: test the key with step 5.

## 5. Provider health test (one small real call)
From the project root:
```powershell
backend\.venv\Scripts\python.exe eval\provider_health.py
```
(Linux/macOS: `backend/.venv/bin/python eval/provider_health.py`.) It never prints the key, and writes `eval/results/provider_health.json`. Exit code 0 = OK, 2 = not configured, 1 = call failed.

## 6. Common errors
The adapters report only the HTTP status and the provider's error codes; never the key and never user text.

| Output | Cause / fix |
|---|---|
| `BLOCKED_BY_LLM_ACCESS`, reason `LLM_PROVIDER not set` / `LLM_MODEL not set` / `LLM_API_KEY not set` | Fill the missing line, save, restart. |
| `reason: unknown LLM_PROVIDER '...'` | Use `gemini` or `anthropic`. |
| `FAILED`, `HTTP 401` | Anthropic: invalid or revoked key, or extra spaces/quotes. Re-copy the key. |
| `HTTP 400 INVALID_ARGUMENT API_KEY_INVALID` | Gemini: invalid key (Google answers 400, not 401). Re-copy it from AI Studio. |
| `HTTP 403 PERMISSION_DENIED` | Gemini: the key/project is not allowed to use the Gemini API. |
| `HTTP 404 NOT_FOUND` | Gemini: model id wrong or not available to your key. |
| `HTTP 429 RESOURCE_EXHAUSTED` | Gemini: free-tier quota or rate limit reached. Wait, or enable billing in AI Studio. |
| `empty model output (finish reason SAFETY)` | Gemini declined to answer (safety filter). Tibyan shows no verdict. |
| `HTTP 403` | Key lacks permission for this model/service. |
| `HTTP 404` | Model id not found or not available to your account. Fix `LLM_MODEL`. |
| `HTTP 400` | Request rejected — most often billing/credit not set up, or an unsuitable model. Check the provider billing page. |
| `HTTP 429` | Rate limit or quota. Wait and retry. |
| `HTTP 5xx` / `529` | Provider-side temporary error. Retry later. |
| `error_category: TIMEOUT` | Slow network; check connection or raise `LLM_TIMEOUT_S`. |
| `transport error: ...` | No network, or a firewall/proxy blocking `generativelanguage.googleapis.com` / `api.anthropic.com`. |

In the app, when the model call fails or its output fails verification, Tibyan shows no verdict rather than an unverified one.

## 7. Security rules
- `.env` is listed in `.gitignore`. Never run `git add .env` or `git add -f .env`.
- Before any push: `git check-ignore .env` must print `.env`, and `git status` must not list `.env`.
- Never put the key in source code, README/docs, GitHub issues, chats, screenshots or logs.
- The frontend never receives the key; it reads only `VITE_API_BASE_URL`.
- If a key may have leaked, revoke it in the provider console and create a new one.

## 8. Disable / remove
Empty the three lines and restart:
```
LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=
```
The app returns to `LLM_UNAVAILABLE`; everything else keeps working.
