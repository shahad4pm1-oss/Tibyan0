# Claim-analysis evaluation cases

Two files, never mixed:

| File | What | Labels |
|---|---|---|
| `technical_cases.jsonl` | Routing, gate, verifier and safety behaviour with **deterministic expected outcomes** (e.g. "personal case → REQUIRES_SPECIALIST without calling the model", "invented scholar → rejected"). Model outputs are **scripted test doubles**, not a real model | `review_status = "not_required_technical"`. These are software expectations, not religious judgments |
| `candidate_cases_pending.jsonl` | Cases whose correct relation needs religious/contextual judgment | `review_status = "pending"`, `gold_relation = null` until a named qualified reviewer approves. A `proposed_relation` may record who proposed it (e.g. the project presentation); it is **not** a gold label |

## Fields
| Field | Type | Meaning |
|---|---|---|
| `id` | str | stable id |
| `category` | str | one of SUPPORTED, OVERSTATED, CONTRADICTED, INSUFFICIENT_EVIDENCE, REQUIRES_SPECIALIST (the behaviour exercised) |
| `quote_spec` | object | how to build the quote. `{"locator": "quran:2:191", "field": "emlaey", "tokens": [0, 4]}` reads tokens from the corpus; optional `"replace": [index, word]` makes a misquotation; `{"synthetic": "..."}` is a non-religious sentence not in the corpus. Quran text is never stored in this file |
| `claim` | str | the claim (user language; not religious source text) |
| `script` | list[str] | technical cases only: names of scripted model outputs (see `eval/run_safety_eval.py`) |
| `expected` | object | technical cases only: `llm_calls`, `gate`, `status`, `relation`, `level` |
| `critical` | bool | counts toward Critical Safety Case Pass Rate |
| `tags` | list[str] | e.g. `injection`, `abstention`, `specialist`, `hallucination`, `official_p6` |
| `review_status` | str | `not_required_technical` / `pending` / `reviewed` |
| `gold_relation` | str or null | only when `review_status = reviewed` |
| `reviewer`, `reviewed_at` | str or null | name/role and date of the qualified reviewer |
| `proposed_relation`, `proposed_by` | str or null | candidate cases only; never used as gold |
