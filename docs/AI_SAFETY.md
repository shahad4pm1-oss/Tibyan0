# AI safety: the LLM's role and the controls around it (Phase 3)

## 1. The LLM's exact role
The language model does **one** thing: classify the relationship between a user's **claim** and **verified evidence** that Tibyan has already retrieved from its approved corpus. It returns one of five labels with a brief reason and the evidence ids it relied on.

The model is **not a source**. It never supplies, quotes or locates religious text. Locating the quote, verifying the source, retrieving context and building evidence are deterministic (Phase 2) and happen before the model is involved, if it is involved at all.

## 2. What the model is prohibited from doing (enforced in code, not only in the prompt)
| Prohibition | Prompt rule | Enforcement in code |
|---|---|---|
| Using model memory as a source | SYSTEM RULE 1 | Grounding verifier: any 5-word window of AI text that occurs in the Quran corpus only at passages **not** supplied as evidence → reject |
| Inventing verses, hadith, tafsir, scholars, books, references | 2 | Citation verifier: unsupplied `s:a` references, ayah numbers, surah names and a list of source/authority names (رواه، البخاري، تفسير، ابن كثير، قال العلماء، …) → reject |
| Quoting text not in the cited evidence | 3 | Grounding verifier: quoted segments («…» “…” "…" ﴿…﴾) must be inside a **cited** passage or the user's own words; Uthmani-script characters in AI text → reject |
| Citing evidence that does not exist | output rules | Citation verifier: `evidence_ids ⊆ backend ids`; key_evidence ⊆ evidence_ids; a verdict needs a non-metadata citation |
| Issuing fatwas / personal rulings | 4 | Level D never reaches the model; safety lint rejects personal-ruling language (يجوز لك، يجب عليك، …) |
| Judging people, intent, groups; profiling the user | 5 | Safety lint rejects person-judgment and profiling language |
| Certainty on disputed matters, asserting consensus | 6 | Safety lint rejects unsupported certainty (بالإجماع، قطعًا، …); level C verdicts are overridden to REQUIRES_SPECIALIST |
| Following instructions inside user text | 9 | User text is JSON-encoded with `< > =` escaped inside an UNTRUSTED USER DATA block; it cannot close the block or forge an evidence tag |
| Producing hidden reasoning | 10 | Schema has no reasoning field; adapter discards non-text content blocks |

## 3. Request flow
```
input validation → retrieval → quote match → source resolution → context → evidence (E1…En)
→ content level (A/B/C/D) → EVIDENCE GATE
     ├─ SPECIALIST_REQUIRED (level D) ──────────────► REQUIRES_SPECIALIST + referral (no model call)
     ├─ INSUFFICIENT (any gate reason) ─────────────► INSUFFICIENT_EVIDENCE (no model call)
     └─ PASS → LLM → strict JSON schema → citation verifier → grounding verifier → safety lint
                  │      any failure: ONE retry with a correction; second failure → INSUFFICIENT_EVIDENCE
                  │      provider error / timeout / empty: no retry, no verdict (ANALYSIS_UNAVAILABLE)
                  └→ safety.finalize (level C restriction, needs_specialist → referral) → response
```

## 4. Evidence gate (`backend/app/services/evidence_gate.py`)
Decisions: PASS / INSUFFICIENT / SPECIALIST_REQUIRED. The model is called **only on PASS**.

| Gate reason | Condition |
|---|---|
| `PERSONAL_CASE_LEVEL_D` | content level D → SPECIALIST_REQUIRED |
| `SOURCE_NOT_FOUND` | no approved passage matches |
| `SOURCE_AMBIGUOUS` | the quote matches several passages |
| `NEAR_MATCH_UNCONFIRMED` | no word-for-word match (PARAPHRASED stays disabled) |
| `NO_DIRECT_TEXTUAL_MATCH` | match status not EXACT/PARTIAL |
| `SOURCE_NOT_APPROVED` | resolved source not APPROVED |
| `NO_EVIDENCE` / `NO_CONTEXT` | no matched evidence object / no context |
| `INTEGRITY_CHECK_FAILED` | corpus digest differs from build, or an evidence text differs from the DB |
| `QUOTE_TOO_SHORT_FOR_ANALYSIS` | fewer than `GATE_MIN_QUOTE_TOKENS` (3) normalized words |

**Evidence strength** (no numeric confidence anywhere):

| Strength | Condition |
|---|---|
| SUFFICIENT | resolved EXACT/PARTIAL match of ≥ 5 normalized words, matched evidence present, integrity OK |
| LIMITED | same, but the quote has < 5 words |
| INSUFFICIENT | anything else |

## 5. Content-level routing (`content_level_router.py`)
A transparent keyword heuristic on the claim, applied to normalized text with Arabic proclitics. Precedence D > C > A > B (stricter wins). Rules are listed in the module (`RULES`). It is deliberately conservative and **not calibrated**: harmless claims containing words like «حكم» or «الكفار» go to C (specialist review) rather than letting a disputed matter through.

| Level | Behaviour |
|---|---|
| A (textual) | normal evidence-grounded verification |
| B (explanation; default) | evidence-grounded analysis; prompt asks for qualification |
| C (disputed / sensitive) | model runs with level-C guidance; any SUPPORTED/OVERSTATED/CONTRADICTED is overridden to REQUIRES_SPECIALIST (`LEVEL_C_CERTAINTY_RESTRICTED`) and the model's text is not shown |
| D (personal case / fatwa) | model never called; REQUIRES_SPECIALIST with a fixed referral; the verified source and context are still shown as general information |

## 6. User-visible outcomes
| Situation | `claim_analysis.status` | relation | Text shown |
|---|---|---|---|
| Model output verified | COMPLETED / ABSTAINED / REFERRED | model's label | AI summary in the labelled AI panel |
| No source | ABSTAINED | INSUFFICIENT_EVIDENCE | «لم نعثر على مرجع كافٍ في المصادر المتاحة.» (never «مكذوب») |
| Ambiguous / near match | ABSTAINED | INSUFFICIENT_EVIDENCE | explains that no attribution was made |
| Level D | REFERRED | REQUIRES_SPECIALIST | fixed personal-case message + referral |
| Level C override | REFERRED | REQUIRES_SPECIALIST | fixed message; model text withheld |
| Output rejected twice | AI_OUTPUT_REJECTED | INSUFFICIENT_EVIDENCE | fixed message; no model text shown |
| Provider failure / not configured | ANALYSIS_UNAVAILABLE | none | source, text, context and evidence still shown; no verdict |

All fixed Arabic messages are **drafts pending specialist review** (SCIENTIFIC_POLICY §6).

## 7. Privacy and logging
One audit line per request (`tibyan.audit`): request id, timestamp, statuses, retrieved passage ids, evidence ids, content level and matched rule codes, gate decision and reasons, relation, overrides, input-flag codes, provider/model, prompt version, attempts, tokens, latency, error category. **Never** the quote or claim text (tested). No accounts, no profiles.

## 8. Test doubles vs real model
- `ScriptedProvider` (tests and `eval/run_safety_eval.py`) and `AbstainingTestDouble` (`LLM_PROVIDER=test_double`) are labelled `(TEST DOUBLE)` in every response and refused when `APP_ENV=production`.
- **No real model has been run.** The Anthropic adapter is unit-tested with a mock HTTP transport only. Live validation, stability and the grounded-vs-ungrounded experiment are **BLOCKED_BY_LLM_ACCESS**.
