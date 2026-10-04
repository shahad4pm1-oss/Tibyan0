# Challenge-period work plan (4–6 October 2026)

**Status: PLANNED, NOT STARTED.** Nothing below has been done. Every item will be committed after the tag `tibyan-runnable-local-v1` (the last pre-challenge state; see `PRE_CHALLENGE_FREEZE.md` §2b), and results will be recorded only once they have actually been measured. Starting point: `PRE_CHALLENGE_FREEZE.md`.

Prerequisites to obtain at the start: an LLM API key (project credentials, held in environment variables / host secrets only), hosting accounts (backend and static frontend), a public GitHub account, and, where available, a qualified specialist reviewer.

## Day 1 — 4 October: real model
1. **Real LLM integration.** Configure `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` from the environment; run `eval/provider_health.py`; fix any adapter or schema issue it reveals.
2. **Real-model safety and stability.** Run the 25 technical cases against the real model (not the scripted double); run `eval/stability.py` (repeat runs, label agreement); real prompt-injection cases.
3. **Grounded vs ungrounded.** Run `eval/grounded_vs_ungrounded.py`; report results as measured, including negative ones.
4. **Token, latency and cost.** Record real input/output tokens, per-request latency (p50 / p95) and cost from the provider's current price list into `eval/results/live_llm_eval.json`.
5. **Fix issues found by real-model testing** (verifier false positives, retry behaviour, prompt wording), without loosening routing or the gate to obtain more AI answers. Re-run the regression after each fix.

## Day 2 — 5 October: review, deployment, live demo
6. **Specialist review** of evaluation cases where a qualified reviewer is available; record reviewer, date and decisions; only reviewed cases become gold. Compute classification metrics only on reviewed cases.
7. **Production deployment.** Backend from `Dockerfile` / `render.yaml`; frontend via Netlify or Cloudflare Pages; set `CORS_ORIGINS`, `VITE_API_BASE_URL`, rate limit and LLM secrets; follow the checklist in `DEPLOYMENT.md` §5.
8. **Live-demo validation.** Run the browser E2E suite and the four examples against the live URL; record live `/health`, latency and any defects.
9. **Public GitHub preparation.** Public repository, README, licenses, attribution, secret scan of the full history before publishing.

## Day 3 — 6 October: finish and submit
10. **Final UX fixes** found through live testing (no new scope).
11. **Final measurable evaluation.** Re-run retrieval, guard-rail, real-model, performance and load evaluations on the final build; update the `/evaluation` page from the result files only.
12. **Final documentation and submission materials.** Update `BASELINE.md` (challenge-period section, separated from pre-challenge work), `EVALUATION.md`, `LIMITATIONS.md`; demo video / screenshots; submission form content per the Participant Guide.

## Rules carried over
- No Quran or hadith text typed from model memory; no fabricated metrics, reviews, licenses or deployment claims.
- Test doubles stay test-only; no mock AI in production.
- If a prerequisite (key, hosting, reviewer) is still missing, the item is reported as blocked, not simulated.
