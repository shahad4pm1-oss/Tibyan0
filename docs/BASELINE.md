# Baseline

This file separates two kinds of work:

- **Part A — PRE-CHALLENGE EXISTING WORK** (§1–12): everything done on 1–2 October 2026, before the official challenge period, frozen at tag `pre-challenge-freeze-2026-10-02` (`PRE_CHALLENGE_FREEZE.md`). None of it was done during 4–6 October.
- **Part B — WORK TO BE COMPLETED DURING THE OFFICIAL 4–6 OCTOBER CHALLENGE PERIOD** (§13): planned in `CHALLENGE_PERIOD_PLAN.md`; not started at freeze. Only Part B is challenge-period work (Participant Guide: only work done 4–6 October is evaluated; prior work may be used if its starting version and rights are documented).

To list challenge-period changes only: `git log pre-challenge-freeze-2026-10-02..HEAD`.

---

# PART A — PRE-CHALLENGE EXISTING WORK (1–2 October 2026)

## 1. State before Phase 1
**No repository, code, dataset, model, UI, backend, test or deployment was supplied.** Only three documents were provided (Participant Guide, Scientific Package, Tibyan presentation). The presentation describes a design; it contains no implementation.

Git: commit tagged **`baseline-empty`** is an empty commit recording this state.

| Item | Existed before Phase 1? |
|---|---|
| Source code (frontend/backend) | No |
| Datasets / corpus | No |
| Models / indexes | No |
| Tests | No |
| Deployment / live URL | No |
| Documentation | No (only the three supplied documents, not stored in the repo) |

## 2. Created in Phase 1 (2026-10-01, before the 4–6 Oct challenge window)
Disclosure for judging (Guide FAQ p.43: only work done 4–6 Oct is evaluated): everything below was done on **1 October 2026**, as preparation. It is governance, scaffolding and interfaces only. **No retrieval, corpus, AI analysis or verification logic exists.**

| Path | What |
|---|---|
| `docs/OFFICIAL_REQUIREMENTS.md` | Requirements extract, authority hierarchy, conflicts |
| `docs/SOURCES.md` | Source policy (APPROVED / PENDING_REVIEW / EXCLUDED_FROM_V1) |
| `docs/SCIENTIFIC_POLICY.md` | Safety rules SP-01..SP-16, content levels, verdict vocabulary |
| `docs/SCOPE.md` | Frozen V1 scope |
| `docs/ARCHITECTURE.md` | Stack, pipeline, module map |
| `docs/ACCEPTANCE_CRITERIA.md` | Measures and pass conditions (no results) |
| `docs/JUDGING_MAP.md` | Mapping to the 7 final criteria |
| `docs/BASELINE.md` | This file |
| `backend/app/main.py`, `api/health.py`, `schemas/health.py` | `GET /health` |
| `backend/app/core/config.py` | Settings from env |
| `backend/app/schemas/verification.py` | Pydantic contracts with policy guards (types only) |
| `backend/app/core/interfaces.py` | Stage and provider protocols (no implementations). Removed 2026-10-02 (unused since Phase 2) |
| `backend/tests/` | 5 tests: health + schema guards |
| `backend/requirements*.txt`, `pyproject.toml` | Dependencies |
| `frontend/` | Minimal Vite + React + TS + Tailwind RTL page calling `/health` |
| `.env.example`, `.gitignore`, `README.md` | Env and secret policy, run steps |
| `data/`, `scripts/`, `eval/`, `tests/` | Empty placeholders |

## 3. Verified in Phase 1
- Backend deps installed in a venv (Python 3.11.15); `pytest`: 5 passed; `ruff`: clean.
- SQLite 3.45.1 in the environment supports FTS5 (checked).
- Frontend deps installed; `npm run build` (tsc + vite) succeeded.
- Uvicorn served `/health`; the built frontend in headless Chromium rendered RTL and displayed the health response via CORS.

## 4. Known issues
- `fastapi.testclient` emits a Starlette deprecation warning about `httpx`; harmless in Phase 1; revisit when upgrading.
- The build container was reset once during Phase 1; the repository was re-initialized and all files recreated. No earlier work exists outside this repository.
- Nothing is deployed. No corpus. No AI provider chosen.

## 5. Phase 1 corrections (2026-10-01, after user review)
Documentation corrections only; architecture and scope unchanged. Phase 1 remains PASS.
1. **Tafsir sources.** Earlier wording said Tafsir al-Saadi and Tafsir Ibn Kathir were "rejected". Corrected: they are not automatically approved as standalone production sources merely because the presentation lists them. Any tafsir use must comply with the official package (official source scope or dorar.net/tafseer). They moved from EXCLUDED_FROM_V1 to PENDING_REVIEW in `SOURCES.md`. IslamQA stays excluded because the package does not list it as an approved source.
2. **Verdict labels.** Earlier wording said "مضلِّل" was dropped because the package forbids judging persons. That reasoning was imprecise and is withdrawn. The labels are now `SUPPORTED`, `OVERSTATED`, `CONTRADICTED`, `INSUFFICIENT_EVIDENCE`, `REQUIRES_SPECIALIST`, chosen for clarity and measurability. They describe the claim–evidence relationship, not a person. `UNCLEAR` became `INSUFFICIENT_EVIDENCE` and `SPECIALIST_REVIEW` became `REQUIRES_SPECIALIST`, in the docs and in the `ClaimVerdict` enum (rename only).

## 6. Phase 2 readiness (2026-10-01, set by user review)
**PHASE 2 READINESS: READY.**

READY — real production corpus ingestion may remain blocked until a specific officially compliant Quran dataset/edition and its provenance/reuse status are resolved. However, Phase 2 can and should begin by resolving that data source, building the ingestion/validation pipeline, database, retrieval components, and using clearly marked synthetic NON-RELIGIOUS fixtures wherever real religious data is temporarily unavailable.

Not blockers for starting Phase 2 (needed in later phases): LLM provider choice; embedding provider API key; sharia reviewer; public GitHub account; hosting account.

This supersedes the "NOT READY" readiness line in the original Phase 1 report and the "READY FOR PHASE 2: NO" line in the corrections report. No other Phase 1 decision changes.

## 7. Phase 2 (2026-10-01, before the 4–6 Oct challenge window)
Disclosure for judging: like Phase 1, this work was done on **1 October 2026**, before the evaluated window (Guide FAQ p.43). Starting point: tag `phase1-final`.

**Built:** data acquisition with hash verification; canonical SQLite schema; Quran ingestion; hadith importer (synthetic fixtures only); 13-check corpus validation; FTS5/BM25 retrieval; embedding provider abstraction with a local LSA model; FAISS index; RRF and lexical_first fusion; retrieval comparison on generated known-answer cases; deterministic quote matcher and source resolver; context expander; evidence builder; `POST /api/v1/analyze` with user-safe errors and LEXICAL_ONLY degraded mode; RTL UI for Phase 2 results; 126 automated tests; docs `DATA_PIPELINE.md`, `METHODOLOGY.md`, `LICENSES.md`.

**Real data:** Quran, KFGQPC `UthmanicHafs_v2-0.zip` (SHA-256 `a7b0e559…bfebdfd72c`), 6,236 ayat, corpus version `c1-kfgqpc-hafs-2.0u13`. **Synthetic data:** test fixtures and NOT_FOUND evaluation sentences only (non-religious, labelled); never in the production index.

**Not built (Phase 3):** scope/safety gate, evidence gate, claim analysis, verdicts, LLM citation verification.

**Open items:** KFGQPC terms not yet read on the official site (secondary quote only); no human spot-check of the text against the printed mushaf; real Bukhari/Muslim data (REAL_HADITH = BLOCKED_BY_DATA); semantic model is classical LSA (no neural model obtainable in the build environment) and showed no measured benefit; matching thresholds uncalibrated.

## 8. Phase 2 corrections (2026-10-01, after user review)
Phase 2 remains PASS for the Quran retrieval foundation. The canonical Quran text is unchanged (same `original_text` digest).
1. **Provenance and reuse.** Documentation now separates three layers: KFGQPC (underlying text), Quranpedia / Quran.ws (distribution path), and the actual acquisition route (`quranpedia/quran-text` commit `87d7691a` via raw.githubusercontent.com). The Quranpedia dump policy (dump version 2026-09-30, LICENSE.md 2026-10-01) is the primary reuse reference for the distribution path. No quranpedia.net dump file was used. KFGQPC's usage rights are now cited from the full reproduction in the quran-text LICENSE, which replaces the earlier "secondary quote" wording in §7. Reuse status: PERMITTED_FOR_IN_APP_USE; republication attribution rules recorded.
2. **PARAPHRASED reserved.** New `PARAPHRASE_MODE` (default `disabled`, `experimental` refused in production). Non-exact matches now return AMBIGUOUS (`NEAR_MATCH_UNCONFIRMED`) with closest passages listed and nothing attributed. 9 new tests.
3. **Semantic wording.** The semantic component is described everywhere as character n-gram TF-IDF + LSA + FAISS, not a neural embedding model, with the measured finding that it did not improve retrieval.

## 9. Phase 3 (2026-10-01, before the 4–6 Oct challenge window)
Disclosure for judging: done on **1 October 2026**, before the evaluated window. Starting point: tag `phase2-corrected`. Retrieval foundation unchanged (metrics identical to Phase 2).

**Built:** LLM provider layer (`app/llm/`: Anthropic Messages API adapter over HTTP, scripted and abstaining test doubles, factory, cost), versioned prompts, strict output schema, content-level router (A–D), evidence gate and evidence strength, claim analyzer with one controlled retry, citation verifier, grounding verifier, safety service, audit logging and token/cost telemetry, Phase 3 API fields, Phase 3 RTL UI, evaluation case schema with 25 technical cases and 3 pending candidate cases, guard-rail evaluation, stability and grounded-vs-ungrounded harnesses. Tests: 275 passing (+1 live test skipped).

**Contract change:** `claim_analysis` in `/api/v1/analyze` replaces the Phase 2 placeholder (`NOT_IMPLEMENTED_PHASE_2`); one Phase 2 test assertion was updated accordingly.

**Not done:** any real LLM call (no API key: BLOCKED_BY_LLM_ACCESS); stability and grounded-vs-ungrounded runs; specialist review of any case or fixed message.

Defect found and fixed during Phase 3 verification: under a real uvicorn server the audit logger had no handler, so audit lines were silently dropped (tests passed only because pytest captures records directly). `configure_logging()` in `app/main.py` now attaches Tibyan's own handler; a regression test exercises that handler, and a live server run confirmed one audit line per request with no user text.

## 10. Real-LLM validation attempt (2026-10-01 21:49 KSA)
Requested: validate Phase 3 against a real provider using credentials from environment variables. Result: **BLOCKED_BY_LLM_ACCESS**. No `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` (or other provider key) is set and no `.env` exists. Credentials belonging to the build tooling are not project credentials and were not used. `eval/provider_health.py` (minimal one-call health check through the existing adapter) was added and run: `status: BLOCKED_BY_LLM_ACCESS, reason: LLM_PROVIDER not set` (`eval/results/provider_health.json`). Per instructions, real-model testing stopped at this step; no real-model results exist. Phase 3 stays PARTIAL.

## 11. Phase 4 (2026-10-01/02, before the 4–6 Oct challenge window)
Disclosure for judging: done on 1–2 October 2026, before the evaluated window. Starting point: tag `phase3-live-validation-blocked`. Retrieval and guard-rail metrics unchanged (re-run, identical apart from timestamps).

**Built:** API hardening (request ids, security headers, body limit, per-IP rate limit, request timeout, safe JSON errors, docs/OpenAPI off and https-only CORS in production, production refusal of test doubles, hash embeddings, experimental paraphrase mode and fixture corpora, `/health` components and `config_problems`); `GET /api/v1/methodology` and `GET /api/v1/evaluation`; no-LLM message «تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً»; final RTL UI with ten result sections and three routes (`/`, `/methodology`, `/evaluation`); corpus-derived demo examples (`scripts/make_demo_examples.py`, inputs only); performance benchmark, load test and test-suite collector; real-corpus API E2E tests (13); Playwright browser E2E with axe-core (42 checks, 3 viewports) and screenshots in `docs/screenshots/`; `Dockerfile`, `render.yaml`, `frontend/netlify.toml`, `_redirects`, `_headers`; docs `SECURITY.md`, `EVALUATION.md`, `DEPLOYMENT.md`, `OPERATIONS.md`. Pipeline version `0.4.0-phase4`. Tests: backend 310 passed, 1 skipped (live LLM).

**Not done:** real LLM validation (PENDING: no API key); deployment (no hosting credentials, no live URL); Docker image build (Docker Hub blocked; build steps verified in a clean virtualenv instead, producing a byte-identical DB); specialist review of cases and fixed messages; screen-reader user testing.

**Status:** REAL LLM VALIDATION = PENDING. FINAL COMPETITION READINESS = NOT YET COMPLETE.

## 12. Pre-challenge freeze (2026-10-02 02:21 KSA)
Product frozen at commit `1e285b3` (tag `phase4-product-ready-llm-pending`). The freeze commit (tag `pre-challenge-freeze-2026-10-02`) adds `PRE_CHALLENGE_FREEZE.md` and `CHALLENGE_PERIOD_PLAN.md`, restructures this file into Part A / Part B, and corrects one wording issue: the source-resolution result is now stated as "no incorrect definitive attribution was produced" in the current evaluation, with the retrieval metrics (Recall@1, Recall@5, MRR below 1.0) documenting the remaining misses. No code, data or metric changed.

Not completed before the challenge: real LLM validation, deployment, specialist-reviewed gold cases (0), hadith corpus, neural embedding evaluation, public GitHub repository.

## 12b. Post-freeze pre-challenge work: multi-source expansion (2026-10-02, still before the 4–6 Oct challenge period)
Requested by the participant after the freeze tag; done on **2 October 2026**, before the official challenge period, so it is **pre-challenge work** too. It is committed after `pre-challenge-freeze-2026-10-02` and tagged separately (`pre-challenge-multisource-2026-10-02`); the freeze tag is unchanged and still marks the Phase 4 state.

**Built:** hadith corpus from Sahih al-Bukhari (7,380 numbered entries) and Sahih Muslim (2,922) — Shamela editions via OpenITI, SHA-256 pinned (`scripts/fetch_hadith.py`, `app/corpus/openiti_hadith.py`, `app/corpus/sahihayn.py`); separate hadith FTS index; Quran-first multi-source routing; per-source context; source type on all results; grading recorded from the package's Sahihayn rule (never generated); LLM analysis gated to Quran results; grounding verifier over both indexes; terminology samples from the package p.8 (`terms` table, verified against the PDF); validation V14–V16 and a pinned Quran digest; UI source badges, hadith rendering distinct from Quran, terminology block, methodology/evaluation pages; `eval/multi_source_eval.py`; 8 new test files; docs `OFFICIAL_SOURCE_INVENTORY.md`, `CORPUS_COVERAGE.md`.

**Unchanged:** the Quran text (digest equals the Phase 2 pin), Quran FTS rows, LSA model and FAISS index (byte-identical), and the Quran retrieval regression.

**Blocked (not integrated):** Dorar hadith/tafseer/aqeeda/feqhia/history (dorar.net unreachable; no dataset or bulk-reuse terms found), Bayyinat (dawa.center unreachable; «all rights reserved»), Jamhara dictionary and islamic-content.com / dawa.center content (unreachable; personal non-commercial terms), Quran translations, other Sunnah books.

## 12c. Multi-source correction pass (2026-10-02, pre-challenge)
- Sahihayn: religious authority (approved by the package) documented separately from dataset provenance (OpenITI files; cross-check against Shamela/Dorar PENDING; printed-edition reuse PENDING VERIFICATION).
- Hadith search normalization `hnorm-v1` (NFKC, honorific formulas removed, search only) and verbatim-first candidate ranking; measured before/after on identical cases (`EVALUATION.md` §1b). Display text unchanged.
- 192 Sahih Muslim narrations unnumbered in the file kept with `hadith_number = null` and a book/chapter locator; no number invented.
- The 10 terms are named the Official Scientific Package Sample Glossary (records = 10), not the Jamhara dictionary. (Later change, 2026-10-04: the glossary was removed from the product; this section records the state at the time.)
- Hadith status set to **LIMITED_PRODUCTION**, shown in the UI and API.
- Quran corpus, indexes and metrics unchanged.

---

# PART B — WORK TO BE COMPLETED DURING THE OFFICIAL 4–6 OCTOBER CHALLENGE PERIOD

## 13. Challenge period (4–6 October 2026)
**Not started at freeze.** Plan: `CHALLENGE_PERIOD_PLAN.md` (real LLM integration and validation, real-model safety and stability, grounded-vs-ungrounded evaluation, real token/latency/cost, fixes from real-model testing, specialist review where available, production deployment, live-demo validation, public GitHub preparation, final UX fixes, final measurable evaluation, final documentation and submission). Completed work will be recorded here, with dates, only after it happens.

## 12d. Local runnability consolidation (2026-10-02, pre-challenge)
One-command local run: `setup.ps1` / `start.ps1` / `stop.ps1` (+ `.cmd` launchers, `setup.sh` / `start.sh` / `stop.sh`), `scripts/sanity_check.py`, pinned `backend/constraints.txt`, `.env` read from the repository root (any working directory), Windows-safe SQLite paths, `/health` with Quran/hadith/glossary/FTS components, app version and `llm_mode` (REAL_LLM / LLM_UNAVAILABLE). Docs `RUN_LOCAL.md`, `LOCAL_DATA_MANIFEST.md`. Removed two unused placeholders (`backend/app/core/interfaces.py`, empty top-level `tests/`). No retrieval, safety or data behaviour changed; tag `tibyan-runnable-local-v1`.
