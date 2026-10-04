# Scientific Safety Policy (software requirements)

Source of authority: Scientific Package pp.2, 5, 6, 8 (see `OFFICIAL_REQUIREMENTS.md` §3).
Each rule has an ID. Later phases must cite these IDs in code comments, tests and `ACCEPTANCE_CRITERIA.md`.
"MUST" rules are release blockers.

## 1. Core rules

| ID | Rule | Software requirement |
|---|---|---|
| **SP-01** | Every religious statement or quotation shown is traceable to a source | Every displayed text segment of type `source_text` or `commentary` carries `source_id`, `edition`, `locator` (e.g. `2:190`, `bukhari:1234`), and a link or citation string. The response schema rejects a segment without them. |
| **SP-02** | Never attribute text to a source where it does not exist | The Citation Verifier re-reads the cited span from the local corpus by `locator` and checks string equality (after declared normalization) before display. Any mismatch removes the citation and downgrades the result to `INSUFFICIENT_EVIDENCE` (abstain). LLM output may only *reference* evidence IDs; it never writes source text. |
| **SP-03** | Separate original text, source commentary, and AI explanation | Response carries three distinct segment types: `source_text` (Quran/hadith), `commentary` (approved tafsir/sharh, with author), `ai_explanation`. The UI renders them in visually distinct, labeled blocks. `ai_explanation` never contains quoted religious text that is not also present as a verified `source_text` segment. |
| **SP-04** | Interpretive/disputed matters never stated as certain | If the content level is C, or evidence includes conflicting commentary, the response must carry `certainty: "qualified"` and the UI shows the disagreement notice. Banned absolutes in `ai_explanation` for level C (e.g. "بإجماع", "قطعًا", "all Muslims agree") are checked by a lint rule unless backed by an approved source segment saying so. |
| **SP-05** | No independent personal fatwa | Scope/Safety Gate classifies level D inputs (personal case, individual ruling, contract/worship validity, family dispute, legal/medical with sharia effect). Level D returns general information only (if any approved text applies) plus a referral message; the Claim Analyzer is not run on the personal question. No code path produces a halal/haram ruling for a user situation. No automated tarjih between scholarly positions. |
| **SP-06** | Missing or insufficient evidence: abstain, qualify, or refer | The Evidence Gate decides before any claim analysis. If the quote is not found, or retrieved evidence is below threshold, or context is incomplete, the system returns `NOT_FOUND`/`INSUFFICIENT_EVIDENCE` with an explicit statement ("لم يُعثر على نص مطابق في المصادر المتاحة"). It never falls back to model knowledge. |
| **SP-07** | No unnecessary personal or religious inferences about users | No accounts, no user profiles, no storage of user religion/beliefs. Inputs are processed per request; logs store only request id, timings, verdict, and a hash of the input by default. Raw input logging is off unless explicitly enabled for evaluation runs. A privacy notice states this. |
| **SP-08** | Disclose AI-generated analysis | Every result shows a fixed disclosure that this is an AI-assisted verification tool, not a mufti or human specialist. `ai_explanation` blocks are labeled "تحليل آلي". |

## 2. Additional rules derived from the package

| ID | Rule | Software requirement |
|---|---|---|
| SP-09 | Hadith used as evidence must show its grading (package p.3 and terminology "Hadith") | `source_text` of type hadith requires `grading` and `grading_source`. V1 corpus = Bukhari and Muslim only; anything else is excluded until graded per `SOURCES.md`. |
| SP-10 | Misquoted verse: give correct text gently, show surah and ayah, do not build on the corrupted text (p.6) | Quote Matcher returns `AMBIGUOUS` with reason `NEAR_MATCH_UNCONFIRMED` (PARAPHRASED is reserved and disabled in production): the closest verified passages are displayed for review and nothing is attributed; claim analysis runs against the verified text, never the user's variant. |
| SP-11 | Do not attribute unproven consensus (p.6) | Claims asserting agreement/consensus are tagged; without an approved source stating it, verdict cannot be `SUPPORTED`. |
| SP-12 | Respectful tone; do not mirror hostility (p.6) | Response templates are fixed Arabic text reviewed once; the LLM does not write verdict headlines. |
| SP-13 | Do not judge persons or groups (p.2 scope) | Verdicts describe the relationship between the **claim** and the **evidence**, not the character, intent or identity of the user or of whoever used the quotation. Output never comments on a person's honesty or motives. |
| SP-14 | Commentary separated from Quranic text (p.3, tafsir rule) | Tafsir segments are `commentary` with author and work; never merged into `source_text`. |
| SP-15 | Sensitive terms use the official dictionary (p.4, p.8) | UI terms and any English labels use the Al-Jumhura equivalents. |
| SP-16 | Out-of-scope input | Inputs that are not a quote+claim (general chat, requests to generate religious content) get a scoped refusal. Tibyan is not an open-ended chatbot. |

## 3. Content levels and required behavior

| Level | Detection in Tibyan | Required behavior | Allowed outputs |
|---|---|---|---|
| **A** Stable original information (Quran, verified hadith, pillars, core seerah, settled facts) | Quote resolves to Quran or Bukhari/Muslim; claim is descriptive of the text | Direct answer documented to the source | Any quote status; claim verdicts `SUPPORTED`, `OVERSTATED`, `CONTRADICTED`, `INSUFFICIENT_EVIDENCE` |
| **B** Explanation, definition, reasoning, general shubuhat | Claim interprets meaning, compares, or addresses a common objection | Answer only from approved material with the reference shown; avoid certainty where disagreement is possible | Same verdicts; `ai_explanation` must cite evidence ids; qualifier shown where commentary differs |
| **C** Disputed or high-sensitivity (fiqh disagreement, detailed aqeedah, controversial history, needs specialist editing) | Classifier + keyword rules + conflicting commentary in evidence | Restrict to what is approved, or state that disagreement exists, or refer to a specialist | Quote status and context are still shown; claim verdict is limited to `INSUFFICIENT_EVIDENCE` or `REQUIRES_SPECIALIST` unless the claim is purely textual (e.g. truncation itself) |
| **D** Fatwa / personal case | Scope gate: first-person situation, request for a ruling on an individual matter | No independent ruling; general information plus referral to a qualified party | `REQUIRES_SPECIALIST` only, with referral text. No claim analysis |

**Ambiguity rule:** when level detection is uncertain between two levels, the stricter level applies.

## 4. Verdict vocabulary (frozen for V1)

Quote status (from Quote Matcher):
| Code | Arabic label | Meaning |
|---|---|---|
| `EXACT` | النص موجود بلفظه | Matches a verified source after normalization |
| `PARTIAL` | النص مقتطع | Matches a contiguous part of a longer unit; truncation shown |
| `PARAPHRASED` | النص قريب من نص في المصدر لكنه لا يطابقه حرفيًا | **Reserved/experimental, disabled in production** until a reviewed paraphrase set and calibrated thresholds exist (replaces Phase 1's `VARIANT`) |
| `AMBIGUOUS` | النص يطابق أكثر من موضع / لا مطابقة حرفية | The wording occurs in several passages (`MULTIPLE_LOCATIONS`), or there is no word-for-word match and the closest passages are listed (`NEAR_MATCH_UNCONFIRMED`); none is attributed |
| `NOT_FOUND` | لم يُعثر على النص في المصادر المتاحة | No match in the V1 corpus; this is **not** a claim that the text does not exist anywhere |

Claim verdict (from Claim Analyzer, only after Evidence Gate passes):
| Code | Arabic label | Meaning |
|---|---|---|
| `SUPPORTED` | الادعاء متسق مع النص في سياقه | Evidence supports the claim |
| `OVERSTATED` | الادعاء أوسع مما يدل عليه النص | Claim goes beyond what the text says in context |
| `CONTRADICTED` | السياق يخالف الادعاء | Context directly contradicts the claim |
| `INSUFFICIENT_EVIDENCE` | لا تكفي الأدلة المتاحة للحكم | Evidence insufficient or ambiguous; **abstention** |
| `REQUIRES_SPECIALIST` | يحتاج إلى مراجعة مختص | Level C/D, disputed matter or conflicting evidence; **referral** |

**What the labels mean.** Each label describes the relationship between the **claim** and the **evidence** retrieved from the approved corpus. It is not a statement about the character, intent or identity of the user or of anyone who used the quotation.

**Why these labels and not "مضلِّل" (misleading).** The presentation's word is not forbidden by the package: describing a *use* of a quotation as inconsistent, overstated or misleading is not in itself a judgment of a person. The five labels are used because they are clearer, each maps to a distinct measurable outcome, and they suit evaluation (confusion matrix, per-class precision/recall).

**Rules attached to the labels.**
- Disputed or ijtihadi matters are not stated with unjustified certainty (SP-04): at level C, a substantive verdict is only allowed when the claim concerns the text itself (e.g. truncation); otherwise `INSUFFICIENT_EVIDENCE` or `REQUIRES_SPECIALIST`.
- Insufficient evidence always leads to abstention (`INSUFFICIENT_EVIDENCE`) or referral (`REQUIRES_SPECIALIST`), never to a guessed verdict (SP-06).

## 4b. Implementation status (Phase 3)
| Rule | Implemented in | Tested in |
|---|---|---|
| SP-01 traceability | evidence objects from DB; `claim_analysis.evidence_ids` ⊆ backend ids | test_citation_verifier, test_analysis_pipeline |
| SP-02 no false attribution | `citation_verifier.py`, `grounding_verifier.py` | test_citation_verifier, test_grounding_verifier, test_hallucination_cases |
| SP-03 separate text / commentary / AI | API: religious text only in `context`/`evidence`; AI text only in `claim_analysis` with `summary_source`; UI: scripture font vs labelled AI panel | test_analysis_pipeline; UI review |
| SP-04 no certainty on disputed matters | level C override in `safety.finalize`; certainty lint | test_specialist_routing, test_safety |
| SP-05 no fatwa | level D routing before the model; personal-ruling lint | test_specialist_routing, test_safety |
| SP-06 abstain on insufficient evidence | `evidence_gate.py`; rejection → INSUFFICIENT_EVIDENCE | test_evidence_gate, test_llm_failure |
| SP-07 privacy | audit log without user text | test_safety::test_logs_contain_no_raw_user_text |
| SP-08 AI disclosure | `claim_analysis.disclosure`; UI panel label | test_analysis_pipeline |
| SP-11 no unproven consensus | consensus claims → level C; consensus lint on AI text | test_content_level_router, test_safety |
| SP-13 no judging persons | person-judgment lint | test_safety, test_analysis_pipeline::hostile |
| SP-16 out-of-scope input | Arabic-quote validation (INVALID_INPUT); open chat is not supported by the API | test_analyze_api |

## 5. Required disclosures (fixed text, to be reviewed before release)
- AI disclosure (SP-08).
- Corpus scope: which sources were searched and their versions, so `NOT_FOUND` is read correctly.
- Not a fatwa; referral guidance for personal questions.
- Privacy notice (SP-07).

## 6. Human review
- Evaluation cases are labeled `unreviewed` until a named, qualified reviewer signs off; reviewer name/role and date stored with the case. No case is presented as expert-reviewed otherwise.
- Fixed Arabic templates (verdict labels, referral text, disclosures) need one specialist review before release. Until then they are marked draft.
