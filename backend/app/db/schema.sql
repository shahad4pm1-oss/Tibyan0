-- Tibyan canonical corpus schema (Phase 2; multi-source extension 2026-10-02)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id                  TEXT PRIMARY KEY,               -- e.g. 'quran', 'bukhari'
    source_type         TEXT NOT NULL CHECK (source_type IN ('quran','quran_translation','hadith','tafsir','commentary',
                                     'aqeedah','fiqh','seerah','history','dawah','shubuhat','dictionary',
                                     'synthetic_fixture')),
    title               TEXT NOT NULL,
    author              TEXT,
    edition             TEXT NOT NULL,
    publisher           TEXT,
    source_url          TEXT,
    license_note        TEXT NOT NULL,
    verification_status TEXT NOT NULL CHECK (verification_status IN ('APPROVED','PENDING_REVIEW','REJECTED')),
    acquired_at         TEXT NOT NULL,
    corpus_version      TEXT NOT NULL,
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS passages (
    id                  TEXT PRIMARY KEY,               -- e.g. 'quran:2:191', 'bukhari:1'
    rowid_int           INTEGER UNIQUE NOT NULL,        -- stable integer key for FTS/FAISS mapping
    source_id           TEXT NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    reference           TEXT NOT NULL,                  -- display reference, e.g. '2:191'
    sequence            INTEGER NOT NULL,               -- global order within the source
    parent_id           TEXT,                           -- e.g. 'quran:2' (surah) or hadith book id
    original_text       TEXT NOT NULL CHECK (length(trim(original_text)) > 0),  -- canonical display text
    normalized_text     TEXT NOT NULL CHECK (length(trim(normalized_text)) > 0), -- search only
    normalized_text_alt TEXT,                           -- optional second search copy
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    UNIQUE (source_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_passages_source_seq ON passages(source_id, sequence);
CREATE INDEX IF NOT EXISTS idx_passages_parent ON passages(parent_id);

CREATE TABLE IF NOT EXISTS context_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    passage_id          TEXT NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
    related_passage_id  TEXT NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
    relation_type       TEXT NOT NULL CHECK (relation_type IN ('previous','next','same_chapter','commentary_of')),
    priority            INTEGER NOT NULL DEFAULT 0,
    UNIQUE (passage_id, related_passage_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_context_passage ON context_links(passage_id, relation_type);

CREATE TABLE IF NOT EXISTS corpus_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Production search indexes, one per source group so that BM25 statistics of one corpus are not
-- changed by another (the Quran index is byte-for-byte the Phase 2 index). Only rows of APPROVED,
-- non-synthetic sources are inserted (scripts/build_fts.py); retrievers re-check status.
--   passages_fts : quran (+ synthetic fixtures in test DBs)
--   hadith_fts   : hadith collections
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    normalized_text,
    normalized_text_alt,
    tokenize = 'unicode61 remove_diacritics 0'
);
CREATE VIRTUAL TABLE IF NOT EXISTS hadith_fts USING fts5(
    normalized_text,
    normalized_text_alt,
    tokenize = 'unicode61 remove_diacritics 0'
);

-- Terminology entries (source_type 'dictionary'). Kept OUT of the passage indexes: a term entry is
-- never a candidate source for a quoted text, it is only looked up by exact (normalized) term.
CREATE TABLE IF NOT EXISTS terms (
    id                  TEXT PRIMARY KEY,               -- e.g. 'dictionary:sp:en:tawhid'
    source_id           TEXT NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    term_ar             TEXT NOT NULL CHECK (length(trim(term_ar)) > 0),
    term_normalized     TEXT NOT NULL,
    language            TEXT NOT NULL,
    translation         TEXT NOT NULL CHECK (length(trim(translation)) > 0),
    usage_note          TEXT,
    reference           TEXT NOT NULL,
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    UNIQUE (source_id, term_normalized, language)
);
