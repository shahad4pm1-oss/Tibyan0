# Judging Alignment Map

Source: Participant Guide pp.37 to 41 (final-stage criteria and 1–5 rubrics). No results are recorded here. Evidence will be collected per `ACCEPTANCE_CRITERIA.md`.

## 1. Technical quality and AI use — 25%
**Requires:** product runs stably; AI does a real job with a clear methodology. Rubric 3: completes the core scenario with appropriate AI. 4: works on varied test cases in scope, handles errors understandably. 5: results repeat stably, methodology and limits documented, verifiable improvement due to the chosen AI.
**Tibyan components:** retrieval (FTS5/BM25 + a vector-space LSA/FAISS baseline, not a neural model), deterministic quote matcher, claim analyzer (LLM over backend evidence only, strict schema, one controlled retry), citation and grounding verifiers, evidence gate, error handling and safe degradation, provider abstraction. Phase 3 evidence so far: 275 automated tests and 25/25 guard-rail cases with scripted outputs; **real-model results BLOCKED_BY_LLM_ACCESS**.
**Evidence to collect:** AC-2.1/2.2 (hybrid vs single methods; Phase 2 result: the LSA component did **not** improve retrieval over BM25 and plain RRF degraded it, so no retrieval-improvement claim is made, see `METHODOLOGY.md` §5); AC-6.1 vs AC-6.2 baseline (improvement due to AI, Phase 3); AC-6.3 repeated-run stability; AC-9 test suite; methodology page; error-case screenshots.

## 2. Benefit per track success criterion — 20%
**Requires:** clear improvement in the target task, backed by verifiable results for the target group. Rubric 3: tests a use case with a suitable metric and preliminary results. 4: reference comparison shows clear improvement with the measuring method shown. 5: improvement repeats across varied in-scope cases; results and limits documented.
Track criterion parts (see `OFFICIAL_REQUIREMENTS.md`):
| Part | Tibyan proof |
|---|---|
| S1 accuracy of verifying | AC-3 locator/quote-status accuracy, AC-6 verdict accuracy vs baseline |
| S2 source shown traceably | Source display with locator + edition + link (M17); AC-7.1 = 100% |
| S3 state of evidence shown | Quote status (EXACT/PARTIAL/AMBIGUOUS/NOT_FOUND; PARAPHRASED reserved), hadith grading, evidence highlighting (M18) |
| S4 supported vs needs verification/referral | Verdict set incl. INSUFFICIENT_EVIDENCE and REQUIRES_SPECIALIST; AC-8 |
**Evidence to collect:** per-category results on held-out cases; optional small task test with real users from the track audience (time and correctness with vs without Tibyan) — only if run; never estimated.

## 3. Reliability and scientific safety — 15%
**Requires:** sound content and sources; effective attribution, abstention, referral in mandatory cases. Rubric 3: passes **all critical cases**, meets acceptance in normal cases, attributed content. 4: also succeeds on diversity, conflict and missing-information cases with clear source tracing and feasible human review. 5: consistent across the full test set over repeated attempts; exposes its knowledge limits and errors and allows tracing their fixes.
**Tibyan components:** `SOURCES.md` governance, `SCIENTIFIC_POLICY.md` SP-01..SP-16 (implementation map §4b), content-level routing, evidence gate, citation and grounding verifiers, safety lint, level C/D routing (`AI_SAFETY.md`). Measured on scripted outputs: critical safety cases 23/23, required abstention 13/13, specialist routing 6/6.
**Evidence to collect:** AC-1 corpus validation; AC-7 and AC-8 (critical = 100%); official package p.6 cases in the eval set; reviewer sign-off counts; known-failures list in the eval report.

## 4. Innovation and added value — 15%
**Requires:** proven addition compared with **a specific alternative** or current practice. Rubric 4: comparison with a specific alternative shows valuable improvement. 5: testing proves clear advantage, with comparison limits stated.
**Tibyan components:** quote+claim context analysis (beyond existence/authenticity lookup).
**Evidence to collect:** documented comparison against a named alternative (e.g. existence-only lookup = our lexical-only baseline; or a manual workflow using an approved reference site) on the same cases, with limits stated. The presentation's "no tool in the market does this" claim is not used unless documented.

## 5. Beneficiary experience, communication, accessibility — 10%
**Requires:** target user completes the task and understands outputs in clear, respectful language suited to their background. Rubric 4: considers background, language and accessibility needs, explains errors and next step. 5: suitable user tests support usability and show improvements made from results.
**Tibyan components:** Arabic RTL UI; separated segment types (SP-03); fixed respectful templates (SP-12, SP-13); error messages with next step; example inputs; copy/share card; keyboard and screen-reader basics.
**Evidence to collect:** accessibility check results (automated tool + keyboard pass); any user tests actually run with counts and changes made.

## 6. Operational realism and completeness — 10%
**Requires:** what it takes to keep running after the challenge: cost, dependencies, content review. Rubric 3: approximate costs, dependencies, next step. 4: maintenance plan, content review, realistic responsibilities. 5: estimates backed by measurements, alternative for a critical dependency, practical adoption plan.
**Tibyan components:** SQLite + in-process FAISS (low cost); provider abstraction (alternative for the LLM/embedding dependency); versioned corpus.
**Evidence to collect:** AC-6.4 measured cost/latency per request; hosting cost; dependency and license register; content-review plan with responsible roles.

## 7. Presentation clarity and verifiability — 5%
**Requires:** panel can understand and verify the claims. Rubric 5: concise, organized, easy re-testing, clearly separates what was done from what is proposed.
**Tibyan components:** live demo with example inputs, public repo, reproducible eval (AC-10.1), versions shown in UI, `BASELINE.md` separating pre-challenge from 4–6 Oct work.
**Evidence to collect:** deck slide per claim → linked evidence; ≤ 2 min video; re-test instructions.
