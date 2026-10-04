# Architecture (frozen for V1, 2026-10-01)

Stack frozen in Phase 1. Phase 2 implemented retrieval through evidence; Phase 3 implemented content-level routing, the evidence gate, LLM claim analysis and its verifiers, safety and the final response (see §5 and `AI_SAFETY.md`). Phase 4 hardened the API, finished the product UI and prepared deployment (§5, `SECURITY.md`, `DEPLOYMENT.md`).

## 1. Stack
| Layer | Choice | Why |
|---|---|---|
| Frontend | React + TypeScript + Vite + Tailwind CSS, **Arabic RTL-first** (`<html lang="ar" dir="rtl">`) | Fast static build; hosts on Cloudflare Pages/Netlify (guide p.34) |
| Backend | Python 3.11+ (verified on 3.11.15), FastAPI, Pydantic v2, Uvicorn | Typed request/response contracts enforce SP-01/SP-03 at the schema level |
| Database | SQLite (single file, read-only at runtime) | Corpus is small and static; zero ops cost |
| Lexical retrieval | SQLite FTS5 with `bm25()` | Built into SQLite |
| Semantic retrieval | Vector-space retrieval + FAISS (`faiss-cpu`), index in `data/indexes/`. Current model: character n-gram TF-IDF + LSA, **not a neural embedding model**; a neural provider can be plugged in via `EMBEDDING_PROVIDER` and must be re-evaluated | Small corpus, in-process |
| AI | Provider abstraction: `EmbeddingProvider`, `LLMProvider` (`app/llm/`: Anthropic Messages API and Google Gemini generateContent adapters over plain HTTP, test doubles, factory, cost) | No vendor lock-in |
| Hosting (prepared, not deployed) | Backend: Docker image (`Dockerfile`, `render.yaml` for Render). Frontend: static build (`frontend/netlify.toml`, `public/_redirects`, `public/_headers` for Netlify / Cloudflare Pages) | Suggested by guide; no hosting credentials available yet (`DEPLOYMENT.md`) |

Not used: Redis, microservices, Kubernetes, message queues (see `SCOPE.md`).

## 2. Configuration
All runtime settings come from environment variables (see `.env.example`), loaded by `backend/app/core/config.py`.

| Variable | Meaning |
|---|---|
| `APP_ENV` | `development` / `test` / `production` |
| `DATABASE_PATH` | SQLite corpus file |
| `FAISS_INDEX_PATH` | Reserved (the FAISS index lives next to the DB in `data/indexes/`) |
| `CORPUS_VERSION` | Version label of the curated corpus, shown in UI and responses |
| `PIPELINE_VERSION` | Version of the pipeline logic |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | Claim-analysis model (`gemini`, `anthropic`, or `test_double` outside production). Unset = no verdicts, source verification still works |
| `LLM_BASE_URL`, `LLM_TIMEOUT_S`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE` | Adapter settings; empty `LLM_BASE_URL` = provider's official endpoint (ANTHROPIC_*/GOOGLE_*/GEMINI_* env vars are never read) |
| `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | Operator-supplied prices for cost telemetry; unset = no cost |
| `PROMPT_VERSION` | `claim_analysis_v1` |
| `GATE_MIN_QUOTE_TOKENS`, `STRENGTH_MIN_TOKENS_SUFFICIENT` | 3, 5 (uncalibrated) |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY` | Embedding model |
| `CORS_ORIGINS` | Comma-separated allowed origins. In production only `https://` non-localhost origins are honoured; `*` is dropped |
| `RATE_LIMIT_PER_MINUTE` | 30 per client IP on `POST /api/v1/analyze` (in-process, per worker). `0` disables; refused in production |
| `TRUST_PROXY_HEADERS` | `false`. `true` only behind a proxy that sets `X-Forwarded-For` (Render) |
| `MAX_BODY_BYTES` | 16384 |
| `REQUEST_TIMEOUT_S` | 45 (whole `/api/v1/analyze` request; 504 `TIMEOUT` on expiry) |
| `LOG_RAW_INPUT` | Default `false` (SP-07) |
| `HYBRID_STRATEGY` | `lexical_first` (default, evidence-backed) or `rrf` |
| `RRF_K`, `LEXICAL_TOP_K`, `SEMANTIC_TOP_K`, `HYBRID_TOP_N` | 60, 20, 20, 5 |
| `PARAPHRASE_MODE` | `disabled` (default; `experimental` refused in production) |
| `PARAPHRASE_MIN_COVERAGE`, `PARAPHRASE_MIN_MARGIN`, `MIN_PARTIAL_TOKENS`, `MAX_SPAN_AYAT`, `CONTEXT_WINDOW` | 0.6, 0.1, 2, 3, 2 (uncalibrated) |

Business logic depends only on the interfaces; concrete providers are chosen by a factory from `*_PROVIDER`. **Provider and model choices are open decisions** (see Phase 1 report). The `hash` embedding provider is a test double, refused when `APP_ENV=production`.

## 3. Request pipeline

```
Frontend (React, RTL)
  │  POST /api/v1/analyze {quote, claim, language}
  ▼
FastAPI
  ▼
1  Input Validation        Pydantic: lengths, Arabic script, required fields
  ▼
2  Scope/Safety Gate       Level A–D; Level D → referral (SP-05); off-scope → refusal (SP-16)
  ▼
3  Arabic Normalization    Versioned rules; same function used at index time and query time
  ▼
4a Lexical Retrieval (FTS5/BM25)   ┐
4b Semantic Retrieval (LSA + FAISS) ┘ candidate pool only; never decides a match
  ▼
5  Hybrid Ranking          lexical_first (default) or RRF; exact-phrase candidates first
  ▼
6  Quote Matcher           EXACT / PARTIAL / AMBIGUOUS / NOT_FOUND (deterministic); PARAPHRASED reserved, disabled
  ▼
7  Source Resolution       RESOLVED / AMBIGUOUS / NOT_FOUND; re-reads passages from the approved corpus
  ▼
8  Context Expansion       Quran: ±N ayat within the surah; hadith: full text + chapter
  ▼
9  Evidence Builder        EvidenceItem[] with ids, type, locator, text from DB
  ▼
10 Evidence Gate           Sufficient? else INSUFFICIENT_EVIDENCE (SP-06), stop
  ▼
11 Claim Analyzer          LLM/NLI over evidence ids only → verdict + cited evidence ids + spans
  ▼
12 Citation Verifier       Every cited id/span re-read from DB; mismatch → drop + downgrade (SP-02)
  ▼
13 Scientific Safety       Level rules, certainty qualifier, banned-absolutes lint, disclosures (SP-03/04/08/13)
  ▼
14 Response Builder        Segments typed source_text / commentary / ai_explanation; versions
```

Short-circuits: the evidence gate (step 10) ends the request with an abstention (INSUFFICIENT) or referral (SPECIALIST_REQUIRED) without calling the LLM. Every request writes one audit log line (ids and codes only) and returns stage timings in `metadata.timings_ms`.

**As implemented in Phase 3** (order in `analysis_pipeline.py`): validate input → retrieve (BM25 + LSA, lexical_first) → match quote → resolve source → expand context → build evidence → **classify content level** (`content_level_router.py`; Phase 1's "Scope/Safety Gate" step 2 is implemented here, after retrieval, because level D/C routing must not suppress source verification) → **evidence gate** → **LLM claim analyzer** (`claim_analyzer.py`) → **schema validation** → **citation verifier** → **grounding verifier** → **safety lint** (one retry on any verification failure) → **safety finalize** (`safety.py`) → response builder.

### Deviations from the Phase 1 plan (all in Phase 2, with reasons)
1. **Matcher before resolver** (steps 6/7 swapped): resolution needs the match result to know which passage(s) the quote belongs to, and whether it is ambiguous.
2. **Endpoint name** `/api/v1/analyze` (was `/verify` in the plan): as specified for Phase 2.
3. **Hybrid default is `lexical_first`, not plain RRF**: on 2 × 1,400 known-answer cases RRF was worse than BM25 alone, and the LSA retriever is weaker than BM25 (`METHODOLOGY.md` §5). The LSA candidates only widen the pool; no retrieval improvement from the semantic component is claimed. RRF stays available.
4. **Quote statuses** `PARAPHRASED` and `AMBIGUOUS` replace Phase 1's `VARIANT` (as specified for Phase 2). After the Phase 2 corrections, `PARAPHRASED` is reserved/experimental and disabled in production: a misquotation returns `AMBIGUOUS` (`NEAR_MATCH_UNCONFIRMED`) with the closest real passages listed and nothing attributed (`LIMITATIONS.md` §1).

## 4. Module map (`backend/app/`)
| Package | Contents |
|---|---|
| `api/` | `health.py` (component readiness), `analyze.py` (POST /api/v1/analyze, timeout, user-safe errors), `info.py` (GET /api/v1/methodology, GET /api/v1/evaluation) |
| `core/` | `config.py` (settings + `production_problems()`), `errors.py` (error codes, bilingual messages), `middleware.py` (request id + security headers, body limit, rate limit) |
| `llm/` | `base.py` (LLMProvider, errors, usage), `anthropic_provider.py`, `gemini_provider.py`, `test_doubles.py`, `factory.py`, `cost.py` |
| `prompts/` | `claim_analysis_v1.{system,user,retry}.txt` |
| `corpus/` | `quran.py` (KFGQPC ingestion), `hadith.py` (canonical JSONL importer), `fts.py`, `validation.py`, `common.py` |
| `db/` | `schema.sql`, `connection.py` |
| `repositories/` | `corpus.py`: approval-filtered lookups, neighbours, BM25 and phrase queries |
| `schemas/` | `analyze.py` (API), `claim_analysis.py` (strict LLM output schema), `health.py`, `verification.py` (Phase 1 contracts) |
| `services/` | `normalizer`, `lexical_retriever`, `embeddings`, `semantic_retriever`, `rank_fusion`, `quote_matcher`, `source_resolver`, `context_expander`, `evidence_builder`, `content_level_router`, `evidence_gate`, `claim_analyzer`, `citation_verifier`, `grounding_verifier`, `safety`, `analysis_pipeline`, `types`, `text_diff` (quote comparison, 2026-10-03), `evidence_map` (map projection, 2026-10-03) |

Scripts: `fetch_quran.py`, `ingest_quran.py`, `ingest_hadith.py`, `build_fts.py`, `validate_corpus.py`, `build_embeddings.py`, `build_corpus.py` (all steps). Evaluation: `eval/compare_retrieval.py`.

## 5. Implemented
Phase 1: health endpoint, settings, contracts, protocols, minimal RTL page.
Phase 2: full data pipeline (`DATA_PIPELINE.md`), BM25 + LSA vector retrieval with lexical_first fusion, deterministic quote matching and source resolution, Quran context windows, evidence objects, `/api/v1/analyze` with degraded LEXICAL_ONLY mode, RTL UI showing status, source, canonical text in context and evidence. 

Phase 4: production hardening (`SECURITY.md`): pure-ASGI middleware for request ids, security headers, body limit and per-IP rate limit; request timeout; safe JSON for 404/405/422/500; docs and OpenAPI disabled in production; CORS restricted to https origins; production refuses test doubles, hash embeddings, experimental paraphrase mode and non-production (fixture) corpora; `/health` reports database, corpus, lexical, semantic and LLM components. Frontend: three routes (`/`, `/methodology`, `/evaluation`), ten-section result, no-LLM message, corpus-derived demo examples sent through the real pipeline, WCAG 2.1 AA checked with axe-core. Deployment files: `Dockerfile`, `render.yaml`, `frontend/netlify.toml` (`DEPLOYMENT.md`).

Multi-source (2026-10-02, pre-challenge, after the freeze tag): hadith corpus (Sahih al-Bukhari, Sahih Muslim via OpenITI/Shamela) with its own FTS index `hadith_fts`; `CorpusRepository(index=…)`; Quran-first routing with a deterministic strength rule (`_strength_rank`); hadith matcher without spans; context per source type; `source_type` on sources, units and evidence; `terms` table and `services/terminology.py`; validation V14–V16; gate blocks LLM analysis for non-Quran sources; grounding verifier checks both indexes. Schema `source_type` now accepts quran, quran_translation, hadith, tafsir, commentary, aqeedah, fiqh, seerah, history, dawah, shubuhat, dictionary (only quran, hadith and dictionary have data; the dictionary terms are no longer looked up or shown since 2026-10-04).

Innovation features (2026-10-03, pre-challenge): after claim analysis the pipeline adds `quote_comparison` / `candidate_comparisons` (`services/text_diff.py`) and `evidence_map` (`services/evidence_map.py`) to the response; both read only the pipeline's own outputs and change none of them. Screenshot input is frontend-only (`frontend/src/ocr/`: `validate.ts`, `ocr.ts` with tesseract.js in a Web Worker, `segment.ts`, `ImageVerify.tsx`); the OCR worker, WebAssembly core and Arabic model are served by the site under `/ocr/` (Vite plugin in `frontend/vite.config.ts`). The backend has no upload route. Details: `METHODOLOGY.md` §12, `PRIVACY.md`.

Phase 3: content-level routing (A–D), evidence gate and evidence strength, provider-neutral LLM layer with Anthropic adapter (mock-tested only), versioned prompts, strict output schema, citation and grounding verifiers, safety service, single controlled retry, audit logging, token/cost telemetry, Phase 3 API fields, RTL UI separating Quran text, commentary and AI analysis. **Not validated with a real model** (no API key).

## 6. Data layout
| Path | Content | In git? |
|---|---|---|
| `data/raw/` | Verified KFGQPC package (fetched by `scripts/fetch_quran.py`) | No |
| `data/curated/` | Unused so far | — |
| `data/metadata/` | Provenance record and structural expectations | Yes |
| `data/indexes/` | SQLite DB (with FTS5), `lsa_model.npz`, `semantic.faiss`, `semantic_ids.json`, `semantic_meta.json` | No (built by `scripts/build_corpus.py`) |
| `frontend/public/fonts/` | KFGQPC Uthmanic Hafs font from the same verified package | Yes |

## 7. Corpus data model
Tables `sources`, `passages`, `context_links`, `corpus_info`, and FTS5 table `passages_fts(normalized_text, normalized_text_alt)` keyed by `passages.rowid_int`; FAISS row ↔ `rowid_int` via `semantic_ids.json`. Full field list in `DATA_PIPELINE.md` §2.
