# تِبيان — Tibyan

> **All rights reserved.** The code in this repository is published for viewing only; no licence is granted to use, copy, modify or redistribute it. Each data source keeps its own licence and terms (Quran text and font, hadith files, tafsir): see [`docs/LICENSES.md`](docs/LICENSES.md).
>
> **جميع الحقوق محفوظة.** الكود منشور للاطلاع فقط، ولا يُمنح أي ترخيص لاستخدامه أو نسخه أو تعديله أو إعادة توزيعه. ولكل مصدر بيانات رخصته وشروطه (انظر `docs/LICENSES.md`).

## تشغيل سريع على Windows (عربي)
قبل البدء ثبّت مرة واحدة: **Python 3.11** (الموصى به؛ المدعوم 3.11 حتى 3.14) و**Node.js 22 LTS**.

1. ضع المشروع في مسار بحروف إنجليزية فقط، مثل: **`C:\tibyan`**
2. شغّل: **`setup.cmd`** (أول مرة فقط، يحتاج إنترنت، حتى تظهر `Setup complete.`)
3. شغّل: **`start.cmd`**
4. افتح: **http://localhost:5173**
5. للإيقاف: **`stop.cmd`**

التعليمات المفصلة (المتطلبات، مفتاح Gemini، التحقق من صورة، حل المشكلات): **[`docs/RUN_WINDOWS.md`](docs/RUN_WINDOWS.md)**.
يعمل دون أي مفتاح API؛ المفتاح يفعّل تحليل الادعاء فقط.

## Quick start (Windows, English)
Install once: **Python 3.11** (python.org, tick "Add python.exe to PATH") and **Node.js 22 LTS** (nodejs.org).
**Recommended: Python 3.11. Tested compatible: Python 3.11–3.14.** Setup prefers 3.11 when several versions are installed, and rebuilds `backend\.venv` (safely) if it was made with a different Python. Put the project in `C:\tibyan` (English-only path). Then, in the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1     # first time only (or double-click setup.cmd)
powershell -ExecutionPolicy Bypass -File .\start.ps1     # start (or double-click start.cmd)
powershell -ExecutionPolicy Bypass -File .\stop.ps1      # stop  (or double-click stop.cmd)
```

Open **http://localhost:5173** (API: http://localhost:8000, health: http://localhost:8000/health). Linux/macOS: `./setup.sh`, `./start.sh`, `./stop.sh`.

Works without any API key (LLM_UNAVAILABLE mode: quote verification, source, text, context and evidence; no claim verdict). Step-by-step Windows guide (Arabic): **[`docs/RUN_WINDOWS.md`](docs/RUN_WINDOWS.md)**; English guide and troubleshooting: **`docs/RUN_LOCAL.md`**; optional LLM key: **[`docs/LLM_API_SETUP.md`](docs/LLM_API_SETUP.md)**; data files: `docs/LOCAL_DATA_MANIFEST.md`.

---

Context verifier for Islamic quotations: given a **quote** and the **claim** attached to it, Tibyan checks whether the quote exists in approved sources, whether it is complete, what its context says, and (when a language model is configured) whether the claim is supported, overstated, contradicted, lacks sufficient evidence, or requires a specialist.

Built for the track **أدوات المعرفة والتحقق لتمكين المعرفين بالإسلام** of the AI Challenge for Serving Islamic Content (Bathel Foundation, 2026). The build history is in `docs/BASELINE.md`.

## Status (4 October 2026)
- Runs locally. Not deployed to any public host.
- Without an LLM key it runs in `LLM_UNAVAILABLE` mode: quote verification, source, text, context and evidence, and the result says *«تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً»*. No verdict is ever invented.
- Claim analysis has been run end to end with a real model (Google Gemini) through the full pipeline. **Its quality has not been measured**: there is no saved real-model evaluation and no specialist-reviewed test set yet, so the Evaluation page reports it as pending.
- Corpus: the Quran (KFGQPC Hafs), Sahih al-Bukhari and Sahih Muslim (hadith search `LIMITED_PRODUCTION`), with tafsir shown as a separate commentary layer. Other official sources are not integrated (`docs/CORPUS_COVERAGE.md`).

## What works now
- `POST /api/v1/analyze` with `{quote, claim, language: "ar"}` returns:
  - quote status (EXACT / PARTIAL / AMBIGUOUS / NOT_FOUND; PARAPHRASED reserved and disabled), the verified source, canonical text, a ±2-ayah context window and evidence objects E1…En;
  - evidence strength (SUFFICIENT / LIMITED / INSUFFICIENT; no numeric confidence);
  - claim analysis: SUPPORTED / OVERSTATED / CONTRADICTED / INSUFFICIENT_EVIDENCE / REQUIRES_SPECIALIST, with cited evidence ids, or no verdict when no model is configured.
- The LLM is called only after an **evidence gate** passes, receives only backend evidence, and every output passes a strict schema, a **citation verifier** (ids ⊆ backend ids, no outside sources), a **grounding verifier** (no religious text outside cited evidence) and a **safety lint**, with one controlled retry. Personal-fatwa cases never reach the model; disputed matters are restricted to specialist referral. Details: `docs/AI_SAFETY.md`.
- **Integrated sources:** the Quran (KFGQPC Hafs); Sahih al-Bukhari; Sahih Muslim (with documented gaps). The Sahihayn are approved by the package; their machine-readable files come from OpenITI (Shamela-derived), with the cross-check against Shamela/Dorar PENDING and printed-edition reuse PENDING VERIFICATION. Hadith search is **LIMITED_PRODUCTION**.
- **Commentary layer (never searched, never the source of a quote):** Tafsir al-Tabari for the matched ayah, fetched live from the Quran.com API, with the local Tafsir Mujahid files (`data/json-data`) as fallback. Shown under «تفسير الآية», separate from the Quran text.
- **Not integrated:** Dorar Tafsir, Aqeedah, Fiqh, History and Hadith API verification; Bayyinat; the full Jamhara dictionary; general dawa.center and islamic-content.com content; other Sunnah collections (`docs/OFFICIAL_SOURCE_INVENTORY.md`, `docs/CORPUS_COVERAGE.md`).
- Retrieval: BM25 (SQLite FTS5) plus a vector-space baseline (character n-gram TF-IDF + LSA + FAISS; **not a neural embedding model**, no measured retrieval improvement). A quote that does not match a source word for word is never attributed.
- Arabic RTL UI (desktop / tablet / phone, light and dark) with four pages: verification (`/`), methodology and limits (`/methodology`), evaluation (`/evaluation`, measured numbers only) and sources (`/sources`). The result opens as one summary card (quote status, source, evidence strength, and, when a real model produced it, the claim verdict with a short analysis and a per-part table), followed by three collapsed groups: «النص والسياق» (source, original text in its context, text comparison, evidence map), «الأدلة» (one expandable row per evidence item; long commentary is clipped behind «عرض المزيد») and «التحفظات والمراجع» (limitations, references, technical details). If the AI step fails, the card says so in a visible banner. Quran text (KFGQPC font, framed), hadith text (Naskh), AI analysis and system messages are visually distinct. Examples fill the form with corpus-derived inputs that go through the real pipeline. Design system: `docs/DESIGN_SYSTEM.md`.
- **Text comparison («مقارنة النص»)**: a deterministic word-by-word comparison of the quote with the canonical text (`quote_comparison`): verbatim, normalization-only differences (diacritics, punctuation, alef forms, honorifics…), missing / added / different words, partial quote. Neutral wording, never a judgement of why; the canonical text is never modified. Near matches get a non-definitive comparison inside the first three candidate cards; ambiguous hadith and not-found results get none.
- **Evidence & context map («خريطة الدليل والسياق»)**: source → canonical text (quoted / not in the quote / context) → claim → evidence E1…En → result (`evidence_map`), built only from the response's own data. «أهمية السياق للادعاء» stays «غير محدد» unless a verified AI analysis cited the context. Vertical timeline on phones.
- **Screenshot verification («تحقق من صورة») — hidden in the UI since 2026-10-05** (recognition quality on vowelled and Uthmanic-script text is not good enough to show; the code is kept and is switched back on with `IMAGE_MODE_ENABLED` in `frontend/src/features.ts`). When enabled: a «صورة» tab next to the default «نص» tab. The image is checked (type by content, size, dimensions before decoding), its text is extracted **in the browser** (tesseract.js, Arabic model, served by the site itself), the visitor reviews and edits the suggested quote and claim, and only the confirmed text goes through the same `/api/v1/analyze` request. The image is never uploaded or stored and is not evidence (`docs/PRIVACY.md`). The API is unchanged apart from three additive response fields (`quote_comparison`, `candidate_comparisons`, `evidence_map`).
- Hardened API: request ids, security headers, body limit, per-IP rate limit, request timeout, safe JSON errors, docs disabled and CORS restricted in production, `/health` with components. Details: `docs/SECURITY.md`.

## Configure the LLM (optional)
In `.env` (project root): `LLM_PROVIDER=gemini` (Google AI Studio key) or `anthropic`, `LLM_MODEL=<model id>`, `LLM_API_KEY=<key>`; details in `docs/LLM_API_SETUP.md`. Without these, source verification works and no claim verdict is produced. `LLM_PROVIDER=test_double` runs an always-abstaining test double outside production.

Gemini notes (observed on 4 October 2026 with a free-tier key; Google changes these, so check your own account):
- `LLM_MODEL` must be a model your key can actually call. Use an id shown in Google AI Studio. A model can still appear in the model list after it is retired for new users; the call then fails with HTTP 404 and the result banner shows Google's message naming the replacement.
- The free tier is small: 20 requests per day per model on `gemini-3.5-flash`, after which every analysis returns HTTP 429 until the quota resets. One analysis can use more than one request. Anything beyond personal testing needs billing enabled.
- HTTP 503 means the model is overloaded on Google's side; retry, or choose another model. `gemini-3.5-flash-lite` was the most reliable in testing.
- Gemma models answered too slowly for the default `LLM_TIMEOUT_S=30`.

## Build the corpus and indexes
The corpus database and the search indexes are **not in the repository** (`data/indexes/` and `data/raw/` are git-ignored). `setup` builds them; to do it by hand:
```bash
python scripts/build_corpus.py       # download + verify sources, ingest, FTS, validate, vector index
python scripts/build_embeddings.py   # vector index only (if /health reports search_mode LEXICAL_ONLY)
```
`build_corpus.py` needs network access: it downloads the KFGQPC Quran package and the OpenITI hadith files, checks their pinned SHA-256 hashes, and stops at the first failure. It writes `data/indexes/tibyan.sqlite3`, `lsa_model.npz`, `semantic.faiss`, `semantic_ids.json` and `semantic_meta.json`. If the three `semantic*` files are missing the app still runs, with lexical search only.

## Manual steps (developers; the setup scripts do all of this)
Requires network access to one of the routes in `data/metadata/quran_kfgqpc_hafs_v2.json`.
```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && cd ..
python scripts/build_corpus.py      # Quran + Sahihayn → FTS → validate → embeddings
python eval/multi_source_eval.py    # hadith retrieval, cross-source safety
python eval/compare_retrieval.py    # retrieval comparison, writes eval/results/
python eval/run_safety_eval.py      # guard-rail evaluation with scripted model outputs
python eval/provider_health.py      # one real call: run first once a key is set
python eval/stability.py            # needs a real LLM key
python eval/grounded_vs_ungrounded.py   # needs a real LLM key
```

## Run the parts by hand (developers)
```bash
cd backend && . .venv/bin/activate
uvicorn app.main:app --port 8000
pytest                              # 498 tests (+1 live-model test skipped without a key); needs the built corpus
```
```bash
cd frontend && npm install && cp .env.example .env && npm run dev
```
Browser E2E (backend on :8000 with `RATE_LIMIT_PER_MINUTE=0`, then `npm run build && npx vite preview --port 4173`):
```bash
cd frontend && npx playwright test        # desktop/tablet/mobile (some scenarios run on one size only), axe-core WCAG 2.1 AA
cd frontend && npm run test:unit          # screenshot text segmentation (Node test runner)
```
Performance and load: `python eval/perf_benchmark.py`, `python eval/load_test.py --pid <uvicorn pid>`. Deployment: `docs/DEPLOYMENT.md`.

## Documents
| File | Purpose |
|---|---|
| `docs/OFFICIAL_REQUIREMENTS.md` | What the official documents require |
| `docs/SOURCES.md` | Which sources may be used, and the dataset in use |
| `docs/LICENSES.md` | Register of sources, tools and licenses |
| `docs/SCIENTIFIC_POLICY.md` | Safety rules the software must enforce |
| `docs/SCOPE.md` | Frozen V1 scope |
| `docs/ARCHITECTURE.md` | Stack, pipeline, modules |
| `docs/DATA_PIPELINE.md` | Source → raw → ingestion → validation → indexes → evidence |
| `docs/METHODOLOGY.md` | Methods, evaluation set, measured results and their limits |
| `docs/LIMITATIONS.md` | Known limitations and what the system does about each |
| `docs/AI_SAFETY.md` | The LLM's role, prohibitions, gate, verifiers, routing, abstention |
| `docs/PROMPTING.md` | Prompt version, structure, structured output, provider config |
| `docs/ACCEPTANCE_CRITERIA.md` | How each phase is judged done |
| `docs/JUDGING_MAP.md` | Mapping to the official judging criteria |
| `docs/OFFICIAL_SOURCE_INVENTORY.md` | Every official source: URL, method, terms, access, status, blocker |
| `docs/CORPUS_COVERAGE.md` | Records acquired / validated / indexed per source |
| `docs/RUN_LOCAL.md` | How to install, run, stop and troubleshoot locally |
| `docs/LOCAL_DATA_MANIFEST.md` | Every data file: source, hash, committed / downloaded / generated |
| `docs/SECURITY.md` | Threat model, API hardening, audits, logging |
| `docs/PRIVACY.md` | What data is handled, where it goes and how long it lives (typed text and screenshots) |
| `docs/EVALUATION.md` | Every measured number, how it was produced, and what is not measured |
| `docs/DEPLOYMENT.md` | Docker / Render backend, Netlify / Cloudflare Pages frontend, env vars |
| `docs/OPERATIONS.md` | Health, logs, incidents, enabling the LLM, rebuilding the corpus |
| `docs/BASELINE.md` | What existed before, what was built when (Part A pre-challenge / Part B challenge period) |
| `docs/PRE_CHALLENGE_FREEZE.md` | Frozen pre-challenge state: commit, capabilities, metrics, what is not completed |
| `docs/CHALLENGE_PERIOD_PLAN.md` | Plan written before the 4–6 October challenge period |

## Attribution
Quran text and the Uthmanic Hafs font: King Fahd Glorious Qur'an Printing Complex (KFGQPC), used under its usage rights. Distributed via Quranpedia (quranpedia.net) / Quran.ws (`quran-text`). Used inside the application only; no attribution is required for that use, given voluntarily. Republication rules: `docs/LICENSES.md` §1.1.

Hadith text (Sahih al-Bukhari, Sahih Muslim): OpenITI corpus (`github.com/OpenITI/0275AH`), derived from al-Maktaba al-Shamela, under **CC BY-NC-SA 4.0**: attribution required, **non-commercial use only**, share-alike for adapted material. The files are downloaded at build time and are not in this repository (`docs/LICENSES.md` §1.2).

Tafsir: Tafsir Mujahid files from the Quranpedia.net data dump (version 2026-08-10, https://quranpedia.net); Tafsir al-Tabari fetched live from the Quran.com API v4. Reuse terms for both are recorded as to be confirmed in `docs/LICENSES.md` §1.3.

## Secrets
Copy `.env.example` to `.env` locally. `.env` is git-ignored. Never commit keys.
