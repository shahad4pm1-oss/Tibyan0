# Local data manifest

Every file Tibyan needs to run locally, where it comes from, and who creates it. `setup.ps1` / `setup.sh` handle all of them; **no file has to be provided by hand** unless the automatic download is impossible on your network (then see "Manual fallback").

## 1. Downloaded automatically by setup (not committed)
Each file is accepted only if its SHA-256 equals the pinned value; anything else is rejected.

| File (under the project folder) | Purpose | Source | SHA-256 | Size |
|---|---|---|---|---|
| `data/raw/kfgqpc/UthmanicHafs_v2-0.zip` | Quran text (KFGQPC Uthmanic Hafs v2.0) | KFGQPC package; tried in order: qurancomplex.gov.sa, cdn.quran.ws, `raw.githubusercontent.com/quranpedia/quran-text/87d7691a…/sources/kfgqpc/UthmanicHafs_v2-0.zip` | `a7b0e5591945712ec5e4d6142938ae4d1e9b49bdc89dff06222789bfebdfd72c` | 10,729,285 B |
| `data/raw/openiti/0256Bukhari.Sahih.Shamela0001681-ara1` | Sahih al-Bukhari (Shamela edition file via OpenITI) | `raw.githubusercontent.com/OpenITI/0275AH/44e1c36738a2bf5c14dafa232a6ae1891e6171cd/data/0256Bukhari/0256Bukhari.Sahih/0256Bukhari.Sahih.Shamela0001681-ara1` | `16f95173b9ea1927b577ff85dc7e2a8351b8287e4ea9863782c4c5fc87ac8132` | 6,039,255 B |
| `data/raw/openiti/0261Muslim.Sahih.Shamela0001727-ara1.mARkdown` | Sahih Muslim (Shamela edition file via OpenITI) | `raw.githubusercontent.com/OpenITI/0275AH/44e1c36738a2bf5c14dafa232a6ae1891e6171cd/data/0261Muslim/0261Muslim.Sahih/0261Muslim.Sahih.Shamela0001727-ara1.mARkdown` | `8126f063f53504b68d6e9e133cec049c10acf498c501f5f4897013efc1e56d9e` | 4,933,663 B |

Why not committed: the raw packages are third-party data used in-app and are not redistributed by this repository (`LICENSES.md`).

## 2. Generated automatically by setup (not committed)
Built by `scripts/build_corpus.py` (fetch → ingest Quran → fetch hadith → ingest Sahihayn → verify and ingest glossary → FTS → validate → embeddings).

| File | Purpose | Notes |
|---|---|---|
| `data/indexes/tibyan.sqlite3` | Corpus database: 6,236 ayat, 10,494 hadith records, 10 glossary terms (unused since 2026-10-04), FTS5 indexes `passages_fts` (Quran) and `hadith_fts` | ~87 MB; validated (V01–V16); Quran text digest pinned (`5634b860…c7c65a`) |
| `data/indexes/lsa_model.npz` | LSA model (character n-gram TF-IDF + SVD) for Quran semantic search | ~19 MB; deterministic |
| `data/indexes/semantic.faiss` | FAISS vector index over the Quran | ~6 MB |
| `data/indexes/semantic_ids.json`, `semantic_meta.json` | index row mapping and metadata | — |
| `backend/.venv/` | Python environment | from `backend/requirements.txt` + `backend/constraints.txt` |
| `frontend/node_modules/` | frontend packages | from `frontend/package-lock.json` (`npm ci`) |
| `.env` | local settings | copied from `.env.example`; never committed |
| `logs/`, `.run/` | run logs and process records of `start.ps1` | — |

If the vector files are missing the app still runs (LEXICAL_ONLY, with a warning); exact and partial matching are unaffected.

## 3. Committed in the repository

| File | Purpose | SHA-256 |
|---|---|---|
| `data/metadata/quran_kfgqpc_hafs_v2.json` | Quran provenance, pinned hashes, pinned Quran text digest | — |
| `data/metadata/quran_structure_expected.json` | expected ayah counts (validation V11) | — |
| `data/metadata/hadith_sahihayn_openiti.json` | hadith provenance, pinned hashes, grading rule | — |
| `data/curated/dictionary_scientific_package_p8.json` | Official Scientific Package Sample Glossary (10 terms; ingested but not used by the product since 2026-10-04) | `3119d628e74da0b9b04c0f056c64870e959b76c87b2886571d02a6af9b1677c2` |
| `frontend/public/fonts/kfgqpc_uthmanic_hafs_v20.ttf` | KFGQPC Quran font | `d560bbbc7a90a4f4d416d206a5ac48bd8a1ad00273d64d232f16ca54941bd041` |
| `frontend/src/examples.json` | demo inputs (read from the corpus by `scripts/make_demo_examples.py`) | — |

## 4. Optional, never required
| File | Purpose |
|---|---|
| `data/raw/package/scientific_package_v1448-3-20.pdf` | the official Scientific Package PDF (SHA-256 `23d776c7…5a1cb9c7`). If present, `scripts/verify_dictionary_extract.py` also re-checks the glossary against it; otherwise only the rule check runs. Not committed (organiser's document). |

## 5. Manual fallback (only if downloads fail)
Download the three files in §1 in a browser, put them at exactly those paths (create the folders `data\raw\kfgqpc` and `data\raw\openiti`), and run setup again. Setup verifies the SHA-256 and continues without network access.

## 6. Internet
- **Needed once**, during setup: Python packages (PyPI), frontend packages (npm), and the three source files.
- **Not needed after setup**: Quran and hadith search, context, evidence and the whole UI run locally (tested with the network disabled). All UI fonts (IBM Plex Sans Arabic, Noto Naskh Arabic, Reem Kufi) and the Quran font are bundled, so the UI looks the same offline.
- **A real cloud LLM always needs internet.**

## Tafsir commentary (data/json-data/)

- 114 files `NNN_<surah-slug>.json`, split from `tafsir-book-269_json.gz` (Tafsir Mujahid, Quranpedia.net dump 2026-08-10).
- Surahs 1 and 109 have no entries in this work; their files exist with an empty `ayahs` list.
- Loaded lazily per surah by `app/corpus/tafsir.py` (`LocalTafsirCorpus`, LRU of 8 surahs). Settings: `TAFSIR_ENABLED`, `TAFSIR_DATA_DIR`.
- Shown to the model and to users as a separate `source_commentary` evidence item: `[النص القرآني]: … [تفسير الآية]: …`.

## Tafsir al-Tabari loader (Quran.com API v4)

- `backend/app/corpus/tafsir_loader.py` — `TabariTafsirManager.get_ayah_context(surah, ayah)`, async, in-memory LRU cache, retries, and clean error results instead of exceptions. Resource id 15.
- Not wired into the analysis pipeline yet, and not validated against the live API (no network in the build environment). Check `resource_id` / `resource_name` in the first live response.
- al-Tabari died in 310 AH; confirm with the organisers that this satisfies the "first three centuries" rule.
