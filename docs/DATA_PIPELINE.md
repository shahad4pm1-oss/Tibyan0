# Data pipeline

```
source (KFGQPC UthmanicHafs_v2-0.zip)
  ↓  scripts/fetch_quran.py        download, accept only if SHA-256 matches the pinned digest
raw data (data/raw/kfgqpc/, not committed)
  ↓  scripts/ingest_quran.py       CSV → canonical passages + context links (app/corpus/quran.py)
ingestion
  ↓  scripts/build_fts.py          FTS5 index from APPROVED sources only; records original_text digest
  ↓  scripts/validate_corpus.py    13 checks; exit 1 on any failure (app/corpus/validation.py)
validation
  ↓
canonical database (data/indexes/tibyan.sqlite3, not committed)
  ↓
FTS (passages_fts, BM25)
  ↓  scripts/build_embeddings.py   OFFLINE: fit local LSA model, embed APPROVED passages
embeddings (lsa_model.npz)
  ↓
FAISS (semantic.faiss + semantic_ids.json + semantic_meta.json)
  ↓  request time (app/services/analysis_pipeline.py)
hybrid retrieval  (BM25 top 20 + semantic top 20 → lexical_first ordering; RRF available)
  ↓
quote matcher → source resolver  (deterministic; no LLM)
  ↓
context  (Quran: matched ayat ± 2 within the surah; hadith: the single unit)
  ↓
evidence (E1…En, canonical text read from the DB)
```

One command runs the whole build: `python scripts/build_corpus.py` (about 10 s). It stops at the first failing step.

## 1. Acquisition
- **Underlying text**: KFGQPC `UthmanicHafs_v2-0.zip` (data v2.0, update 13.0).
- **Distribution path**: Quranpedia / Quran.ws repository `quran-text` at commit `87d7691a`, which redistributes the KFGQPC package unmodified. No quranpedia.net dump file was used.
- **Pinned** in `data/metadata/quran_kfgqpc_hafs_v2.json`: filename, size, SHA-256, MD5, SHA-1, official URL, acquisition routes, and the three layers of reuse terms.
- **Routes tried in order**: official KFGQPC URL → cdn.quran.ws mirror → `raw.githubusercontent.com/quranpedia/quran-text/<pinned commit>/sources/kfgqpc/UthmanicHafs_v2-0.zip`. In the build environment only the third route is reachable; it was the one used on 2026-10-01.
- **Verification**: any file whose SHA-256 is not `a7b0e559…bfebdfd72c` is rejected and deleted. That digest also matches the kfgqpc-resources archive list, and the file's MD5/SHA-1 match KFGQPC's own published checksums.
- **Reuse**: in-app use, no attribution required (Quranpedia dump policy, quran-text in-product waiver, KFGQPC usage rights). The raw package and DB are never committed. Republication rules: `LICENSES.md` §1.1.

## 2. Canonical format (table `passages`)
| Field | Quran value | Notes |
|---|---|---|
| `id` | `quran:<surah>:<ayah>` e.g. `quran:2:191` | stable |
| `rowid_int` | 1…6236 in mushaf order | FTS / FAISS key |
| `source_id` | `quran` | |
| `reference` | `2:191` | display |
| `sequence` | publisher row order | |
| `parent_id` | `quran:<surah>` | context never crosses it |
| `original_text` | publisher `aya_text` minus the trailing separator and ayah-number glyph | **only text ever displayed** |
| `normalized_text` | `normalize_for_search(aya_text_emlaey)` | search only |
| `normalized_text_alt` | `normalize_for_search(original_text)` | search only |
| `metadata_json` | surah_number, ayah_number, surah_name, surah_name_en, juz, page, line_start/end, publisher_row_id, **publisher_aya_text** (verbatim), publisher_aya_text_emlaey, trailing_separator, ayah_mark_glyph | |

Why the ayah-number glyph is removed from `original_text`: it is a code point (U+FC00 onwards, Arabic Presentation Forms) that only the KFGQPC font draws as an ayah number; any other font draws an unrelated ligature. The number is kept in structured fields, the full publisher string is kept verbatim, and check V12 proves `original_text + separator + glyph == publisher_aya_text` for every ayah. One row (2:286) uses U+0020 instead of U+00A0 before the glyph, as the publisher's `read.me` notes.

`context_links`: `previous`/`next` between consecutive ayat of the same surah only (12,244 links). Hadith get no neighbour links.

`sources`: one row per source with `verification_status` ∈ APPROVED / PENDING_REVIEW / REJECTED and `source_type` ∈ quran / hadith / commentary / synthetic_fixture.

`corpus_info`: `corpus_kind` (production | test_fixture), `corpus_version`, `original_text_sha256`.

## 3. Approval gate (three layers)
1. **Index build**: `build_fts` and `build_embeddings` read only APPROVED sources, and in production never `synthetic_fixture`.
2. **Query time**: every repository query joins `sources` and re-checks status (`CorpusRepository._eligible`), so even a polluted index cannot surface an ineligible passage (tested).
3. **Validation**: V01 and V10 fail a production corpus containing any non-APPROVED or synthetic source, or any ineligible row in the index.

## 4. Validation checks (`app/corpus/validation.py`)
| ID | Check |
|---|---|
| V01 | statuses valid; production: only APPROVED, no synthetic, `corpus_kind=production` |
| V02 | `PRAGMA foreign_key_check` clean |
| V03 | no duplicate passage ids or (source, sequence) |
| V04 | reference non-empty |
| V05 | canonical text non-empty |
| V06 | search copies exist and equal a fresh normalization of their inputs (detects stale/altered copies) |
| V07 | structural metadata present; Quran id matches surah/ayah |
| V08 | Quran order: ayat consecutive from 1 in each surah, surahs ascending |
| V09 | context links resolve, stay within one surah/source, are adjacent |
| V10 | FTS index contains exactly the eligible passages |
| V11 | 6,236 ayat, 114 surahs, per-surah counts equal `quran_structure_expected.json` (independent KFGQPC release) |
| V12 | `original_text` reconstructs the publisher `aya_text` exactly |
| V13 | digest of all `original_text` equals the digest recorded at build time |

Corruption tests (`backend/tests/test_corpus_validation.py`) alter a copy of the real DB in eight ways and assert the expected checks fail.

## 5. Hadith: Sahih al-Bukhari and Sahih Muslim (2026-10-02)
1. **Acquire** `scripts/fetch_hadith.py`: downloads the two OpenITI files from `raw.githubusercontent.com/OpenITI/0275AH/44e1c367…` and accepts each only if size and SHA-256 equal `data/metadata/hadith_sahihayn_openiti.json` (Bukhari `16f95173…7ac8132`, 6,039,255 bytes; Muslim `8126f063…1e56d9e`, 4,933,663 bytes). Raw files stay in `data/raw/openiti/` (git-ignored).
2. **Parse** `app/corpus/openiti_hadith.py`. Bukhari: a record starts at the heading `### | N - ` (the edition's number) after the first book heading; extra numbers printed with the same text are kept in `numbers_covered`; the record ends at the next non-page heading, so chapter titles, mu'allaq preambles and «تعليق مصطفى البغا» never enter a record. Muslim: narrations start at `# (N)` (Abd al-Baqi number); narrations with the same N form one record. Narrations that start at a `### $ <text>` heading without a number (192, mostly Kitab al-Iman) become records with `hadith_number = null`, internal id `hadith:muslim:u:<book>:<chapter>:<ordinal>` and a locator; a leading bare digit in such a heading is removed as markup. Records with fewer than 3 Arabic words (stray markup) are dropped. Nothing is numbered by inference.
3. **Transform** (documented, reversible to the file text): T1 remove OpenITI markup (page markers, milestones, `~~`, `# `, stray HTML); T2 join paragraph lines with a space, narrations with a newline; T3 collapse whitespace. No letter, diacritic or punctuation is changed.
4. **Ingest** `scripts/ingest_sahihayn.py` → sources `hadith:bukhari`, `hadith:muslim` (`source_type = hadith`); passages `hadith:<collection>:<number>`; metadata: collection, Arabic name, number(s), book, chapter, numbering, grading rule fields, source-file line. No previous/next links (adjacent hadith are not context).
5. **Index** `hadith_fts` (separate from the Quran's `passages_fts`, so Quran BM25 statistics are unchanged): `normalized_text` = `normalize_hadith_search` (hnorm-v1: NFKC, norm-v1, honorific formulas removed), `normalized_text_alt` = plain norm-v1. The LSA/FAISS index stays Quran-only.
6. **Validate** V14 (source type known, provenance and license present), V15 (hadith id = source:number, grading authority allowed and not model-generated, no markup), V10 (each index holds only its own source group), V13 (whole-corpus digest, and the Quran digest equal to the Phase 2 pin).

The generic JSONL importer (`app/corpus/hadith.py`) remains for future collections and is still exercised only with synthetic non-religious fixtures.

## 5b. Official Scientific Package Sample Glossary (p.8; records = 10; not the Jamhara dictionary)
Since 2026-10-04 the glossary is not used by the product: it is not looked up, not shown in results and not listed as a source. The build step below still runs and still fills the `terms` table.

`data/curated/dictionary_scientific_package_p8.json` holds the 10 entries of «نماذج لقاموس المصطلحات الأساسية», with both the corrected text and the PDF text layer as extracted. The PDF's text layer stores lam-alif ligatures reversed (e.g. «االستسالم» for «الاستسلام»); `scripts/verify_dictionary_extract.py` proves each corrected field differs from the text layer only by that defect and, when the package PDF is present, that the text-layer strings occur in a fresh extraction of the SHA-256-pinned file. `scripts/ingest_dictionary.py` refuses to ingest if verification fails. Entries go to the `terms` table, never to a passage index (validation V16).

## 6. Rebuild triggers
Change of raw package (Quran or hadith), curated terminology file, normalizer version, ingestion code, or embedding model → rerun `build_corpus.py` (fetch Quran → ingest Quran → fetch hadith → ingest Sahihayn → verify and ingest terminology → FTS → validate → embeddings). The semantic retriever refuses an index whose recorded `original_text_sha256` differs from the DB, and the API then runs LEXICAL_ONLY.
