# Operations

## 1. Health
`GET /health` (never rate-limited):

| Field | Meaning |
|---|---|
| `status` | `ok`: corpus and lexical search ready, integrity check passed. `degraded`: corpus integrity check failed (claim analysis disabled). `unavailable`: no corpus loaded (analyze returns 503) |
| `components.database`, `components.corpus` | ready, corpus version, passage count (6,236), `integrity_ok` |
| `components.lexical_search` | FTS5 ready |
| `components.semantic_index` | ready, model, reason if not. If not ready the API runs `LEXICAL_ONLY` and adds the `SEMANTIC_SEARCH_UNAVAILABLE` warning to each response; exact and partial matching are unaffected |
| `components.llm` | `configured`, provider, model, `mode` (`REAL_LLM` / `LLM_UNAVAILABLE`; `TEST_DOUBLE_NON_PRODUCTION` only outside production), also at top level as `llm_mode`, reason, prompt version. Never the key |
| `config_problems` | production misconfigurations (e.g. rate limit 0, no https CORS origin, test double). Should be empty |

## 2. Logs
Logger `tibyan` writes to stdout/stderr. One `tibyan.audit` JSON line per analyze request: request id, timestamp, status codes, retrieved and evidence ids, routing level, gate, strength, relation, overrides, provider/model, prompt version, attempts, token counts, error category, search mode, latency. **No quote or claim text and no keys** (`LOG_RAW_INPUT=false`; enforced by a test). Every response carries `X-Request-ID`; error responses include `request_id` in the body. Use it to find the audit line.

## 3. Common incidents
| Symptom | Likely cause | Action |
|---|---|---|
| `/health` `unavailable`, analyze 503 `CORPUS_NOT_AVAILABLE` | DB missing, or production given a fixture corpus | Rebuild: `python scripts/build_corpus.py`; check `DATABASE_PATH` |
| `/health` `degraded`, `integrity_ok: false` | DB modified after build | Rebuild the corpus; do not hand-edit the DB |
| `search_mode: LEXICAL_ONLY` | FAISS / LSA files missing or unreadable | `python scripts/build_embeddings.py`; service keeps working meanwhile |
| Many 429s | Rate limit reached, or `TRUST_PROXY_HEADERS` wrong (all users share the proxy IP) | Behind a proxy set `TRUST_PROXY_HEADERS=true`; raise `RATE_LIMIT_PER_MINUTE` if needed |
| 504 `TIMEOUT` | Slow LLM provider or overloaded instance | Check provider status; lower `LLM_TIMEOUT_S`; add instances |
| Claim analysis always `ANALYSIS_UNAVAILABLE` | No LLM configured, or provider errors | Expected without a key. With a key: `python eval/provider_health.py` |
| Browser CORS errors | Frontend origin not in `CORS_ORIGINS`, or not https in production | Add the exact https origin |

## 4. Enabling the LLM (when a key exists)
1. Set `LLM_PROVIDER=anthropic`, `LLM_MODEL=<current model id>`, `LLM_API_KEY` (host secret store only). Restart.
2. `/health` → `llm_mode = REAL_LLM`.
3. Run `eval/provider_health.py`, then `eval/stability.py` and `eval/grounded_vs_ungrounded.py`; review results before announcing the feature. Until then the evaluation page keeps showing "Pending real-model validation".

## 5. Rebuilding the corpus
`python scripts/build_corpus.py` (fetch → verify SHA-256 → ingest → FTS → validate → embeddings). Fails closed on any mismatch. Then `python scripts/make_demo_examples.py` re-checks that the demo examples still demonstrate their states.

## 6. Running the browser E2E suite
```bash
RATE_LIMIT_PER_MINUTE=0 CORS_ORIGINS=http://localhost:4173 backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000 &
cd frontend && npm run build && (npx vite preview --port 4173 &) && npx playwright test
```
`PW_CHROMIUM=<path to chrome>` selects a preinstalled Chromium. Screenshots are written to `docs/screenshots/redesign/` (quantised to 256 colours to keep the repository small; pre-redesign screenshots are in the history at tag `tibyan-runnable-local-v1`).

## 7. Releases
Tag each release; keep `PIPELINE_VERSION` (`0.4.0-phase4`) and the corpus version visible in responses (`metadata`) and on `/methodology`.
