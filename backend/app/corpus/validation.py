"""Corpus validation. A corrupted production corpus must FAIL.

Each check has an ID that docs/DATA_PIPELINE.md and tests refer to.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.services.normalizer import normalize_for_search, normalize_hadith_search

VALID_STATUS = {"APPROVED", "PENDING_REVIEW", "REJECTED"}
KNOWN_TYPES = {"quran", "quran_translation", "hadith", "tafsir", "commentary", "aqeedah", "fiqh", "seerah",
               "history", "dawah", "shubuhat", "dictionary", "synthetic_fixture"}
# Grading authorities a production hadith record may cite. Never a model.
HADITH_GRADING_AUTHORITIES = {"SCIENTIFIC_PACKAGE_SAHIHAYN_RULE"}
_MARKUP = ("PageV", "~~", "###", "#META#")


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def fail(self, check: str, msg: str, limit: int = 20) -> None:
        if sum(e.startswith(check) for e in self.errors) < limit:
            self.errors.append(f"{check}: {msg}")


def original_text_digest(conn: sqlite3.Connection, source_type: str | None = None) -> str:
    """Digest of (id, original_text) for all passages, or for one source type only."""
    h = hashlib.sha256()
    q = "SELECT p.id, p.original_text FROM passages p"
    args: tuple = ()
    if source_type is not None:
        q += " JOIN sources s ON s.id = p.source_id WHERE s.source_type = ?"
        args = (source_type,)
    for (pid, txt) in conn.execute(q + " ORDER BY p.rowid_int", args):
        h.update(pid.encode())
        h.update(b"\x00")
        h.update(txt.encode())
        h.update(b"\x01")
    return h.hexdigest()


def _info(conn: sqlite3.Connection) -> dict[str, str]:
    return {k: v for k, v in conn.execute("SELECT key, value FROM corpus_info")}


def validate(conn: sqlite3.Connection, production: bool, structure_expected: Path | None = None) -> ValidationReport:
    rep = ValidationReport()
    info = _info(conn)
    sources = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM sources")}

    # V01 source status / production purity
    rep.checks_run += ["V01", "V14"]
    for sid, s in sources.items():
        if s["verification_status"] not in VALID_STATUS:
            rep.fail("V01", f"source {sid} has invalid status {s['verification_status']}")
        if production and s["source_type"] == "synthetic_fixture":
            rep.fail("V01", f"synthetic source {sid} present in production corpus")
        if production and s["verification_status"] != "APPROVED":
            rep.fail("V01", f"non-APPROVED source {sid} ({s['verification_status']}) present in production corpus")
        # V14 source type known; provenance and license recorded
        if s["source_type"] not in KNOWN_TYPES:
            rep.fail("V14", f"source {sid} has unknown source_type {s['source_type']}")
        if production:
            meta = json.loads(s["metadata_json"] or "{}")
            if not (s["source_url"] or meta.get("provenance")):
                rep.fail("V14", f"source {sid} has no source_url/provenance")
            if not (s["license_note"] or "").strip():
                rep.fail("V14", f"source {sid} has no license note")
    if production and info.get("corpus_kind") != "production":
        rep.fail("V01", f"corpus_kind is {info.get('corpus_kind')!r}, expected 'production'")

    # V02 foreign keys
    rep.checks_run.append("V02")
    for row in conn.execute("PRAGMA foreign_key_check"):
        rep.fail("V02", f"foreign key violation {tuple(row)}")

    passages = [dict(r) for r in conn.execute("SELECT * FROM passages ORDER BY source_id, sequence")]
    rep.stats["passages"] = len(passages)

    # V03 duplicate ids / sequences
    rep.checks_run.append("V03")
    ids = [p["id"] for p in passages]
    if len(ids) != len(set(ids)):
        rep.fail("V03", "duplicate passage ids")
    seqs = [(p["source_id"], p["sequence"]) for p in passages]
    if len(seqs) != len(set(seqs)):
        rep.fail("V03", "duplicate (source_id, sequence)")

    for p in passages:
        meta = json.loads(p["metadata_json"])
        st = sources.get(p["source_id"], {}).get("source_type")
        # V04 reference
        if not (p["reference"] or "").strip():
            rep.fail("V04", f"{p['id']} empty reference")
        # V05 canonical text
        if not (p["original_text"] or "").strip():
            rep.fail("V05", f"{p['id']} empty original_text")
        # V06 normalized search copy exists and is current
        if not (p["normalized_text"] or "").strip():
            rep.fail("V06", f"{p['id']} empty normalized_text")
        if st == "quran":
            if p["normalized_text"] != normalize_for_search(meta.get("publisher_aya_text_emlaey", "")):
                rep.fail("V06", f"{p['id']} normalized_text stale or altered")
            if p["normalized_text_alt"] != normalize_for_search(p["original_text"]):
                rep.fail("V06", f"{p['id']} normalized_text_alt stale or altered")
        elif st == "hadith":
            if p["normalized_text"] != normalize_hadith_search(p["original_text"]):
                rep.fail("V06", f"{p['id']} normalized_text stale or altered (hnorm-v1)")
            if p["normalized_text_alt"] not in (None, normalize_for_search(p["original_text"])):
                rep.fail("V06", f"{p['id']} normalized_text_alt stale or altered")
        elif p["normalized_text"] != normalize_for_search(p["original_text"]):
            rep.fail("V06", f"{p['id']} normalized_text stale or altered")
        # V07 structural metadata
        need = {"quran": ("surah_number", "ayah_number", "surah_name"),
                "hadith": ("grading", "grading_source", "collection")}.get(st, ())
        if st == "hadith" and meta.get("hadith_number") in (None, "") and not (
                meta.get("locator") and meta.get("book") and meta.get("chapter")):
            rep.fail("V07", f"{p['id']} has neither a hadith number nor a book/chapter locator")
        for k in need:
            if meta.get(k) in (None, ""):
                rep.fail("V07", f"{p['id']} missing metadata {k}")
        # V12 Quran: exact reconstruction of the publisher string
        if st == "quran":
            rebuilt = p["original_text"] + meta.get("trailing_separator", "") + meta.get("ayah_mark_glyph", "")
            if rebuilt != meta.get("publisher_aya_text"):
                rep.fail("V12", f"{p['id']} original_text does not reconstruct publisher aya_text")
            if p["id"] != f"quran:{meta.get('surah_number')}:{meta.get('ayah_number')}":
                rep.fail("V07", f"{p['id']} id does not match surah/ayah metadata")
        # V15 hadith: id, collection, number, grading with an allowed (non-model) authority, clean text
        if st == "hadith":
            loc = meta.get("locator") or {}
            expected = (f"{p['source_id']}:{meta.get('hadith_number')}" if meta.get("hadith_number") else
                        f"{p['source_id']}:u:{loc.get('book_number')}:{loc.get('chapter_number')}:"
                        f"{loc.get('unnumbered_ordinal_in_chapter')}")
            if p["id"] != expected:
                rep.fail("V15", f"{p['id']} id does not match source/hadith_number or locator")
            if production:
                if meta.get("grading_authority") not in HADITH_GRADING_AUTHORITIES:
                    rep.fail("V15", f"{p['id']} grading authority {meta.get('grading_authority')!r} not allowed")
                if meta.get("grading_generated_by_model") is not False:
                    rep.fail("V15", f"{p['id']} grading_generated_by_model must be false")
                if any(m in p["original_text"] for m in _MARKUP):
                    rep.fail("V15", f"{p['id']} original_text contains source-file markup")
    rep.checks_run += ["V04", "V05", "V06", "V07", "V12", "V15"]

    # V08 order (Quran): consecutive ayat from 1 within each surah, surahs ascending
    rep.checks_run.append("V08")
    quran = [p for p in passages if sources.get(p["source_id"], {}).get("source_type") == "quran"]
    prev = (0, 0)
    for p in quran:
        m = json.loads(p["metadata_json"])
        cur = (m["surah_number"], m["ayah_number"])
        ok = (cur[0] == prev[0] and cur[1] == prev[1] + 1) or (cur[0] == prev[0] + 1 and cur[1] == 1)
        if not ok:
            rep.fail("V08", f"order break at {p['id']} after {prev}")
        prev = cur

    # V11 structural expectations from an independent source
    if quran and structure_expected is not None:
        rep.checks_run.append("V11")
        exp = json.loads(Path(structure_expected).read_text(encoding="utf-8"))
        counts: dict[int, int] = {}
        for p in quran:
            s = json.loads(p["metadata_json"])["surah_number"]
            counts[s] = counts.get(s, 0) + 1
        if len(quran) != exp["ayah_count_total"]:
            rep.fail("V11", f"ayah total {len(quran)} != expected {exp['ayah_count_total']}")
        if len(counts) != exp["surah_count"]:
            rep.fail("V11", f"surah count {len(counts)} != expected {exp['surah_count']}")
        for s, n in exp["ayah_count_by_surah"].items():
            if counts.get(int(s)) != n:
                rep.fail("V11", f"surah {s}: {counts.get(int(s))} ayat != expected {n}")

    # V09 context links resolve and are coherent
    rep.checks_run.append("V09")
    pmap = {p["id"]: p for p in passages}
    for r in conn.execute("SELECT passage_id, related_passage_id, relation_type FROM context_links"):
        a, b, rel = r
        if a not in pmap or b not in pmap:
            rep.fail("V09", f"dangling link {a}->{b}")
            continue
        pa, pb = pmap[a], pmap[b]
        if rel in ("previous", "next"):
            if pa["source_id"] != pb["source_id"] or pa["parent_id"] != pb["parent_id"]:
                rep.fail("V09", f"{rel} link crosses unit boundary {a}->{b}")
            step = 1 if rel == "next" else -1
            if pb["sequence"] - pa["sequence"] != step:
                rep.fail("V09", f"{rel} link not adjacent {a}->{b}")

    # V10 search index contains only eligible passages
    rep.checks_run.append("V10")
    eligible = {
        r[0] for r in conn.execute(
            """SELECT p.rowid_int FROM passages p JOIN sources s ON s.id = p.source_id
               WHERE s.verification_status = 'APPROVED'
                 AND (s.source_type != 'synthetic_fixture' OR ? = 0)""",
            (1 if production else 0,),
        )
    }
    from app.corpus.fts import INDEX_FOR_TYPE, INDEXES
    indexed: set[int] = set()
    for table in INDEXES:
        rows = {r[0] for r in conn.execute(f"SELECT rowid FROM {table}")}
        allowed = {r[0] for r in conn.execute(
            f"""SELECT p.rowid_int FROM passages p JOIN sources s ON s.id = p.source_id
                WHERE s.source_type IN ({",".join("?" * len([t for t, ix in INDEX_FOR_TYPE.items() if ix == table]))})""",
            [t for t, ix in INDEX_FOR_TYPE.items() if ix == table])}
        if rows - allowed:
            rep.fail("V10", f"{len(rows - allowed)} passages in {table} belong to another source group")
        indexed |= rows
    indexable = {x[0] for x in conn.execute(
        f"""SELECT p.rowid_int FROM passages p JOIN sources s ON s.id = p.source_id
            WHERE s.source_type IN ({",".join("?" * len(INDEX_FOR_TYPE))})""", list(INDEX_FOR_TYPE))}
    eligible &= indexable
    if indexed - eligible:
        rep.fail("V10", f"{len(indexed - eligible)} ineligible passages in search index (PENDING/REJECTED/synthetic)")
    if eligible - indexed:
        rep.fail("V10", f"{len(eligible - indexed)} eligible passages missing from search index")
    rep.stats["indexed"] = len(indexed)

    # V16 terminology entries: approved dictionary source, translation and reference present
    rep.checks_run.append("V16")
    n_terms = 0
    for t in conn.execute("SELECT t.*, s.source_type, s.verification_status FROM terms t "
                          "LEFT JOIN sources s ON s.id = t.source_id"):
        n_terms += 1
        if t["source_type"] != "dictionary":
            rep.fail("V16", f"term {t['id']} source is not a dictionary source")
        if production and t["verification_status"] != "APPROVED":
            rep.fail("V16", f"term {t['id']} source not APPROVED")
        if not (t["translation"] or "").strip() or not (t["reference"] or "").strip():
            rep.fail("V16", f"term {t['id']} missing translation/reference")
        if t["term_normalized"] != normalize_for_search(t["term_ar"]):
            rep.fail("V16", f"term {t['id']} normalized term stale")
    rep.stats["terms"] = n_terms
    rep.stats["by_type"] = {r[0]: r[1] for r in conn.execute(
        "SELECT s.source_type, count(*) FROM passages p JOIN sources s ON s.id = p.source_id GROUP BY 1")}

    # V13 original text integrity digest recorded at build time
    rep.checks_run.append("V13")
    recorded = info.get("original_text_sha256")
    if recorded is None:
        rep.fail("V13", "no original_text_sha256 recorded")
    elif recorded != original_text_digest(conn):
        rep.fail("V13", "original_text changed since build (digest mismatch)")
    q_rec = info.get("quran_original_text_sha256")
    if q_rec is not None and q_rec != original_text_digest(conn, "quran"):
        rep.fail("V13", "Quran original_text changed since build (digest mismatch)")

    return rep
