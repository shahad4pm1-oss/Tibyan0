# Evaluation (as of Phase 4, 2026-10-01)

Every number here is read from a file in `eval/results/` produced by a script in `eval/`. Rerunning the script reproduces it (timings vary by machine). The `/evaluation` page and `GET /api/v1/evaluation` show the same files and nothing else.

**What is NOT measured (read this first)**
- **Real LLM claim analysis: PENDING real-model validation.** No real model has been called (no API key). There are no numbers for classification quality, stability, real-model injection resistance, latency or cost of claim analysis. `eval/results/provider_health.json`, `stability.json` and `grounded_vs_ungrounded.json` record `BLOCKED_BY_LLM_ACCESS`.
- **Religious classification accuracy / precision / recall / F1: not computed.** Reviewed gold cases: 0 (3 candidates pending a qualified reviewer). No such number may be reported until reviewed cases exist.
- Latency or capacity on a production host (not deployed), user comprehension, true paraphrases, real-world misquotations, hadith.

## 1. Retrieval and quote matching (`eval/compare_retrieval.py`)
Cases are generated from the corpus itself (exact Uthmani, exact imla'i, partial, formatting noise, multi-ayah spans, one-word substitution, one-word deletion; 200 per category). They test finding the right location, not understanding meaning.

| Ranking (dev seed 20261001 / held-out seed 777, 1,400 cases each) | Recall@1 | Recall@5 | MRR |
|---|---|---|---|
| BM25 only | 0.9607 / 0.9686 | 0.9957 / 0.9964 | 0.9764 / 0.9810 |
| lexical_first (production) | 0.9643 / 0.9750 | 0.9957 / 0.9993 | 0.9784 / 0.9854 |
| RRF, LSA-only and others | worse; see `METHODOLOGY.md` §5 | | |

Production matching outcome (dev / held-out): 967 / 960 resolved to the correct location; 33 / 40 repeated texts correctly left unattributed; 400 / 400 near-misquotations not attributed with the true source listed; 0 / 0 definitive attributions to a wrong location; 0 / 0 cases in the outcome class "missed" (true source neither resolved nor listed). Non-Quran sentences: 30 / 30 returned NOT_FOUND.

In the current source-resolution evaluation, no incorrect definitive attribution was produced. Retrieval itself is not perfect; the measured Recall@1, Recall@5 and MRR values document the remaining misses. These are generated cases from the corpus itself, not real-world quotations.

**Phase 4 regression:** both runs were repeated after all Phase 4 changes; every metric is identical to the committed Phase 3 files (only timestamps differ).

## 1b. Multi-source (`eval/multi_source_eval.py`; before: `multi_source_eval_before_hnorm.json`, after: `multi_source_eval.json`, 2026-10-02)
Measured per source type; no combined score. Cases are generated from the hadith texts themselves (seed 20261002, 200 per category, numbered records only), identical before and after the correction pass. "Before" = hadith indexed with the Quran normalization (norm-v1); "after" = `hnorm-v1` plus verbatim-hit candidates (METHODOLOGY §11).

**BM25 alone (`hadith_fts`)** — Recall@1 / Recall@5 / MRR, before → after

| Category | Recall@1 | Recall@5 | MRR |
|---|---|---|---|
| verbatim slice (6–12 words) | 0.675 → 0.705 | 0.860 → 0.865 | 0.762 → 0.775 |
| one word substituted | 0.690 → 0.705 | 0.890 → 0.890 | 0.779 → 0.789 |
| two words deleted | 0.675 → 0.690 | 0.880 → 0.890 | 0.766 → 0.781 |
| «صلى الله عليه وسلم» written as ﷺ | 0.780 → 0.780 | 0.940 → 0.955 | 0.854 → 0.860 |
| honorific omitted | 0.795 → 0.795 | 0.980 → 0.985 | 0.878 → 0.880 |

**Production ranking (verbatim phrase hits first, then BM25)** — before → after

| Category | Recall@1 | Recall@5 | MRR |
|---|---|---|---|
| verbatim slice | 0.955 → 0.955 | 0.955 → 0.995 | 0.955 → 0.969 |
| one word substituted | 0.690 → 0.705 | 0.890 → 0.890 | 0.777 → 0.789 |
| two words deleted | 0.675 → 0.700 | 0.880 → 0.895 | 0.764 → 0.786 |
| written as ﷺ | 0.780 → 0.995 | 0.940 → 1.000 | 0.852 → 0.998 |
| honorific omitted | 0.795 → 0.955 | 0.980 → 0.995 | 0.877 → 0.975 |

**Full pipeline outcome (after):** verbatim slices — 130 resolved to the right hadith, 67 left unattributed because the text recurs verbatim in several hadith, 3 resolved to the Quran (the slice is an ayah quoted in the hadith); ﷺ slices — 161 resolved, 39 repeated-text unattributed (before: 0 resolved, 191 near matches, 6 not found); honorific-omitted slices — 139 resolved, 34 repeated-text unattributed, 27 near matches not attributed (before: 0 resolved); edited slices (substitution/deletion, 400) — 368 near matches not attributed, 4 resolved to the generating hadith, 1 to another hadith that contains the edited text verbatim, 4 not found, 23 near matches without the source listed. **Wrong attributions (resolved passage does not contain the query): 0 before, 0 after.** Quran cases through the full multi-source pipeline: 200 / 200 resolved or listed within the Quran, 0 attributed to a hadith. Non-religious sentences: 30 / 30 NOT_FOUND. Glossary samples: 30 / 30 exact lookups correct, 0 false hits on the 30 non-religious sentences.

What this does not show: BM25 alone remains modest on hadith (long texts, shared isnad vocabulary); edited quotes are deliberately not attributed; no real user hadith quotations were tested. Hadith search is therefore **LIMITED_PRODUCTION**.

Not measured: tafsir, aqeedah, fiqh, history, da'wah and shubuhat (not ingested); claim analysis on hadith (disabled).

**Quran regression:** `compare_retrieval.py` for both seeds and the guard-rail evaluation are identical to the Phase 4 tag (only timestamps and the corpus label differ); Quran FTS rows, LSA model and FAISS index are byte-identical, and the Quran text digest equals the Phase 2 pin.

## 2. Guard rails with scripted model outputs (`eval/run_safety_eval.py`)
**Not model performance.** A scripted test double returns fixed outputs (good, malformed, hallucinated, injected) to check that the verifiers and safety layer reject what they should.

| Check | Result |
|---|---|
| All technical cases | 25 / 25 |
| Critical safety cases | 23 / 23 |
| Required abstention | 13 / 13 |
| Specialist routing | 6 / 6 |
| Prompt-injection defence (structural) | 5 / 5 |
| Hallucinated citation rejection | 6 / 6 |
| Safe degradation on LLM failure | 3 / 3 |
| Citation validity of displayed outputs | 3 / 3 |
| Outputs rejected by verifiers | 21 |

Phase 4 regression: identical to Phase 3.

## 3. Automated tests (`eval/collect_test_suite.py` → `test_suite.json`)
- **Current (2026-10-03, after the text comparison, evidence map and screenshot input):** backend `pytest` 426 passed, 1 skipped (the live-LLM test); browser E2E 45 scenarios × 3 viewports = 135 runs, 119 passed, 0 failed, 16 skipped by design (desktop-only or mobile-only scenarios); segmentation unit tests (`npm run test:unit`) 14 passed. New: `test_text_diff.py` (18), `test_evidence_map.py` (10), `test_no_image_upload.py` (6), `e2e/screenshot.spec.ts` (15 scenarios), 4 new scenarios in `e2e/app.spec.ts` (diff, evidence map ×2, hadith diff). The axe helper now waits for finite animations and transitions before measuring contrast (it had produced intermittent false positives mid-fade). The history below is kept as it was recorded.
- Backend `pytest`: 362 passed, 1 skipped (the live-LLM test, skipped without a key) as of the 2026-10-02 correction pass, including the multi-source tests (hadith ingestion and grading, honorific normalization, unnumbered Muslim narrations, glossary, multi-source retrieval, routing, source authority, context, no cross-source attribution). Includes `test_api_hardening.py` (API hardening) and `test_e2e_api_real.py` (API flows on the real corpus with production settings and no LLM).
- Browser E2E (Playwright, Chromium), after the premium UI redesign (tag `tibyan-premium-ui-v1`): 26 scenarios × 3 viewports (desktop 1280×900, tablet 820×1180, mobile 390×844) = 78 checks; 72 passed, 0 failed, 6 skipped by design (mobile-menu runs on mobile only; copy actions and the six-width sweep run on desktop only). Scenarios: home (hero, empty state), hero CTA focus, validation, example fills the form, Quran exact (report order, Quran font, no-LLM message, no AI panel), partial (preceding / matched / following context), ambiguous, not found (next steps), hadith (Naskh, never the Quran font, source card, no verdict), saying absent from the sources, personal-fatwa specialist panel, terminology, staged loading, server errors 500/503/429, network failure, methodology, evaluation, sources, navigation and footer links, mobile menu dialog, theme toggle (dark mode applied, persisted, axe in dark), system dark preference, copy actions, and no horizontal scroll / no text under 12px at 375, 390, 430, 768, 1024 and 1440 px. Every page and result state, in light and dark mode, is scanned with axe-core (WCAG 2.0/2.1 A and AA): no serious or critical violations. Screenshots: `docs/screenshots/redesign/`.

## 4. Performance without an LLM (`eval/perf_benchmark.py` → `performance.json`)
330 queries sampled from the corpus with seed 4242 (half full ayat, half 4-word excerpts, plus non-Quran sentences). Development container, single process, Python 3.11. Milliseconds.

| Stage | avg | p50 | p95 |
|---|---|---|---|
| DB lookup (one passage) | 0.03 | 0.02 | 0.05 |
| BM25 search (FTS5) | 4.29 | 3.92 | 10.12 |
| Semantic search (LSA + FAISS) | 1.32 | 1.23 | 1.78 |
| Fusion + matching + resolution | 1.00 | 0.36 | 5.74 |
| Context expansion | 0.12 | 0.12 | 0.19 |
| Whole pipeline, no LLM | 8.89 | 6.60 | 29.53 |
| Full HTTP request, no LLM (in-process client) | 11.27 | 8.33 | 34.31 |

Re-measured 2026-10-02 after the multi-source expansion: the stage rows cover the Quran search path; the whole-pipeline rows include the hadith search that runs when the Quran gives no verbatim match (hence the higher p95).

With an LLM configured, the model call would dominate; that time is not measured.

## 5. Load test (`eval/load_test.py` → `load_test.json`)
400 requests per round against one uvicorn worker on loopback, rate limit disabled for the run, no LLM.

| Concurrency | Succeeded | p50 ms | p95 ms | req/s |
|---|---|---|---|---|
| 1 | 400 / 400 | 8.0 | 15.6 | 111.7 |
| 10 | 400 / 400 | 110.7 | 190.3 | 91.4 |
| 25 | 400 / 400 | 335.5 | 602.0 | 73.2 |

Server memory (RSS): 186.3 MB before, 202.3 MB after (2026-10-02 run). No errors; throughput drops under concurrency because the CPU-bound pipeline shares one Python process. Not a production-host capacity claim.

## 5b. Text comparison, evidence map and screenshot input (2026-10-03)
**No change to verification results.** After the three additions, `compare_retrieval.py` (seeds 20261001 and 777), `multi_source_eval.py` and `run_safety_eval.py` were re-run on a clean copy of the commit and compared field by field with the committed result files (timings excluded): **0 differences in all four**. Quran production retrieval stays Recall@1 0.9643 / 0.9750 (dev / held-out); hadith and safety results are unchanged.

**Pipeline cost of the comparison and the map** (`perf_benchmark.py`, same 330 queries, two runs each, ms):

| | p50 before | p50 after | p95 before | p95 after |
|---|---|---|---|---|
| Whole pipeline, no LLM | 8.8 / 9.5 | 9.6 / 9.7 | 37.1 / 37.7 | 37.9 / 36.9 |
| Full HTTP request, no LLM (in-process) | 11.8 / 11.6 | 13.3 / 13.0 | 40.9 / 40.8 | 42.4 / 42.0 |
| BM25 search (unchanged code; run-to-run noise) | 4.8 / 5.3 | 5.3 / 5.0 | 10.7 / 12.4 | 13.5 / 12.2 |

About +0.5 ms per pipeline call and +1.4 ms per HTTP request at the median (larger JSON response). Development container; not a production-host figure.

**Frontend bundle** (`vite build`): main JS 325.6 → 373.5 kB (gzip 97.5 → 112.8 kB); CSS 78.8 → 92.4 kB (gzip 21.3 → 23.3 kB). The OCR code is a separate 17.2 kB chunk loaded only when an image is processed; the OCR engine and Arabic model (≈ 5.6 MB: worker 0.11 MB, one WebAssembly core 3.9 MB, model 1.66 MB) are fetched from the site only then.

**Screenshot OCR latency** (production build in headless Chromium on the development container; from choosing the file to the review panel, engine start included; 1 cold + 5 warm runs per image, warm median):

| Image (drawn from `src/examples.json` quotes) | first | median |
|---|---|---|
| clear quote, 900×156 | 904 ms | 853 ms |
| small 15 px text, 520×137 | 851 ms | 829 ms |
| quote + claim, 900×251 | 839 ms | 837 ms |
| phone-sized post, 1170×2000, 16 lines | 2,428 ms | 2,407 ms |

**OCR accuracy is not reported as a metric.** The browser tests check that the drawn quotes are read word for word, ignoring diacritics and alef / hamza-seat forms (clear, multi-line, several quotes, quote + claim), or with at least 70% of words in place (small, dark, noisy), before the visitor's review; these are synthetic images, not real screenshots (`LIMITATIONS.md` §16).

## 6. How to reproduce
```bash
backend/.venv/bin/python eval/compare_retrieval.py --seed 777 && mv eval/results/retrieval_comparison.json eval/results/retrieval_comparison_heldout_seed777.json
backend/.venv/bin/python eval/compare_retrieval.py
backend/.venv/bin/python eval/run_safety_eval.py
backend/.venv/bin/python eval/perf_benchmark.py
RATE_LIMIT_PER_MINUTE=0 backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000 &
backend/.venv/bin/python eval/load_test.py --pid <uvicorn pid>
(cd frontend && npm run build && npx vite preview --port 4173 &) ; (cd frontend && npx playwright test)
(cd frontend && npm run test:unit)       # screenshot text segmentation
backend/.venv/bin/python eval/collect_test_suite.py
```
Once an LLM key exists: `eval/provider_health.py` first, then `eval/stability.py` and `eval/grounded_vs_ungrounded.py`; a real-model result file named `eval/results/live_llm_eval.json` replaces the "pending" status on the evaluation page.
