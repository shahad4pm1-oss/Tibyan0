# Prompting (claim analysis)

## Version
| Item | Value |
|---|---|
| Prompt version | `claim_analysis_v1` (setting `PROMPT_VERSION`) |
| Files | `backend/app/prompts/claim_analysis_v1.system.txt`, `.user.txt`, `.retry.txt` |
| Fingerprint | SHA-256 of the three files, first 16 hex chars returned as `metadata.prompt_sha256` in every response |

Changing any prompt file changes the fingerprint. A behavioural change must get a new version name (`claim_analysis_v2`) and be re-evaluated.

## Message structure
- **System message** = SYSTEM RULES, relation definitions, output format. Nothing user-controlled is ever placed here.
- **User message** = three delimited parts:
  1. `TASK`, `CONTENT_LEVEL`, `LEVEL_GUIDANCE` (backend-generated);
  2. `=== UNTRUSTED USER DATA ===` with `<user_quote>` and `<user_claim>`, each a JSON string in which `<`, `>` and `=` are escaped as `<`, `>`, `=`. User text therefore cannot close the block, open a fake `=== VERIFIED EVIDENCE ===` section or forge an `<evidence>` tag (tested);
  3. `=== VERIFIED EVIDENCE ===` with source title/edition, match status and reference, and `<evidence id="E…" role="…" reference="s:a">canonical text</evidence>` lines. Evidence text is `original_text` read from the corpus.
- **Retry** (at most one): the same messages plus a `CORRECTION (system)` block listing the issue codes and the allowed evidence ids. The rejected output is not sent back.

## Structured output
- Sent to the provider: `output_config.format = {"type": "json_schema", "schema": provider_json_schema()}` (Anthropic Messages API; documented at platform.claude.com, structured outputs page, read 2026-10-01). The schema uses only vendor-supported features (types, enum, required, nested objects, `additionalProperties: false`).
- Enforced locally by `LLMClaimOutput` (strict, `extra="forbid"`): length limits, evidence-id format, no duplicates, substantive relations must cite evidence, `REQUIRES_SPECIALIST ⇔ needs_specialist`, abstentions need `uncertainty_reason`, `key_evidence ⊆ evidence_ids`.
- Tolerated without "repair": a single surrounding ```json fence, and letter case of the relation label (the vendor documents that enum case is not guaranteed). Nothing else is altered: any other deviation is a rejection.

## What the prompt does not do
- It never asks the model to use general knowledge, to "think step by step", or to output reasoning. Output is a brief reason plus evidence ids.
- It never gives the model religious content beyond the supplied evidence.

## Provider configuration
`LLM_PROVIDER=gemini` or `anthropic`, `LLM_MODEL=<model id from the provider's current model list>`, `LLM_API_KEY=<secret>`. Adapters read only Tibyan's settings (`LLM_BASE_URL`, empty = the provider's official endpoint), never `ANTHROPIC_*`, `GOOGLE_*` or `GEMINI_*` environment variables. Gemini: `generationConfig.responseMimeType = "application/json"` with `responseJsonSchema = provider_json_schema()`; if the service rejects the schema (HTTP 400 naming the schema) the call is repeated once in JSON mode only, and Tibyan's own strict schema validation and verifiers apply to every output either way. Thought parts are discarded. `LLM_TEMPERATURE` is unset by default (provider default). Model choice is an open decision; no model has been run yet.

## Cost telemetry
Tokens and latency are recorded per request (`metadata.llm_usage`, audit log). Cost is computed only if the operator sets `LLM_PRICE_INPUT_PER_MTOK` and `LLM_PRICE_OUTPUT_PER_MTOK` from the provider's current price list; there are no built-in prices.
