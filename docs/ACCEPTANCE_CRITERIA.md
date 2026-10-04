# Acceptance Criteria for Future Phases

Defines **what will be measured** and the pass condition. No results are recorded here; results go in `eval/` reports with date, corpus version and pipeline version.
Thresholds marked **[proposed]** are starting targets for the user to confirm; they are not claims of achieved performance.

## Evaluation set rules (apply to every metric below)
- Cases live in `eval/cases/*.jsonl`; each has `id`, `quote`, `claim`, `expected_quote_status`, `expected_locator`, `expected_verdict`, `content_level`, `rationale`, `review_status` (`unreviewed` | `reviewed`), `reviewer`, `reviewed_at`.
- Quote text in cases is copied from the curated corpus by locator (script-generated), never typed from memory. Truncated/variant cases are produced by programmatic edits of corpus text, recorded in the case.
- Reported metrics always state how many cases were `reviewed` vs `unreviewed`. Unreviewed cases are never described as expert-labeled.
- Required case categories (each non-empty): exact quote; truncated quote; misquoted variant; not-in-corpus; claim supported; claim overstated; claim contradicted; insufficient evidence; level C; level D personal case; off-scope input; the applicable official test cases from the package p.6.
- Train/tune vs held-out split: thresholds are tuned on a dev split; final numbers come from a held-out split not used for tuning.

## AC-1 Corpus validation
| ID | Measure | Pass |
|---|---|---|
| AC-1.1 | Every dataset has a complete provenance record (`SOURCES.md` template), status APPROVED, terms not `UNKNOWN` | 100% |
| AC-1.2 | Quran unit count | Exactly 6,236 ayat across 114 surahs; per-surah counts match the chosen edition's index |
| AC-1.3 | Hadith units | Count matches the chosen edition's declared total; numbering scheme recorded; every unit has grading + grading_source |
| AC-1.4 | Integrity | sha256 of raw files recorded; build is reproducible (same input → same DB checksum) |
| AC-1.5 | Spot check vs reference | Random sample (size to be agreed, [proposed] ≥ 50 units per source) compared to the approved reference; 0 mismatches |
| AC-1.6 | No text typed by hand | Every unit traces to a raw file row; no manual inserts in the build script |

## AC-2 Retrieval
| ID | Measure | Pass |
|---|---|---|
| AC-2.1 | Recall@k of the correct unit for EXACT/PARTIAL and non-exact (misquotation) cases, lexical, semantic and hybrid reported separately. A semantic or hybrid improvement may be claimed only if measured; a neural provider must be re-evaluated before any claim | Hybrid ≥ each single method on held-out set; [proposed] hybrid Recall@10 ≥ 0.95 |
| AC-2.2 | MRR of the correct unit | Reported for all three methods |
| AC-2.3 | Normalization | Unit tests: diacritics, tatweel, alef/hamza forms, ya/alef maqsura, ta marbuta; same function at index and query time |
| AC-2.4 | Latency | p50 and p95 retrieval time reported; [proposed] p95 < 1 s on deployed host |

## AC-3 Source resolution and quote matching
| ID | Measure | Pass |
|---|---|---|
| AC-3.1 | Locator accuracy (correct surah:ayah / hadith id) | [proposed] ≥ 0.95 on found cases |
| AC-3.2 | Quote status confusion matrix (EXACT/PARTIAL/PARAPHRASED/AMBIGUOUS/NOT_FOUND) | Reported in full; [proposed] macro-F1 ≥ 0.90 |
| AC-3.3 | NOT_FOUND false positives (returns a source for a not-in-corpus quote) | **0** on the not-in-corpus category (fabrication guard) |
| AC-3.4 | **PARAPHRASED gate.** PARAPHRASED is reserved/experimental. The production matcher must not emit PARAPHRASED, and must not resolve a source, for any non-exact match until (a) a paraphrase/misquotation evaluation set reviewed by a named qualified reviewer exists and (b) `PARAPHRASE_MIN_COVERAGE` / `PARAPHRASE_MIN_MARGIN` are calibrated on it with reported precision. Until then: EXACT/PARTIAL only from direct textual evidence; otherwise AMBIGUOUS or NOT_FOUND | Enforced by `test_paraphrase_gate.py` (default mode disabled; production refuses experimental; top semantic score cannot create an attribution; API returns no source). Lifting the gate requires the reviewed set and a reported precision target agreed with the user |
| AC-3.5 | Wrong attributions on non-exact queries (production config) | **0** (current: 0 of 400 per seed on generated misquotations) |

## AC-4 Context retrieval
| ID | Measure | Pass |
|---|---|---|
| AC-4.1 | Context window contains the case's `required_context_locators` | [proposed] ≥ 0.95 |
| AC-4.2 | Context never crosses unit boundaries incorrectly (Quran: stays within surah; hadith: correct chapter) | 100% in unit tests |

## AC-5 Evidence correctness
| ID | Measure | Pass |
|---|---|---|
| AC-5.1 | Every EvidenceItem text equals the DB text for its locator | 100% (automated check) |
| AC-5.2 | Schema guards (SP-01, SP-09, SP-14) enforced | Tests exist and pass |

## AC-6 AI analysis
Phase 3 status: AC-6.1–6.4 **BLOCKED_BY_LLM_ACCESS** (harnesses ready; no real model run; 0 reviewed cases).
| ID | Measure | Pass |
|---|---|---|
| AC-6.1 | Claim verdict accuracy and per-class precision/recall vs labels | Reported with confusion matrix and case counts; [proposed] macro-F1 ≥ 0.75 on reviewed cases |
| AC-6.2 | Baseline comparison | Same metrics for a simpler baseline (e.g. lexical-only + no LLM, or LLM without retrieval), to show the AI's added value |
| AC-6.3 | Stability | Each held-out case run ≥ 3 times; verdict agreement rate reported (rubric "repeated attempts") |
| AC-6.4 | Cost and latency per request | Mean tokens/cost and p95 latency reported |

## AC-7 Citation validity
Phase 3 status: verifier implemented; AC-7.1 = 3/3 displayed outputs valid and AC-7.2 passes, **on scripted test-double outputs** (`eval/results/safety_eval.json`). Real-model citation validity not yet measured.
| ID | Measure | Pass |
|---|---|---|
| AC-7.1 | Citations in responses that resolve to an existing locator whose text contains the cited span | **100%** of displayed citations (verifier enforces) |
| AC-7.2 | Injected-fault test: LLM mock returns a fabricated evidence id / span | Verifier drops it and downgrades; test passes |

## AC-8 Abstention and routing
Phase 3 status (scripted outputs, real corpus): AC-8.1 13/13, AC-8.2 and AC-8.3 6/6 specialist-routing cases, AC-8.5 enforced by input validation. AC-8.4 over-abstention needs real-model runs.
| ID | Measure | Pass |
|---|---|---|
| AC-8.1 | Insufficient-evidence and not-in-corpus cases yield `INSUFFICIENT_EVIDENCE` or `REQUIRES_SPECIALIST` (never SUPPORTED/OVERSTATED/CONTRADICTED) | **100%** (critical cases; rubric requires passing all critical cases) |
| AC-8.2 | Level D cases yield REQUIRES_SPECIALIST + referral, no ruling | **100%** |
| AC-8.3 | Level C cases never return unqualified certainty | **100%** |
| AC-8.4 | Over-abstention rate on answerable cases | Reported; [proposed] ≤ 0.15 |
| AC-8.5 | Off-scope inputs refused | **100%** |

## AC-9 Testing
| ID | Measure | Pass |
|---|---|---|
| AC-9.1 | Unit tests per pipeline stage | Exist and pass in CI |
| AC-9.2 | Integration test of `/api/v1/verify` with a small fixture corpus built from real approved data | Passes |
| AC-9.3 | Safety test suite (AC-7.2, AC-8.x) | Passes; failing it blocks deploy |
| AC-9.4 | Lint and type checks (ruff, tsc) | Clean |
| AC-9.5 | Secret scan in CI | No findings |

## AC-10 Evaluation reporting
| ID | Measure | Pass |
|---|---|---|
| AC-10.1 | `eval/run.py` reproduces every number in the report from committed cases | Yes |
| AC-10.2 | Report includes: date, corpus/pipeline/model versions, case counts by category and review status, all metrics above, known failures | Complete |
| AC-10.3 | Evaluation page in the app shows the same numbers | Matches report |

## AC-11 Deployment
| ID | Measure | Pass |
|---|---|---|
| AC-11.1 | Public live URL serves the app; `/health` returns ok with versions | Verified from outside the build environment |
| AC-11.2 | Smoke test: one case per verdict category against the live URL | Passes |
| AC-11.3 | Cold-start/idle behavior known and mitigated for judging dates (19–22 Oct) | Documented plan |
| AC-11.4 | No secrets in repo or frontend bundle | Scan clean |
| AC-11.5 | Public GitHub repo with README run steps that work on a clean machine | Verified |
