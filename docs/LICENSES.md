# Register of sources, tools and licenses

**Code:** all rights reserved. The repository is published for viewing only; no licence is granted for the code (owner's decision, 2026-10-04). The entries below cover third-party data, models and software, each under its own terms.

Required by the Participant Guide (p.32: "سجل المصادر والأدوات والتراخيص"). Statuses are stated as verified, not assumed.

## 1. Content and data

### 1.1 Quran text: three layers
| Layer | Holder | Terms | How verified |
|---|---|---|---|
| Underlying text and font (`UthmanicHafs_v2-0.zip`: `hafsData_v2-0.csv`, `uthmanic_hafs_v20.ttf`) | King Fahd Glorious Qur'an Printing Complex (KFGQPC) | KFGQPC usage rights: free use in personal and business work, government and institutions, digital and media publishing, websites, software and similar, inside and outside Saudi Arabia; printing Qur'an copies inside the Kingdom and importing them for sale are regulated by Royal Decrees 136/8 and 9/B/46356. The Quranic text must not be altered | Reproduced in full (Arabic and English; Arabic governs) in the quran-text LICENSE, commit `87d7691a`, file SHA-256 `21958de4…dd7e20`. Not read on qurancomplex.gov.sa (unreachable). **Open action**: confirm there |
| Distribution: Quranpedia official data-dump policy | Quranpedia.net | **Use inside apps requires no attribution. Republishing the data, in full or in part, as a downloadable database requires crediting Quranpedia.net with a link and the version number.** Provided without warranty; verification is the user's responsibility | Dump page (version `2026-09-30`) and `quranpedia.net/dumps/LICENSE.md` (version `2026-10-01`), read 2026-10-01 through a web fetch. No dump file was used (quranpedia.net unreachable from the build environment) |
| Distribution actually used: `quran-text` repository (`github.com/quranpedia/quran-text` = `github.com/quran-ws/quran-text`), commit `87d7691a` | Quran.ws (own work); KFGQPC (packages under `sources/kfgqpc/`, "redistributed unmodified") | CC BY 4.0 for Quran.ws's own work, with a permanent **waiver of attribution for use inside a product** (app, website, service, API, tool, research work). Attribution required on republication ("if a third party can obtain the data AS DATA from what you distribute"), in the form: *quran-text by quran-ws — https://github.com/quran-ws/quran-text — CC BY 4.0*. KFGQPC files keep KFGQPC's terms | LICENSE and NOTICE.md read verbatim 2026-10-01 (SHA-256 `21958de4…dd7e20`, `88ac99bf…624eb7`) |

**Tibyan's position: in-app use.** The KFGQPC package (`data/raw/`) and the built corpus database (`data/indexes/`) are git-ignored and not distributed. The API returns matched passages and their ±2-ayah context for a user's query; it does not offer the corpus as a dataset. Under all three layers no attribution is required for this use; Tibyan credits KFGQPC and Quranpedia voluntarily (README, UI footer).

**If Tibyan ever republishes the data** (bulk export, downloadable DB, mirror, corpus-serving endpoint), it must: credit Quranpedia.net with a link and the dump/version identifier; credit *quran-text by quran-ws — https://github.com/quran-ws/quran-text — CC BY 4.0*, marking any modification; and name KFGQPC as publisher of the text under its usage rights.

The KFGQPC font `frontend/public/fonts/kfgqpc_uthmanic_hafs_v20.ttf` is redistributed in the public repository, unmodified, under KFGQPC's usage rights (software and websites).

### 1.2 Hadith text (Sahih al-Bukhari, Sahih Muslim)
Religious authority (the package approves the Sahihayn) is a separate question from dataset licensing; this table covers licensing only.

| Layer | Holder | Terms | How verified |
|---|---|---|---|
| Printed editions (metadata represented in the dataset) | Dar Tawq al-Najat (Bukhari, ed. Zuhayr al-Nasir); Dar Ihya al-Turath al-Arabi (Muslim, ed. M. Fuad Abd al-Baqi) | **Printed-edition reuse status: PENDING VERIFICATION.** The classical texts are centuries old; the editions' editorial apparatus may carry rights | Recorded from the file headers only |
| Digital source named by the package | al-Maktaba al-Shamela (shamela.ws) | Not read (unreachable from the build environment). **Cross-check of the files against Shamela / Dorar: PENDING** | — |
| Route actually used | OpenITI corpus, `github.com/OpenITI/0275AH` @ 44e1c367 | **CC BY-NC-SA 4.0** (OpenITI release record, Zenodo DOI 10.5281/zenodo.10007820; OpenITI Terms of Use). Third-party material stays subject to its own rights | Terms page and release record read 2026-10-02 |

**Tibyan's position:** non-commercial, in-app use with attribution (README «Attribution», UI source section). Raw files and the derived DB are not committed or offered for download. **Attribution:** OpenITI corpus, `github.com/OpenITI/0275AH` @ 44e1c367, derived from al-Maktaba al-Shamela, CC BY-NC-SA 4.0. **Non-commercial only:** a public deployment must stay non-commercial while it serves this data. **Constraints carried forward:** any commercial use or redistribution of the hadith data as a dataset is not covered; ShareAlike applies to adapted material if it is ever distributed.

### 1.3 Tafsir (commentary layer; added to this register 2026-10-04)
Tafsir is shown under «تفسير الآية», separate from the Quran text. It is never searched and a quote is never attributed to it.

| Item | Holder / origin | How Tibyan uses it | Terms | Status |
|---|---|---|---|---|
| Tafsir Mujahid (مجاهد بن جبر; ed. محمد عبد السلام أبو النيل; دار الفكر الإسلامي الحديثة، مصر، الأولى 1410هـ / 1989م) | Quranpedia.net data dump, **version 2026-08-10**, https://quranpedia.net | 114 JSON files, one per surah, in `data/json-data/` (about 1.6 MB). **These files are committed to the repository** and copied into the Docker image | Quranpedia's dump policy as recorded in §1.1: use inside an app needs no attribution; **republishing the data, in full or in part, requires crediting Quranpedia.net with a link and the version number**. Committing the files to a public repository is a republication, so the credit is given here and in the README | Credit given. **To be confirmed:** that the dump policy read on 2026-10-01 (for dump version 2026-09-30) also applies to this tafsir dump and version; and the reuse status of the printed edition's editorial work (not verified) |
| Tafsir al-Tabari (جامع البيان عن تأويل آي القرآن، محمد بن جرير الطبري، ت 310هـ) | Quran.com API v4, tafsir resource 15, https://quran.com | Fetched live, per matched ayah, at request time. Not stored in the corpus database and not committed | **To be confirmed.** The Quran.com API terms of use, and the rights in the edition that resource 15 serves, have not been read or verified; nothing is assumed here | **Open action:** read and record the Quran.com API terms before any public deployment. Until then treat this layer as unverified for public use. It can be turned off (`TAFSIR_ENABLED=false`) or switched to the local files (`TAFSIR_PROVIDER=local`) |

### 1.3a Official Scientific Package Sample Glossary (no longer shown)
The **10 sample terms** of «نماذج لقاموس المصطلحات الأساسية» are official challenge material from the Scientific Package (p.8). Since 2026-10-04 they are **not used by the product**: the glossary is not looked up, not shown in results and not listed as a source. The curated file (`data/curated/dictionary_scientific_package_p8.json`) and the ingestion step remain in the repository, and the ten terms are still written to the corpus database by the build. They are not the Jamhara dictionary. The full Jamhara dictionary (islamic-content.com) is **not** used: its terms permit personal non-commercial benefit only and no dataset or API is offered.

### 1.4 Other data
| Item | Owner | Where used | Terms |
|---|---|---|---|
| `data/ayah-map.csv` from quran-text (per-surah counts only, no text) | Quran.ws | `data/metadata/quran_structure_expected.json` | CC BY 4.0, in-product waiver; counts derived and stored with source and commit |
| `quran-ws/kfgqpc-resources` (checksum list, captured page metadata) | Quran.ws (archive); KFGQPC (files) | Hash cross-check only; nothing ingested | Archive states all KFGQPC rights remain with KFGQPC |
| Synthetic fixtures (`backend/tests/fixtures/`, `eval/fixtures/`) | Tibyan team | Tests and evaluation only; never in the production index | Own work |

## 2. Software (runtime)

Versions as installed on 2026-10-01. License identifiers were read from each installed package's own metadata (Python `importlib.metadata`, npm `package.json`) on 2026-10-01, except SQLite, which is from the project's published terms. Since the premium UI (tag `tibyan-premium-ui-v1`) the web fonts are bundled with the frontend build; no request goes to a font service.

| Package | Version | License (as published by the project) |
|---|---|---|
| FastAPI | 0.142.2 | MIT |
| Uvicorn | 0.54.0 | BSD-3-Clause |
| Pydantic / pydantic-settings | 2.13.5 / 2.15.0 | MIT |
| NumPy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| SciPy (dependency) | 1.17.1 | BSD (classifier `BSD License`) |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| faiss-cpu | 1.15.1 | MIT |
| httpx (LLM adapter HTTP client) | 0.28.1 | BSD-3-Clause |
| SQLite (FTS5) | 3.45.1 (system) | Public domain |
| React / React DOM | 19.3 | MIT |
| Vite | 8.3 | MIT |
| Tailwind CSS | 4.3 | MIT |
| TypeScript | 7.0 | Apache-2.0 |
| IBM Plex Sans Arabic (UI text), self-hosted via `@fontsource/ibm-plex-sans-arabic` | 5.3.0 | SIL Open Font License 1.1 |
| Noto Naskh Arabic (hadith text and quote field), self-hosted via `@fontsource/noto-naskh-arabic` | 5.3.0 | SIL Open Font License 1.1 |
| Reem Kufi (display headings and wordmark), self-hosted via `@fontsource/reem-kufi` | 5.3.0 | SIL Open Font License 1.1 |
| lucide-react (UI icons) | 1.49.0 | ISC |
| tesseract.js (screenshot OCR in the browser; added 2026-10-03) | 7.0.0 | Apache-2.0 |
| tesseract.js-core (Tesseract compiled to WebAssembly; dependency of tesseract.js, served from the site under `/ocr/core/`) | 7.0.0 | Apache-2.0 |
| @tesseract.js-data/ara (Arabic recognition model, served from the site under `/ocr/lang/`) | 1.0.0 | MIT (npm package metadata; see §3 for the model) |
| Small runtime dependencies of tesseract.js: wasm-feature-detect 1.9.0, bmp-js 0.1.0, is-url 1.2.4, idb-keyval 6.3.0, regenerator-runtime 0.13.11, node-fetch 2.7.0 with whatwg-url 5.0.0, tr46 0.0.3, webidl-conversions 3.0.1 (Node only, not used in the browser), opencollective-postinstall 2.0.3 (install-time message) | as listed | Apache-2.0, MIT, MIT, Apache-2.0, MIT, MIT, MIT, MIT, BSD-2-Clause, MIT (each package's `package.json`) |

Dev only: @types/node 22.20.5 (MIT; types for `vite.config.ts`), pytest (MIT), ruff (MIT), @playwright/test 1.56.0 (Apache-2.0; browser E2E and screenshots), @axe-core/playwright and axe-core 4.13.0 (MPL-2.0; accessibility checks, not shipped in the bundle), pip-audit 2.10.1 (Apache-2.0 per its package classifier; run in a throwaway venv, not a project dependency). Deployment base image (not built here): `python:3.11-slim` (Docker official image; Python is PSF-2.0, Debian packages under their own licenses).

## 3. Models

| Model | Type | Origin | License |
|---|---|---|---|
| `char-ngram-lsa-v1` | Classical TF-IDF + truncated SVD, fitted locally on the approved corpus | Built by `scripts/build_embeddings.py` | Own artifact (derived from KFGQPC text; same content terms) |
| `hash-trigram-64` | Test double, tests only | Own code | n/a |
| `ara.traineddata` (`4.0.0_best_int`) | Tesseract LSTM text-recognition model for Arabic, integer-quantised; runs in the visitor's browser, never on the server | Tesseract OCR project's trained models, as packaged by the tesseract.js project (`naptha/tessdata`, npm `@tesseract.js-data/ara` 1.0.0) | npm package declares MIT; the Tesseract project publishes its trained-data repositories under Apache-2.0 (not re-verified from the build environment beyond the package metadata) |

Apart from the OCR model above (which only reads letters from a screenshot in the browser and is never a source of content), no third-party neural model is used. The claim-analysis LLM is an external API service (Google Gemini API or Anthropic Messages API, chosen by `LLM_PROVIDER`) used under that provider's terms once a key is configured; none has been called from the build environment.
