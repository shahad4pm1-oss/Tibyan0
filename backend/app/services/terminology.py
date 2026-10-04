"""Approved terminology lookup (source_type 'dictionary').

Finds approved term entries whose Arabic term occurs as a whole word in the quote or claim (after
search normalization), allowing only the common attached proclitics (و ف ب ك and ل + ال -> لل).
Deterministic; no model. Terms are shown as terminology guidance, never as the source of a quote.
"""

from __future__ import annotations

import sqlite3

from app.services.normalizer import tokens

_PROCLITICS = ("", "و", "ف", "ب", "ك", "وب", "فب", "وك", "فك")


def _forms(term_norm: str) -> set[str]:
    forms = {p + term_norm for p in _PROCLITICS}
    if term_norm.startswith("ال"):
        bare = term_norm[2:]
        forms |= {"لل" + bare, "ولل" + bare, "فلل" + bare}
    return forms


class Terminology:
    def __init__(self, conn: sqlite3.Connection):
        rows = conn.execute(
            "SELECT t.id, t.term_ar, t.term_normalized, t.language, t.translation, t.usage_note, t.reference, "
            "t.source_id FROM terms t JOIN sources s ON s.id = t.source_id "
            "WHERE s.verification_status = 'APPROVED' AND s.source_type = 'dictionary' ORDER BY t.id").fetchall()
        self.entries = [dict(zip(("id", "term_ar", "term_normalized", "language", "translation", "usage_note",
                                  "reference", "source_id"), r)) for r in rows]
        self._index: dict[str, list[dict]] = {}
        for e in self.entries:
            for f in _forms(e["term_normalized"]):
                self._index.setdefault(f, []).append(e)

    def __len__(self) -> int:
        return len(self.entries)

    def lookup(self, *texts: str) -> list[dict]:
        seen: dict[str, dict] = {}
        for text in texts:
            for tok in tokens(text):
                for e in self._index.get(tok, []):
                    seen.setdefault(e["id"], e)
        return [{k: v for k, v in e.items() if k != "term_normalized"} for e in seen.values()]
