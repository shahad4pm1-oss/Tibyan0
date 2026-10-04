# V1 Scope (frozen 2026-10-01)

This scope does not expand until every MUST HAVE item meets its acceptance criterion in `ACCEPTANCE_CRITERIA.md`.
Change process: a scope change requires a written entry in §6 with reason and the user's approval.

## 1. Product definition
Tibyan V1 takes an **Arabic quotation** and the **claim** attached to it, and returns:
quote status (exact / partial / variant / not found), the verified source and locator, the surrounding context, the evidence used, a claim verdict or an abstention/referral, and the reason, with every religious text traceable to the approved V1 corpus.

V1 corpus (subject to provenance clearance in `SOURCES.md`): **Quran** (approved text) and **Sahih al-Bukhari and Sahih Muslim**. Tafsir from an approved channel is added only if its terms are cleared; otherwise context = adjacent ayat / surrounding hadith in the same chapter.

## 2. MUST HAVE
| # | Item | Notes |
|---|---|---|
| M1 | Arabic quote input | Length limits, Arabic-script validation |
| M2 | Associated claim input | Required field |
| M3 | Source retrieval | From local approved corpus only |
| M4 | Source verification | Retrieved text re-read from the corpus by locator |
| M5 | Arabic search normalization | Diacritics, tatweel, alef forms, punctuation; declared and versioned (`norm-v1`). ya/ta-marbuta/hamza folding deferred until evaluation shows benefit (Phase 2 instruction) |
| M6 | Lexical search | SQLite FTS5 / BM25 |
| M7 | Semantic search | Vector-space retrieval + FAISS (currently LSA baseline, not neural; no measured improvement yet) |
| M8 | Hybrid retrieval | Fusion of M6 + M7 |
| M9 | Quote completeness detection | EXACT / PARTIAL / AMBIGUOUS / NOT_FOUND (PARAPHRASED reserved, disabled in production) |
| M10 | Source-aware context retrieval | Quran: neighboring ayat; hadith: full hadith and its chapter |
| M11 | Evidence construction | Evidence items with ids, type, locator |
| M12 | Evidence sufficiency gate | Blocks analysis when evidence is weak |
| M13 | Claim-vs-evidence analysis | LLM/NLI over evidence only; verdicts per `SCIENTIFIC_POLICY.md` §4 |
| M14 | Citation verification | SP-02 |
| M15 | Abstention | SP-06 |
| M16 | Specialist routing | Level C/D, SP-05 |
| M17 | Source display | Locator, source name, edition |
| M18 | Evidence highlighting | Highlight the spans that drive the verdict |
| M19 | Error handling | Clear Arabic messages; no stack traces to users |
| M20 | Real evaluation | Labeled case set, reported honestly |
| M21 | Automated testing | Unit + integration + safety tests in CI |
| M22 | Deployment | Public live demo |
| M23 | Documentation | Run, sources/licenses register, methodology |

## 3. SHOULD HAVE
Example inputs; methodology page; evaluation page; copy result; shareable result card; health endpoint (exists as skeleton); corpus/model/pipeline version display; cost measurement.

## 4. NICE TO HAVE (only after all MUST items pass)
Screenshot OCR.

## 5. EXCLUDED FROM V1
Login; accounts; admin dashboard; mobile app; browser extension; voice; speech-to-text; PDF analysis; large multilingual support; fine-tuning; custom model training; knowledge graph; recommendation engine; religious user profiling; Redis (unless technically required); microservices; Kubernetes.
Also excluded: open-ended chat; generating religious content; fatwa; hadith outside Bukhari/Muslim; sources in `SOURCES.md` EXCLUDED_FROM_V1.

## 6. Scope change log
| Date | Change | Reason | Approved by |
|---|---|---|---|
| 2026-10-01 | Initial freeze | Phase 1 | Pending user review |
