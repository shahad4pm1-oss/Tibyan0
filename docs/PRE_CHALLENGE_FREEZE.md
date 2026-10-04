# Pre-challenge freeze

**Everything in this repository up to the tag `pre-challenge-freeze-2026-10-02` is PRE-CHALLENGE WORK.** It was done on 1–2 October 2026, before the official challenge period (4–6 October 2026). The Participant Guide allows a previous project to be used if its starting version and rights are documented, and states that only work completed during 4–6 October is evaluated. This file is that documentation. Nothing listed here was done during the challenge days, and it must not be presented as challenge-period work.

| Item | Value |
|---|---|
| Freeze date and time | 2026-10-02, 02:21 (Asia/Riyadh, UTC+03:00) |
| Product commit frozen | `1e285b34d1316412093ab7da08691b5b04af0539` (tag `phase4-product-ready-llm-pending`, committed 2026-10-02 02:15 +03:00) |
| Freeze commit | The commit tagged **`pre-challenge-freeze-2026-10-02`**. It only adds this file, restructures `BASELINE.md`, adds the challenge-period plan, and corrects one wording issue in `EVALUATION.md` / `METHODOLOGY.md`. No code, data or metric changes |
| Earlier tags (unchanged) | `baseline-empty`, `phase1-foundation`, `phase1-corrected`, `phase1-final`, `phase2-partial-hadith-blocked`, `phase2-corrected`, `phase3-partial-blocked-by-llm-access`, `phase3-live-validation-blocked`, `phase4-product-ready-llm-pending` |
| Rights | Code and documentation were created for this project in this repository, with AI coding assistance recorded as `Co-Authored-By` in each commit. Third-party content (KFGQPC Quran text and font) and software are listed with their terms in `LICENSES.md` |

## 1. Capabilities that already exist (pre-challenge)
**Phase 1: governance.** Requirement extraction and authority hierarchy, source policy, scientific/safety policy SP-01…SP-16, frozen scope, architecture, acceptance criteria, judging map, baseline record.

**Phase 2: corpus and retrieval.**
- Quran corpus acquired from the KFGQPC `UthmanicHafs_v2-0.zip` package with a pinned SHA-256 (`a7b0e559…bfebdfd72c`), via Quranpedia's `quran-text` repository (commit `87d7691a`); ingested into SQLite; 13 validation checks (V01–V13); runtime integrity digest.
- Search normalizer `norm-v1`; BM25 (SQLite FTS5); character n-gram TF-IDF + LSA + FAISS vector baseline (**not neural**); `lexical_first` ranking.
- Deterministic quote matcher (EXACT / PARTIAL / AMBIGUOUS / NOT_FOUND; PARAPHRASED reserved and disabled), source resolver, ±2-ayah context, evidence objects E1…En.

**Phase 3: AI reasoning and safety layer (built, tested only with test doubles).**
- Content-level router A–D, evidence gate, evidence strength, provider-neutral LLM layer with an Anthropic adapter, prompt `claim_analysis_v1`, strict output schema, citation verifier, grounding verifier, safety lint and finalizer, one controlled retry, audit logging with no user text, token/cost telemetry.
- Five relations: SUPPORTED, OVERSTATED, CONTRADICTED, INSUFFICIENT_EVIDENCE, REQUIRES_SPECIALIST.
- Evaluation harnesses for stability, grounded-vs-ungrounded and provider health (none run against a real model).

**Phase 4: product hardening.**
- No-LLM mode: «تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً», no verdicts, test doubles refused in production.
- API hardening: request ids, security headers, body limit, per-IP in-process rate limit, timeout, safe JSON errors, docs off and https-only CORS in production, `/health` with components, `/api/v1/methodology`, `/api/v1/evaluation`.
- Arabic RTL frontend: verification page with ten result sections, `/methodology`, `/evaluation`; four corpus-derived demo examples run through the real pipeline; responsive at desktop / tablet / phone; axe-core WCAG 2.1 AA checks.
- Performance benchmark, load test, real-corpus API E2E tests, Playwright browser E2E with screenshots.
- Deployment files (`Dockerfile`, `render.yaml`, `frontend/netlify.toml`, `_redirects`, `_headers`); docs `SECURITY`, `EVALUATION`, `DEPLOYMENT`, `OPERATIONS`.

## 2. Status at freeze
| Area | Status |
|---|---|
| Quran corpus | 6,236 ayat, corpus version `c1-kfgqpc-hafs-2.0u13`, validation passing, integrity digest OK. No human spot-check against the printed mushaf |
| Retrieval (dev seed 20261001 / held-out seed 777, 1,400 generated cases each) | lexical_first: Recall@1 0.9643 / 0.9750, Recall@5 0.9957 / 0.9993, MRR 0.9784 / 0.9854. BM25 only: Recall@1 0.9607 / 0.9686, Recall@5 0.9957 / 0.9964, MRR 0.9764 / 0.9810 |
| Source resolution | In the current source-resolution evaluation, no incorrect definitive attribution was produced. Retrieval itself is not perfect; the Recall@1, Recall@5 and MRR values above document the remaining misses. Cases are generated from the corpus, not real-world quotations. Non-Quran sentences: 30 / 30 NOT_FOUND |
| Backend tests | 310 passed, 1 skipped (live-LLM test, no key) |
| Browser E2E | 42 / 42 (14 scenarios × 3 viewports), no serious/critical axe-core findings |
| Safety tests | Guard-rail evaluation with **scripted test-double outputs**: 25 / 25 technical cases, 23 / 23 critical. Not model performance |
| Dependency audits | pip-audit: no known vulnerabilities; npm audit: 0 |
| Secret scan | Only known hex checksums in `data/metadata` flagged; no key anywhere |
| **Real LLM validation** | **NOT COMPLETED** (no API key; 0 real model calls) |
| **Deployment** | **NOT COMPLETED** (no hosting credentials; no live URL; Docker image not built, steps verified in a clean virtualenv) |
| **Specialist-reviewed gold cases** | **0** (3 candidates pending review). No classification accuracy / precision / recall / F1 computed |
| **Hadith corpus** | **NOT COMPLETED** (importer exists and is tested on synthetic fixtures only; no licensed Bukhari/Muslim data ingested) |
| **Neural embedding evaluation** | **NOT COMPLETED** (adapter exists; no neural model could be obtained or evaluated) |
| Approved tafsir / commentary | Not ingested |
| Public GitHub repository | Not created |
| Fixed Arabic messages (referral, abstention) | Drafts, not specialist-reviewed |

## 2b. Addendum: multi-source expansion after the freeze (2026-10-02, pre-challenge)
At the participant's request, the corpus was expanded on 2 October 2026 — after the freeze tag but still **before** the challenge period, so this is also pre-challenge work. It is recorded in `BASELINE.md` §12b and tagged `pre-challenge-multisource-2026-10-02`. Added: Sahih al-Bukhari (7,380 numbered entries) and Sahih Muslim (2,922) from Shamela editions via OpenITI; 10 terminology entries from the package (p.8). Still not completed: Dorar sources, tafsir, aqeedah, fiqh, history, Bayyinat, the Jamhara dictionary, real LLM validation, deployment, reviewed gold cases (0), neural embedding evaluation. The `Hadith corpus = NOT COMPLETED` line in §2 described the state at the freeze tag; it is now **PARTIAL** (Sahihayn numbered hadith only). A correction pass on the same day (BASELINE §12c, tag `pre-challenge-multisource-corrected-2026-10-02`) separated religious authority from dataset provenance, added hadith search normalization, kept 192 unnumbered Muslim narrations without numbers, renamed the 10 terms the Official Scientific Package Sample Glossary, and set hadith to LIMITED_PRODUCTION. Challenge-period work should be separated with `git log pre-challenge-multisource-corrected-2026-10-02..HEAD`.

## 3. What happens next
Work for 4–6 October is planned in `CHALLENGE_PERIOD_PLAN.md`. It has **not started**. All challenge-period work will be committed after the freeze tag so it can be separated from this baseline with `git log pre-challenge-freeze-2026-10-02..HEAD`.
