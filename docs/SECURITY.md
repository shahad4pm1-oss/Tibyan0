# Security (Phase 4, 2026-10-01)

Scope: the FastAPI backend (`backend/app`), the static React frontend, the corpus build, and the deployment files. Tibyan stores no user accounts and no user content; the main assets are the integrity of the religious text, the availability of the service, the LLM API key (when one exists), and users' privacy.

## 1. Threats and controls

| Threat | Control | Where | Tested by |
|---|---|---|---|
| Altered or fabricated religious text | Corpus built only from the SHA-256-pinned KFGQPC package; 13 validation checks; runtime digest of all `original_text` must match the build digest, else claim analysis is disabled; every displayed passage is re-read from the DB; evidence text re-checked before the LLM step | `scripts/fetch_quran.py`, `corpus/validation.py`, `analysis_pipeline.py` | `test_original_text_integrity.py`, `test_corpus_validation.py` |
| A test fixture corpus served in production | Production refuses any DB whose `corpus_kind` is not `production` (503 `CORPUS_NOT_AVAILABLE`) | `analysis_pipeline.py` | `test_api_hardening.py::test_production_hides_docs_and_refuses_fixture_corpus` |
| Mock / fake AI in production | Test doubles are refused when `APP_ENV=production` (provider factory and pipeline); `hash` embeddings and `PARAPHRASE_MODE=experimental` are refused; `production_problems()` lists any such setting in `/health` | `llm/factory.py`, `core/config.py` | `test_safety.py`, `test_paraphrase_gate.py`, `test_api_hardening.py` |
| Prompt injection via quote/claim | User text only inside an escaped data block; routing and gate do not depend on the model; schema, citation, grounding and lint verifiers reject non-conforming output | `claim_analyzer.py`, verifiers | `test_prompt_injection.py` (structural only; real-model resistance not measured) |
| SQL / FTS injection | Parameterised SQL everywhere; FTS queries built from normalised tokens, each quoted | `repositories/corpus.py` | `test_api_hardening.py::test_fts_and_sql_injection_inputs_are_safe` |
| XSS | React escapes all text; no `dangerouslySetInnerHTML`, `innerHTML` or `eval` in `frontend/src` (grep-verified); API returns JSON only with `X-Content-Type-Options: nosniff` | frontend | grep in final regression |
| Clickjacking, referrer leaks | `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` on API responses and (via `_headers` / `netlify.toml`) on the static site | `core/middleware.py` | `test_api_hardening.py` |
| Abuse / cost exhaustion | Per-IP rate limit on `POST /api/v1/analyze` (default 30/min, 429 + `Retry-After`); body limit 16 KiB (413); field limits 2,000 chars (422); whole-request timeout 45 s (504); LLM timeout and one retry max | `core/middleware.py`, `api/analyze.py` | `test_api_hardening.py`; live check: request 31 in a minute returned 429 |
| IP spoofing past the rate limit | `X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS=true` (set only behind a proxy that overwrites it, e.g. Render) | `core/middleware.py` | `test_api_hardening.py` |
| Cross-origin misuse | CORS allow-list; in production only `https://` non-localhost origins are honoured and `*` is dropped; only `GET` and `POST` (plus CORS preflight) | `core/config.py`, `main.py` | preflight allow/deny tests |
| Information leakage in errors | Uniform JSON errors with a code, bilingual message and request id; no stack traces; `/docs`, `/redoc`, `/openapi.json` disabled in production; `--no-server-header` | `main.py`, `core/errors.py` | `test_api_hardening.py`, live check (`/docs` → 404) |
| Secret leakage | Keys only from environment variables (`LLM_API_KEY`); never logged, never returned (`/health` reports only provider/model/mode); `.env` git-ignored; `render.yaml` marks the key `sync: false`; frontend bundle contains no key names (grep-verified); `detect-secrets` scan | `.gitignore`, `llm/` | final regression |
| Privacy | Raw quote/claim text is never logged (`LOG_RAW_INPUT=false`); audit log has ids, codes, counts and timings only; nothing persisted; `Cache-Control: no-store` | `services/analysis_pipeline.py`, `core/middleware.py` | `test_e2e_api_real.py::test_raw_input_never_logged`; live check: 0 occurrences of the quote in the server log |
| Malicious image files (screenshot input, 2026-10-03) | No server surface: OCR runs in the browser and the API has no upload route; image bodies are refused by the body limit (413) or as invalid JSON (422) before any parsing. In the browser, before any decoding: size ≤ 8 MB; the real file signature (magic bytes) must be PNG, JPEG or WEBP, whatever the name or extension says; the type the browser derived from the extension must match the signature (a JPEG named `.png` is refused); width/height are read from the header and must be ≤ 8000 px per side and ≤ 24 MP (decompression-bomb limit), ≥ 16 px; then a real decode, whose size must match the header. GIF, SVG (scriptable), PDF, HEIC/AVIF, TIFF, BMP and executables are refused. Nothing is executed or rendered from the file except decoded pixels | `frontend/src/ocr/validate.ts` | `frontend/e2e/screenshot.spec.ts` (empty, oversized, 20000×20000 header, 9000 px side, 8×8, corrupt, GIF, SVG with script, PDF, `MZ` executable, text named `.png`, JPEG named `.png`); `backend/tests/test_no_image_upload.py` |
| Hostile file names (XSS, path traversal, bidi spoofing) | Only the base name is shown, as React text (never HTML); control and bidirectional-override characters are stripped; long names are shortened; the name is never sent or stored | `validate.ts::displayName` | E2E: `<img src=x onerror=…>.png` renders as text with no dialog, `../../../etc/passwd.png` shows `passwd.png`, RLO names are neutralised; no request contains the name |
| Text from an image used as an injection vector | Extracted text is shown for review and goes through the same `/api/v1/analyze` request, limits, routing, gate and verifiers as typed text; the image never reaches a model | `ImageVerify.tsx`, existing pipeline | same tests as typed input (`test_prompt_injection.py`) |
| Third-party code at runtime for OCR | tesseract.js 7.0.0, its WebAssembly core and the Arabic model are pinned in `package-lock.json` and served by the site itself under `/ocr/`; nothing is fetched from a CDN; the worker is created from a same-origin URL (no `blob:` worker) | `frontend/vite.config.ts`, `src/ocr/ocr.ts` | E2E asserts every request goes to the site or the API |
| Container privileges | Image runs as non-root user `tibyan` (uid 10001); corpus is opened read-only | `Dockerfile` | not built here (§4) |

## 2. Rate limiting: what it is and is not
An in-process sliding window (`RateLimiter`) keyed by client IP. It is simple and has no external dependency, but:
- counters are per worker process and reset on restart;
- with several workers or instances the effective limit multiplies;
- it is not a DDoS defence. For anything beyond a single small instance use the host's edge rate limiting or a shared store.
`RATE_LIMIT_PER_MINUTE=0` disables it (tests and load tests only); production reports that as a configuration problem.

## 3. Dependency audit (2026-10-01; frontend re-run 2026-10-03 after adding tesseract.js)
| Tool | Target | Result |
|---|---|---|
| `pip-audit` 2.10.1 | `backend/requirements.txt` | No known vulnerabilities found |
| `pip-audit` 2.10.1 | `backend/requirements-dev.txt` | No known vulnerabilities found |
| `npm audit` | `frontend` (all deps) | 0 vulnerabilities |
| `npm audit --omit=dev` | `frontend` (shipped deps) | 0 vulnerabilities |
| `npm audit` (2026-10-03) | `frontend` (all deps, incl. tesseract.js 7.0.0, tesseract.js-core 7.0.0, @tesseract.js-data/ara 1.0.0) | 0 vulnerabilities |
| `npm audit --omit=dev` (2026-10-03) | `frontend` (shipped deps) | 0 vulnerabilities |

These reflect the advisory databases on that date only.

## 4. Not done / residual risk
- Docker image not built in the build environment (Docker Hub blocked); the Dockerfile's steps were verified in a clean virtualenv (`DEPLOYMENT.md` §4). Base-image CVE scan not run.
- No Content-Security-Policy yet on the static site (the API origin would need to be allow-listed per deployment; fonts are self-hosted, so no font service needs allow-listing). `index.html` contains one small inline script that applies a saved light/dark preference before first paint; a CSP would need its hash. Screenshot OCR would additionally need `worker-src 'self'`, `script-src 'self' 'wasm-unsafe-eval'` (WebAssembly compilation) and `img-src 'self' blob:` (the local preview).
- Image checks run in the browser (there is nothing on the server to protect); a modified client can skip them, but then it only affects that visitor's own tab, and the server still accepts nothing but the JSON quote/claim request.
- No authentication: the API is public by design. Abuse protection is the rate limit only.
- Real-model prompt-injection resistance is not measured (no LLM key).
- No external penetration test.

## 5. Reporting
Report security issues privately to the maintainers (repository owner) rather than in public issues. Include the `X-Request-ID` of an affected response if available; it lets the operator find the audit line without any user text.
