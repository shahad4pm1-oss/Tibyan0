# Known limitations (updated 2026-10-03, text comparison, evidence map, screenshot input)

Each limitation says what the system does about it today. Numbers come from `eval/results/`.

## 1. PARAPHRASED is reserved/experimental
- **Fact:** true paraphrase retrieval (same meaning, different words) has **not been validated**: the evaluation set contains no human-written paraphrases, and the near-match thresholds (`PARAPHRASE_MIN_COVERAGE` 0.6, `PARAPHRASE_MIN_MARGIN` 0.1) are **not calibrated**.
- **What the system does:** `PARAPHRASE_MODE=disabled` is the default and is enforced in production (`APP_ENV=production` refuses `experimental`). A quote that is neither an exact nor a contiguous partial match (in one ayah or across up to 3 consecutive ayat) is **never attributed to a source**. It returns `AMBIGUOUS` with `ambiguity_reason = NEAR_MATCH_UNCONFIRMED`: the closest passages are listed for the user to review, no source is resolved, and no evidence objects are produced. If nothing is close enough, it returns `NOT_FOUND`.
- **Consequence:** a misquotation (one word changed or dropped) is not labelled as such. The user sees "no word-for-word match" plus the closest real passages. On the generated cases, all 400 per seed of these misquotations returned this outcome with the true source in the list, and none was attributed.
- **What would lift it:** a validated paraphrase/misquotation evaluation set reviewed by a qualified person, and thresholds calibrated on it (`ACCEPTANCE_CRITERIA.md` AC-3.4).

## 2. The semantic retriever is not a neural model
- **Fact:** the semantic component is **character n-gram TF-IDF + truncated SVD (LSA) + FAISS**. It is a real vector-space / latent-semantic retrieval baseline, **not a neural Arabic embedding model**. No neural model could be downloaded in the build environment.
- **Measured:** BM25 is stronger than the LSA retriever in every category. Plain RRF fusion made ranking worse than BM25 alone. The production default `lexical_first` keeps BM25 order; the LSA candidates only widen the candidate pool and have **not shown an independent retrieval improvement**.
- **Not claimed:** that AI or semantic search improved retrieval.
- **What would lift it:** a neural Arabic embedding provider, re-evaluated with `eval/compare_retrieval.py` before any improvement claim.

## 3. Evaluation set is generated, not reviewed
Cases are produced programmatically from the corpus (exact, partial, formatting noise, spans, word substitution, word deletion). They are not human-written, not expert-reviewed, include no real-world misquotations and no claims.

## 4. Corpus coverage
Quran (KFGQPC Hafs) and the numbered hadith of Sahih al-Bukhari (7,380 entries) and Sahih Muslim (2,922; Kitab al-Iman 1–99 and 12 other numbers are unnumbered or absent in the source file and not ingested). **Not integrated** (blocked by access and/or terms, `OFFICIAL_SOURCE_INVENTORY.md`): Dorar hadith/tafseer/aqeeda/feqhia/history, Bayyinat, the full Jamhara dictionary, dawa.center and islamic-content.com content, Quran translations, other Sunnah books. NOT_FOUND means "not found in the corpus searched".

## 5. Provenance items still open
- KFGQPC usage rights read as reproduced in full in the quran-text LICENSE, not on qurancomplex.gov.sa itself (unreachable).
- No human spot-check of the ingested text against the printed mushaf.

## 6. Context
The context shown is a retrieved window of up to 2 ayat before and after, within the surah. It is not the complete scholarly context, and no approved tafsir is ingested yet.

## 7. Claim analysis has not been run with a real model
The full reasoning and safety layer exists and is tested with test doubles. No real LLM has produced an output (no API key): there is no measured accuracy, stability, real injection resistance, cost or latency for claim analysis. Status: **REAL LLM VALIDATION = PENDING**. Two adapters exist (Google Gemini `generateContent` and Anthropic Messages); both are verified only against a mocked HTTP transport, not against the live services. In production without a key the product shows «تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً», gives no verdict, and hides section 8 (تحليل تبيان) entirely; test doubles are refused in production.

## 8. No reviewed gold labels
No claim-analysis case has been reviewed by a qualified reviewer (0 reviewed, 3 pending). Classification metrics are therefore not computed.

## 9. Content-level routing is a keyword heuristic
Uncalibrated and conservative: some harmless claims are routed to C (specialist) or D (referral), and a disputed claim phrased without any listed keyword may be treated as B. Level B results are still restricted by the verifiers and lint, but are not the same as specialist review.

## 10. Verifier false positives
The citation and safety lints use word lists; a legitimate model sentence that mentions, for example, «تفسير» will be rejected (then retried, then abstain). This trades some answers for safety and is not yet measured on real model outputs.

## 11. Fixed messages are drafts
Referral, abstention and level-C texts have not been reviewed by a specialist.

## 12. Operational limits (Phase 4)
- **Rate limit is in-process and per worker.** Counters live in memory: they reset on restart and are not shared across workers or instances. With N workers the effective limit is up to N × 30/min per IP. Good enough for a single small instance; a shared store (or the host's edge rate limiting) is needed to scale out.
- **Throughput is modest.** On the development container (2026-10-02 run) one worker served ~112 req/s sequentially and ~73 req/s at 25 concurrent clients (p95 602 ms), all requests succeeding (`eval/results/load_test.json`). The pipeline is CPU-bound Python running in the threadpool; more throughput needs more processes. These are not measurements of any production host.
- **Not deployed.** No hosting credentials were available, so there is no live URL. The Docker image could not be built here (Docker Hub is not reachable from the build environment); the same build steps were verified in a clean virtualenv instead (`DEPLOYMENT.md` §4).
- **Accessibility checked automatically only.** axe-core (WCAG 2.1 A/AA) reports no serious or critical issue on all pages and result states at three widths, plus keyboard checks in the E2E suite. No screen-reader user testing has been done.
- UI fonts are bundled with the frontend (no font service). Quran text always uses the bundled KFGQPC font.

## 13. Hadith-specific limits (2026-10-02; hadith status LIMITED_PRODUCTION)
- **Status: LIMITED_PRODUCTION.** Only verbatim matches are attributed; every hadith result carries a limitation note in the UI and a `HADITH_LIMITED_PRODUCTION` warning in the API.
- **Authority vs provenance.** The Sahihayn are approved by the package; the machine-readable files come from OpenITI. Cross-check against Shamela/Dorar: PENDING (both unreachable). Printed-edition reuse: PENDING VERIFICATION. Non-commercial use only (CC BY-NC-SA 4.0 for the OpenITI layer).
- **Grading is collection-level.** The grade shown is the package rule for the two Sahih collections. A numbered entry's text can include an isnad, a suspended report (mu'allaq) or a Companion's words; the rule is not a separate judgement on those parts. No other grading source (e.g. Dorar) is integrated.
- **Numbering gaps.** Bukhari: 174 of 7,563 numbers are not separate entries in the file (combined with neighbours in that edition). Muslim: 111 of 3,033 numbers absent; 192 narrations that the file does not number are kept with `hadith_number = null` and cited by book and chapter only, and two narrations without their own heading may be joined in one record. No number is invented.
- **Honorifics.** Fixed for search (hnorm-v1): ﷺ, the written formula, its omission, diacritics and punctuation all reach the same text. A quote that omits a formula AND is cut inside another one (e.g. ends with «رضي الله») may still fall to a near match and is then not attributed.
- **Retrieval strength.** With verbatim-first ranking, verbatim and honorific-variant slices reach Recall@1 0.955–0.995; BM25 alone stays near 0.70 on hadith, and edited quotes are deliberately not attributed. Measured on generated cases only.
- **Repeated texts.** Many matns recur across narrations and both collections; such quotes are listed as several locations, not attributed to one.
- **No claim verdicts on hadith.** Claim analysis is disabled for hadith results until a hadith-aware prompt is validated with a real model.
- **Hadith retrieval is BM25 only**, measured on generated cases (`EVALUATION.md` §1b), not on real user quotations.
- **Glossary**: none. The 10 Official Scientific Package Sample Glossary terms were removed from the product on 2026-10-04 (no lookup, no display); the Jamhara dictionary is not integrated.

## 14. Text comparison («مقارنة النص», 2026-10-03)
- **Word level only.** The comparison (`diff-v1`, `backend/app/services/text_diff.py`) aligns whitespace-separated words after the search normalization. It does not judge meaning: it states that a word is missing, added or different, never why.
- **Normalization reasons are mechanical.** "Diacritics", "punctuation", "alef forms", "tatweel", "presentation forms" and "honorific" are detected by character class. A difference that changes spelling inside one word (e.g. a missing hamza seat) is reported as a different word, not as a spelling variant.
- **Quran: imla'i basis.** Typed quotes are compared with the publisher's imla'i text of the same ayah (the search column), and differences are shown on the Uthmani text, which is never altered. When a quote is typed in Uthmani script, the Uthmani text is used instead. The mapping between the two scripts is character-based and can mark a neighbouring word in rare multi-word spellings.
- **Only for a resolved source.** AMBIGUOUS hadith (several locations) and NOT_FOUND get no comparison. Near matches (`NEAR_MATCH_UNCONFIRMED`) get a non-definitive comparison inside each of the first three candidate cards, labelled «للمراجعة، دون نسبة»; it never attributes the quote.
- **Long hadith.** Alignment is limited to a window around the longest common run, so when a quote's words occur in several places of a long hadith, the comparison follows the longest shared run.

## 15. Evidence & context map («خريطة الدليل والسياق», 2026-10-03)
- **A projection, not an analysis.** The map (`map-v1`) only rearranges data the pipeline already returned: passages, evidence ids and the claim-analysis outcome. It adds no text and no judgement.
- **Context relevance is UNDETERMINED without a verified AI analysis.** «ذات صلة» / «محدودة» appear only when a real model's analysis passed the citation and grounding verifiers and cited context (or only the match). As no real model has run yet (§7), every live result today shows «غير محدد» or «تحتاج مراجعة».
- **The omitted-text fact is textual.** "N words of the passage are not in the quote" is a count; it does not mean the omission changes the meaning.
- **Hadith maps have one node.** Adjacent hadith are never shown as context (§13).

## 16. Screenshot input («تحقق من صورة», 2026-10-03)
- **OCR quality depends on the image.** Measured only on images drawn by the test suite from corpus quotes (clear Naskh text, 15–44 px, light and dark backgrounds, light noise). Not measured on real social-media screenshots, decorative or calligraphic fonts, fully vowelled Uthmani Quran text, handwriting, photos of paper, skewed or multi-column layouts. Such images will often produce wrong words; the review step exists for this reason.
- **Arabic model only.** Latin text in the image is read poorly and is not needed for verification. No PDF input (the brief's optional item was not implemented).
- **"Quality" is the engine's own confidence.** «جودة استخراج النص» maps tesseract's mean word confidence to جيدة (≥ 85) / متوسطة (65–84) / ضعيفة (< 65). These cut-offs are starting values, not calibrated. It says nothing about the authenticity of the text.
- **Quote and claim detection is heuristic.** Quotation marks, Quran brackets (or the parentheses OCR often reads them as), attribution formulas and reference removal are fixed text rules (`frontend/src/ocr/segment.ts`). They can miss a quote or include extra words, and the suggested claim is simply the remaining Arabic text. Nothing is verified until the visitor confirms or edits both fields.
- **Device cost.** The OCR engine and model (about 5.6 MB) are downloaded from the Tibyan site on each use unless the browser's HTTP cache keeps them, and recognition runs on the visitor's CPU: on the development container a screenshot took about 0.85 s (small image) to 2.4 s (1170×2000 phone screenshot), engine start included. Older phones will be slower.
- **Browser support.** Needs WebAssembly and Web Workers (all current browsers). If the engine cannot start, the visitor is told so and can retry or type the text.
- **Checks are client-side.** They protect the visitor's tab; the server accepts no images at all (`SECURITY.md`).
