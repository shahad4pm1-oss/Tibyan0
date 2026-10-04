# Deployment (prepared in Phase 4; not deployed)

**Status: NOT DEPLOYED. No live URL.** No hosting credentials (Render, Netlify, Cloudflare) were available to the build. Everything below is ready for an operator who has them. The product runs safely without an LLM key: claim analysis shows «تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً» and no verdict.

## 1. Backend (Docker, e.g. Render)
Files: `Dockerfile`, `.dockerignore`, `render.yaml`.

- **Build:** `docker build -t tibyan-api .` from the repository root. The build installs `backend/requirements.txt`, then runs `python scripts/build_corpus.py`, which downloads the KFGQPC package, **refuses it unless its SHA-256 equals the pinned value**, ingests, builds FTS5, runs validation V01–V13 (build fails on any error) and builds the LSA + FAISS index. Network access to one of the routes in `data/metadata/quran_kfgqpc_hafs_v2.json` is needed at build time only.
- **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --no-server-header` (working directory `backend/`). Runs as non-root user `tibyan`.
- **Health check:** `GET /health` → `status: ok` when the corpus and lexical search are ready (a missing semantic index or LLM is reported in `components` but is not a failure). `config_problems` must be empty in production.
- **Render:** create a Blueprint from `render.yaml` (Docker runtime, `healthCheckPath: /health`, `autoDeploy: false`). Set `CORS_ORIGINS` to the real frontend origin. Leave the LLM variables unset until a key exists, then add `LLM_API_KEY` as a secret in the dashboard (never in the file).
- **Without Docker:** same steps in a virtualenv: `pip install -r backend/requirements.txt && python scripts/build_corpus.py && cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## 2. Frontend (static: Netlify or Cloudflare Pages)
Files: `frontend/netlify.toml`, `frontend/public/_redirects` (SPA fallback for `/methodology`, `/evaluation`), `frontend/public/_headers`.
- Base directory `frontend/`; build `npm ci && npm run build`; publish `dist/`; Node 22.
- Set **`VITE_API_BASE_URL`** to the backend's https origin at build time (it is public, not a secret).
- Cloudflare Pages reads `_redirects` and `_headers` from `dist/` automatically; Netlify uses `netlify.toml`.

## 3. Environment variables (backend)
Full list with defaults: `.env.example` and `ARCHITECTURE.md` §2. Production essentials:

| Variable | Production value |
|---|---|
| `APP_ENV` | `production` (disables `/docs`, refuses test doubles, hash embeddings, experimental paraphrase mode and fixture corpora) |
| `CORS_ORIGINS` | the frontend's `https://` origin(s), comma-separated |
| `RATE_LIMIT_PER_MINUTE` | `30` (must be > 0) |
| `TRUST_PROXY_HEADERS` | `true` behind Render's proxy, else `false` |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | `local_lsa` / `char-ngram-lsa-v1` |
| `HYBRID_STRATEGY` | `lexical_first` |
| `LOG_RAW_INPUT` | `false` |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | unset (no-LLM mode) until a key exists; then `gemini` or `anthropic`, a current model id, and the key as a host secret |

## 4. What was verified here
- **Docker:** the Docker CLI and daemon work in the build environment, but pulling `python:3.11-slim` from Docker Hub is blocked (HTTP 403), so the image was **not built**.
- **Clean-environment simulation** (equivalent to the Dockerfile steps): the deployable files only (`backend/app`, requirements, `scripts`, `data/metadata`, `data/curated`, `eval/results`) were copied to an empty directory with no `data/raw` or indexes; a fresh Python 3.11 virtualenv installed `requirements.txt`; `scripts/build_corpus.py` downloaded, verified, ingested, validated and indexed (`BUILD OK`). The resulting SQLite DB was **byte-identical** to the development DB. Started with `APP_ENV=production` using the Dockerfile's start command: `/health` → `ok`, `production`, `HYBRID`, 6,236 passages, integrity ok, `LLM_UNAVAILABLE`, no config problems; `/docs` → 404; a CORS preflight from a non-allowed origin → 400; a Quran quote → EXACT `112:1`, `ANALYSIS_UNAVAILABLE`; the 31st request in a minute from one IP → 429 with `Retry-After: 60`; the server log contained no user text.
- **Frontend:** `npm run build` succeeded; `vite preview` served the build for the browser E2E suite.

## 5. After deploying (checklist)
1. `GET /health` on the live URL: `status ok`, `app_env production`, `config_problems []`.
2. Open the frontend; run the four example buttons; confirm the no-LLM message and that `/methodology` and `/evaluation` load (deep links work).
3. Confirm the browser console shows no CORS errors.
4. Record the live URL in `BASELINE.md`.
