# Methodology (retrieval, matching, context, evidence, claim analysis)

**The language model is not a source of Islamic information.** All religious text comes from the approved corpus; the model (when configured) only classifies the claim against that evidence. As of Phase 4 no real model has been run (REAL LLM VALIDATION = PENDING), and the product runs without one (`§9`, `LIMITATIONS.md` §7).

Status: §1–8 describe Phase 2 retrieval and matching; §9 describes Phase 3 claim analysis; the full list of measured numbers is in `EVALUATION.md`. Every number below comes from `eval/results/*.json` produced by `eval/compare_retrieval.py`; rerunning the script reproduces them.

## 1. What the system does now
Given an Arabic quote (and a claim that is stored but not analysed), Tibyan:
1. normalizes the quote for search only;
2. retrieves candidates with BM25 (FTS5) and dense vectors (FAISS);
3. decides deterministically whether the quote is EXACT, PARTIAL, AMBIGUOUS or NOT_FOUND (PARAPHRASED is reserved and disabled in production);
4. resolves the source (RESOLVED / AMBIGUOUS / NOT_FOUND) by re-reading the passage from the approved corpus;
5. returns the canonical text, a retrieved context window, and evidence objects E1…En.

No LLM is used anywhere in Phase 2.

## 2. Normalization (`norm-v1`, search only)
Applied: NFC; tatweel removal; Arabic diacritics and Quranic annotation marks removal (incl. superscript alef U+0670 and small high letters); removal of ۞ ۩, Arabic and ASCII punctuation, ornate parentheses ﴾﴿, quotation marks, digits; alef forms أ إ آ ٱ → ا; whitespace (incl. NBSP) collapse.
Not applied: ة→ه, ى→ي, hamza-seat folding. These merge distinct words and need evaluation evidence first.
Two search copies per ayah: the publisher's own imla'i text (`aya_text_emlaey`, which KFGQPC provides "for search purpose") and the Uthmani text. Users type imla'i spelling, which differs from the Uthmani rasm in many words (e.g. superscript-alef spellings), so the imla'i copy is the primary search field.

## 3. The semantic component: what it is and is not
- **What it is:** `local_lsa:char-ngram-lsa-v1`, i.e. **character n-gram TF-IDF (char_wb 2–4) + truncated SVD (LSA, 256 dims) + FAISS** (`IndexFlatIP`, faiss-cpu 1.15.1), fitted offline on the approved corpus's normalized text. It is a real vector-space / latent-semantic retrieval baseline.
- **What it is not:** it is **not a neural Arabic embedding model**. It models surface (orthographic) similarity, not meaning across different vocabulary.
- **Neural provider:** an adapter (`sentence_transformers`) exists but is **not runtime-verified**; no model weights could be downloaded in the build environment. Any future neural provider must be re-evaluated with `eval/compare_retrieval.py` before any improvement claim.
- **Test double:** `hash-trigram-64`, used only in synthetic tests, labelled `(TEST DOUBLE)` in every output and refused when `APP_ENV=production`.

## 4. Evaluation set
- 1,400 cases per seed, **generated programmatically from the real corpus**: 200 each of exact Uthmani, exact imla'i, partial slice (4–8 words), formatting noise (brackets, doubled spaces, ayah number), span across two consecutive ayat, one-word substitution (8–12-word slice), two-word deletion (9–12-word slice).
- The correct answer is known by construction. For verbatim categories, every passage containing the same token sequence also counts as correct (the Quran repeats wording).
- Two seeds: 20261001 (development) and 777 (held out: not looked at while changing code).
- **Limits:** generated cases are not human paraphrases, are not expert-reviewed, and include no claims. True paraphrase (different wording, same meaning) is not tested, because writing such cases would mean typing Quran-derived text by hand. Results describe quote-location performance only.
- NOT_FOUND false positives: 30 synthetic non-religious everyday sentences (`eval/fixtures/synthetic_not_found_ar.txt`).

## 5. Retrieval results

Development seed 20261001 (1,400 cases):

| System | Recall@1 | Recall@5 | MRR |
|---|---|---|---|
| BM25 only | 0.9607 | 0.9957 | 0.9764 |
| Semantic only (local LSA) | 0.8336 | 0.9471 | 0.8823 |
| Hybrid RRF (k=60) | 0.9014 | 0.9814 | 0.9378 |
| Hybrid RRF + exact-phrase priority | 0.9293 | 0.9864 | 0.9545 |
| **Hybrid lexical_first (production default)** | **0.9643** | **0.9957** | **0.9784** |

Held-out seed 777 (1,400 cases):

| System | Recall@1 | Recall@5 | MRR |
|---|---|---|---|
| BM25 only | 0.9686 | 0.9964 | 0.9810 |
| Semantic only (local LSA) | 0.8386 | 0.9421 | 0.8846 |
| Hybrid RRF (k=60) | 0.9121 | 0.9836 | 0.9432 |
| Hybrid RRF + exact-phrase priority | 0.9436 | 0.9929 | 0.9640 |
| **Hybrid lexical_first (production default)** | **0.9750** | **0.9993** | **0.9854** |

### Finding: the semantic component did not improve retrieval
- **BM25 is stronger than the current LSA semantic retriever** in every non-trivial category (e.g. span Recall@1: BM25 0.795 / 0.84, LSA 0.43 / 0.49).
- **Plain RRF degraded retrieval**: Recall@1 −0.059 (dev) and −0.057 (held-out) vs BM25, because equal-weight fusion lets LSA rank-1 errors displace BM25's correct rank-1. Changing k did not fix it (during the investigation, before the span-matching fix, the RRF candidate pool lost 10 of 200 span cases vs BM25 at k=60 and k=200, and 6 at k=10).
- **`lexical_first` remains the production default**: exact-phrase candidates, then BM25 order, then LSA-only candidates appended. Its small Recall@1 edge over BM25 (+0.004 / +0.006) comes from the **exact-phrase rule**, not from the LSA retriever.
- **The LSA component widens the candidate pool but has not demonstrated an independent retrieval improvement.** Matcher outcomes are identical with BM25-only, RRF and lexical_first pools (§6).
- **No claim is made that AI or semantic search improved retrieval.** RRF stays selectable (`HYBRID_STRATEGY=rrf`). A neural Arabic embedding provider may replace LSA and must be re-evaluated first.

## 6. Quote matching results (end to end, production configuration: `PARAPHRASE_MODE=disabled`)
Outcome classes:
- correct resolved;
- correct AMBIGUOUS: the quote's wording genuinely occurs in several passages;
- near match not attributed: no exact or partial match exists, so the result is AMBIGUOUS (`NEAR_MATCH_UNCONFIRMED`), with the true source among the closest passages listed for review;
- WRONG resolved;
- missed.

| Seed | Correct resolved | Correct ambiguous (repeated text) | Near match not attributed (source listed) | Wrong | Missed |
|---|---|---|---|---|---|
| 20261001 | 967 | 33 | 400 | 0 | 0 |
| 777 (held out) | 960 | 40 | 400 | 0 | 0 |

*Missed* here is an outcome class of the matcher (true source neither resolved nor listed), not a retrieval metric. In the current source-resolution evaluation, no incorrect definitive attribution was produced. Retrieval itself is not perfect; the measured Recall@1, Recall@5 and MRR values document the remaining misses. These are generated cases from the corpus itself, not real-world quotations.

The 400 near matches are exactly the word-substitution and word-deletion categories (200 + 200): by design they are no longer attributed. Exact, partial, formatting and span categories are unaffected.

For reference only (not production): with `PARAPHRASE_MODE=experimental` the same cases give 1,354 / 1,348 correct resolved, 13 / 12 conservative ambiguous, 0 wrong. These reference numbers are on generated cases with uncalibrated thresholds and do **not** validate paraphrase detection.

NOT_FOUND on 30 synthetic non-religious sentences: 30/30 (false-positive rate 0.0).

Development note: the first run on seed 20261001 showed 1 wrong resolution (a two-ayah span resolved to an unrelated pair through near matching) because span detection depended on candidate ranking. Span detection was changed to a boundary-anchored phrase search over the whole corpus. The held-out seed was run only after that change.

## 7. Matching rules and thresholds
| Setting | Value | Status |
|---|---|---|
| `PARAPHRASE_MODE` | `disabled` | **production default, enforced in production** |
| `MIN_PARTIAL_TOKENS` | 2 | starting value |
| `MAX_SPAN_AYAT` | 3 | starting value |
| `PARAPHRASE_MIN_COVERAGE` | 0.6 | **not calibrated**; with mode disabled it only separates "closest passages listed" (AMBIGUOUS) from NOT_FOUND |
| `PARAPHRASE_MIN_MARGIN` | 0.1 | **not calibrated**; used only in experimental mode |
| `RRF_K` | 60 | starting value (as specified) |
| `CONTEXT_WINDOW` | 2 ayat each side | as specified |

**PARAPHRASED is reserved/experimental.** It stays in the schema for future use. Until a validated paraphrase evaluation set exists, the production matcher emits only EXACT or PARTIAL from direct textual evidence, and AMBIGUOUS or NOT_FOUND otherwise. Retrieval scores (BM25 or LSA) never decide a match status; they only choose where the deterministic matcher looks. Tests: `backend/tests/test_paraphrase_gate.py`. See `LIMITATIONS.md` §1.

## 8. Context and evidence
- Quran: matched ayat plus up to 2 before and 2 after, never crossing a surah boundary. Labelled "retrieved context window", never "complete context".
- Hadith: the single unit with book/chapter/grading metadata; neighbours are not context.
- Evidence ids E1…En are generated by the backend in order: matched_source, preceding_context, following_context, (source_commentary when approved commentary exists), metadata. Evidence text is always canonical `original_text`.

## 9. Claim analysis (Phase 3)
**Method.** After deterministic source verification, a language model classifies the claim–evidence relation using only backend evidence objects, under the controls in `AI_SAFETY.md` (gate before the model, strict schema, citation and grounding verification, safety lint, one retry, level C/D routing). Prompt: `claim_analysis_v1` (`PROMPTING.md`).

**Real model status: BLOCKED_BY_LLM_ACCESS.** No API key was available. No real model output exists; no classification accuracy, stability or grounded-vs-ungrounded result can be reported. The harnesses are ready: `eval/stability.py` (≥ 3 runs per critical case, all labels recorded) and `eval/grounded_vs_ungrounded.py` (evaluation-only ungrounded baseline). Both currently write `status: BLOCKED_BY_LLM_ACCESS` to `eval/results/`.

**Classification metrics: NOT COMPUTED.** `eval/claim_cases/candidate_cases_pending.jsonl` has 3 candidate cases, all `review_status = pending`, 0 reviewed. One carries a `proposed_relation` from the project presentation; it is not a gold label.

**Guard-rail evaluation (measured).** `eval/run_safety_eval.py` runs 25 technical cases through the real pipeline and real corpus, with **scripted test-double model outputs** (valid and adversarial). It measures Tibyan's controls, not a model. Results (`eval/results/safety_eval.json`):

| Metric | Result |
|---|---|
| Citation validity rate of displayed AI outputs | 3/3 (1.0) |
| Unsupported citations displayed | 0 |
| Scripted model outputs rejected by verifiers | 21 |
| Required-abstention recall | 13/13 |
| Specialist-routing pass rate | 6/6 |
| Prompt-injection defense pass rate (structural) | 5/5 |
| Hallucination rejection rate | 6/6 |
| LLM-failure degradation pass rate | 3/3 |
| Critical safety case pass rate | 23/23 |
| All technical cases | 25/25 |

"Structural" injection defense means: user text stays inside the escaped data block, routing and gate are unchanged, and an output that obeys the injection is still rejected if it breaks a verifier. A model that obeys an injection but returns a **verifier-valid** wrong label cannot be detected deterministically; measuring that requires live-model tests (blocked).

## 10. Not yet measured
Phase 4 measured local latency and a small load test (`EVALUATION.md` §4–5); latency on a real host is still unmeasured. Also not measured: tafsir, aqeedah, fiqh and history retrieval (not ingested), real user hadith quotations, user comprehension, any real-model claim analysis (accuracy, stability, injection resistance, grounded vs ungrounded), human-reviewed cases, true paraphrase retrieval, real misquotations from social media, hadith retrieval, any neural embedding model.

## 11. Multi-source retrieval (2026-10-02)
**Sources and order.** The Quran is searched first exactly as before (same BM25 index, same LSA index, same matcher). Only if the Quran gives no verbatim match (neither a resolved match nor a verbatim match in several ayat) is the hadith corpus (Sahih al-Bukhari, Sahih Muslim) searched, with its own BM25 index (`hadith_fts`) and no semantic retrieval. The stronger textual result wins (resolved > verbatim in several places > near match > none); a quote found verbatim in the Quran is never re-attributed to a hadith, even though many hadith quote ayat.

**Hadith matching.** The same deterministic rules as for the Quran, restricted to one hadith (no spans across hadith). PARTIAL is the normal outcome, since each record also contains the isnad. A text repeated verbatim across narrations or across the two collections is AMBIGUOUS and is not attributed to one of them; the locations are listed. Near matches are listed only for quotes of at least 5 words with at least 80% token coverage (uncalibrated starting values) and are never attributed.

**Context and evidence.** A hadith is shown in full with its collection, number(s), book, chapter, edition and grading rule. Adjacent hadith are never used as context. Evidence items carry `source_type` and `verification_status`.

**Grading.** Taken from the package rule for the two Sahih collections, recorded per record with `grading_generated_by_model = false`; no model ever grades a hadith.

**Claim analysis.** The language model is used only for Quran results. For hadith the gate returns `CLAIM_ANALYSIS_NOT_ENABLED_FOR_SOURCE_TYPE`: the text and source are shown and no verdict is produced. Personal-fatwa claims (level D) are still referred to a specialist whatever the source. The grounding verifier now checks AI text against both the Quran and hadith indexes.

**Terminology.** Not part of the product since 2026-10-04. (Before that, the 10 package sample terms were looked up by exact normalized word and shown as guidance, separate from sources.)

**Hadith search normalization `hnorm-v1` (correction pass, 2026-10-02; search only).** The hadith index's first search column uses: NFKC (expands ﷺ and Arabic presentation forms) → norm-v1 (diacritics, tatweel, punctuation, decorative marks, alef forms, whitespace) → removal of honorific formulas as whole token sequences (صلى الله عليه [وآله] وسلم; رضي/رضى الله عنه/عنها/عنهما/عنهم/عنهن; عليه/عليها/عليهم [الصلاة و]السلام). The second column keeps plain norm-v1. A quote is matched as a verbatim phrase under either hnorm-v1 or NFKC+norm-v1, so a quote with ﷺ, with the formula written out, or without it finds the same text, and a slice cut inside a formula still matches. Stored and displayed text never changes. The Quran index and its queries are untouched (norm-v1). Verbatim phrase hits that BM25 did not rank in its top 20 are now added to the candidate list ahead of BM25 order (ranking only; attribution is still decided by the deterministic matcher). Attribution thresholds were not changed.

**Matn-only index: not built.** The edition marks the Prophet's words with «…», but the boundary between isnad and matn is not marked (narrative before the quoted words, multi-narrator chains, «…» around Companions' speech), so a matn field could not be derived reliably; none was invented.

**Unnumbered Sahih Muslim narrations.** 192 narrations that the source file starts with a text heading but does not number (179 in Kitab al-Iman) are kept with `hadith_number = null`, an internal id `hadith:muslim:u:<book>:<chapter>:<ordinal>`, and a locator (book, chapter, source-file line); they are cited by book and chapter. Bare digits at the start of some of those headings are an unmarked, inconsistent edition marker: they are removed as markup and never used as numbers. Numbers 1–99 remain absent; no number was inferred.

**Results** (`eval/multi_source_eval.py`, seed 20261002, 200 generated cases per category, identical cases before and after; `EVALUATION.md` §1b): with the production ranking, verbatim slices Recall@1 0.955 → 0.955 and Recall@5 0.955 → 0.995; slices quoted with ﷺ Recall@1 0.780 → 0.995; slices without the honorific 0.795 → 0.955. BM25 alone stays modest (Recall@1 ≈ 0.69–0.80). No generated case was attributed to a passage that does not contain it, before or after. Hadith status: **LIMITED_PRODUCTION** (see `LIMITATIONS.md` §13). The Quran retrieval regression is identical to the Phase 4 tag.

## 12. Text comparison, evidence map and screenshot input (2026-10-03)
These three additions sit **after** the pipeline's decisions. They change no threshold, no matching rule, no evidence, no label and no safety rule, and the existing response fields are byte-for-byte unchanged (the four evaluation result files reproduce with 0 differences; `EVALUATION.md` §6).

**Text comparison (`quote_comparison`, `diff-v1`, `backend/app/services/text_diff.py`).** Deterministic, no model.
1. Both sides are split on whitespace. Each word gets a comparison form (NFKC, then norm-v1) and keeps its display form; the canonical text is never modified.
2. Quran: the quote is aligned against the publisher's imla'i text of the matched ayat (the column users type) and against the Uthmani text; the column with more equal words is used. Imla'i words are mapped back to the Uthmani display words through a character-level alignment, so the Uthmani text is what is shown. Hadith: the stored text, with honorific formulas (the hnorm-v1 sequences) taken out of the alignment and shown as normalization-only.
3. A local window around the longest common run is aligned with `difflib.SequenceMatcher`. Equal comparison forms are MATCHED, or NORMALIZATION_ONLY when the written forms differ, with the reason detected by character class (diacritics, tatweel, punctuation, alef forms, presentation forms, honorific, orthography, formatting). Words only in the quote are ADDED_BY_USER; words only in the source are DELETED_FROM_USER_QUOTE inside the quoted range and OUTSIDE_QUOTE before or after it; a one-for-one change is SUBSTITUTED.
4. The summary uses neutral wording only: «مطابق حرفيًا», «اختلاف في علامات التشكيل فقط», «كلمة مفقودة من الاقتباس», «كلمة مختلفة عن النص المعتمد», «الاقتباس يحتوي على جزء من النص فقط». It never says why a difference exists.
5. A definitive comparison exists only for a RESOLVED source. For `NEAR_MATCH_UNCONFIRMED` results the closest three passages each get a comparison marked `definitive: false`, shown inside the candidate card «للمراجعة، دون نسبة». AMBIGUOUS hadith (repeated text) and NOT_FOUND get none.

**Evidence & context map (`evidence_map`, `map-v1`, `backend/app/services/evidence_map.py`).** A projection of the response's own data: the resolved source; the passages in reading order (preceding context, matched passage, following context; for hadith only the hadith itself); each passage split into segments that are in the quote (green), in the matched passage but not in the quote (amber), or neighbouring context (grey), taken from the comparison; every evidence id linked to its passage (the metadata item to the source); the claim; and the claim-analysis outcome already decided by the pipeline. «أهمية السياق للادعاء» is UNDETERMINED (غير محدد) unless a real model's analysis passed the verifiers: then RELEVANT (ذات صلة) if it cited context evidence, LIMITED (محدودة) if it cited only the match; NEEDS_REVIEW (تحتاج مراجعة) when the matter was referred or certainty restricted. No numeric confidence, and nothing is inferred without a model. Built only for RESOLVED results.

**Screenshot input (frontend only, `frontend/src/ocr/`).** Image → checks (`validate.ts`: size, signature, declared type, header dimensions, decode) → OCR in the browser (`ocr.ts`: tesseract.js 7.0.0, Arabic LSTM model `ara` from `@tesseract.js-data/ara` 1.0.0 folder `4.0.0_best_int`, OEM 1, default page segmentation; small images are upscaled ×2 and dark backgrounds inverted before recognition) → candidate quotes and a suggested claim (`segment.ts`, fixed text rules: quotation marks, Quran brackets, parentheses as OCR reads those brackets, attribution formulas; references, verse numbers and isti'adha removed) → **mandatory review and editing by the visitor** → the same `/api/v1/analyze` request as typed text. OCR confidence is shown only as «جودة استخراج النص» (pixel legibility) and never enters the pipeline. The image itself is not evidence and never reaches the backend or a model.
