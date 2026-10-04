"""Evidence objects with backend-generated IDs (E1, E2, ...).

Phase 3 will allow the LLM to cite ONLY these IDs. Text is always the canonical
original_text read from the corpus, never normalized or generated text.

Tafsir layer: when a tafsir source is supplied (LocalTafsirCorpus, TabariTafsirSource, or a ChainedTafsir of
both: al-Tabari first, local Tafsir Mujahid as fallback), each matched Quran ayah that has a tafsir entry gets
one extra `source_commentary` evidence item whose text keeps the divine text and the commentary strictly
separated (competition requirement). The matched_source item itself stays the untouched canonical ayah.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from app.corpus.tafsir import LocalTafsirCorpus
from app.services.context_expander import ContextWindow
from app.services.types import Passage

log = logging.getLogger("tibyan.evidence")

QURAN_LABEL = "[النص القرآني]"
TAFSIR_LABEL = "[تفسير الآية]"
TAFSIR_MAX_CHARS = 4000  # bounds prompt size; a truncated tafsir is flagged in metadata and marked in the text
TRUNCATION_MARK = " […]"

TAFSIR_SEPARATION_DIRECTIVE = (
    "TAFSIR SEPARATION DIRECTIVE (mandatory; applies whenever the evidence contains the two labelled layers)\n"
    f"Some evidence items contain two distinct layers: the divine text, labelled {QURAN_LABEL}, and human "
    f"commentary, labelled {TAFSIR_LABEL}.\n"
    f"a. The text under {QURAN_LABEL} is the Quran. The text under {TAFSIR_LABEL} is a scholar's interpretation. "
    "It is NOT the Quran and must never be presented as the Quran or as a ruling stated by the Quran.\n"
    "b. Never merge, blend or paraphrase the two layers into one statement. For every point, say which layer "
    "it comes from.\n"
    f"c. Attribute meanings, explanations and opinions found under {TAFSIR_LABEL} to the tafsir "
    "(\"the tafsir states\"), never to the verse itself.\n"
    "d. Never place tafsir wording inside a quotation of the verse, and never attribute verse wording to the "
    "tafsir unless it appears word-for-word inside that layer.\n"
    f"e. If a point is supported only by {TAFSIR_LABEL}, say so explicitly. If the {QURAN_LABEL} layer alone "
    "does not establish the claim, do not use the tafsir to upgrade the claim beyond what the tafsir states.\n"
    "f. Name no scholar or book other than what the evidence itself supplies, and cite the evidence id of the "
    "layer you rely on."
)


def format_evidence_text(ayah_text: str, tafsir_text: str) -> str:
    """Competition format: divine text and commentary separated, in exactly this layout."""
    return f"{QURAN_LABEL}: {ayah_text} \n\n {TAFSIR_LABEL}: {tafsir_text}"


def with_tafsir_directive(system_prompt: str) -> str:
    """Append the strict separation directive to a system prompt (idempotent)."""
    if TAFSIR_SEPARATION_DIRECTIVE in system_prompt:
        return system_prompt
    return f"{system_prompt.rstrip()}\n\n{TAFSIR_SEPARATION_DIRECTIVE}\n"


def has_tafsir_layer(evidence: list[Evidence]) -> bool:
    return any(e.role == "source_commentary" and (e.metadata or {}).get("layers") for e in evidence)


@dataclass
class Evidence:
    id: str
    passage_id: str | None
    source_id: str
    reference: str | None
    text: str
    role: str  # matched_source | preceding_context | following_context | source_commentary | metadata
    source_title: str | None = None
    edition: str | None = None
    metadata: dict | None = None
    source_type: str | None = None          # quran | hadith | ... (never mixed: one source per result)
    verification_status: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _public_meta(p: Passage) -> dict:
    keep = ("surah_number", "ayah_number", "surah_name", "juz", "page",
            "collection", "collection_ar", "hadith_number", "numbers_covered", "locator", "book", "book_number", "chapter",
            "chapter_number", "grading", "grading_ar", "grading_source", "grading_authority",
            "grading_generated_by_model")
    return {k: p.metadata[k] for k in keep if k in p.metadata}


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    cut = text[:limit].rsplit(None, 1)[0] if " " in text[:limit] else text[:limit]
    return cut.rstrip() + TRUNCATION_MARK, True


class EvidenceBuilder:
    def __init__(self, tafsir: LocalTafsirCorpus | None = None, tafsir_max_chars: int = TAFSIR_MAX_CHARS):
        self.tafsir = tafsir
        self.tafsir_max_chars = tafsir_max_chars

    def _tafsir_for(self, p: Passage) -> tuple[str, str | None]:
        """(tafsir text, tafsir book title) for a Quran passage; ('', None) when there is none."""
        if self.tafsir is None:
            return "", None
        surah, ayah = p.metadata.get("surah_number"), p.metadata.get("ayah_number")
        if surah is None or ayah is None:
            return "", None
        try:
            text = self.tafsir.get_tafsir(int(surah), int(ayah))
            if not text:
                return "", None
            try:  # a chained source reports the book that actually answered for this ayah
                return text, self.tafsir.get_source_name(int(surah), int(ayah))
            except TypeError:
                return text, self.tafsir.get_source_name(int(surah))
        except (ValueError, OSError) as exc:
            log.error("tafsir lookup failed for %s:%s: %s", surah, ayah, exc)
            return "", None

    def build(self, ctx: ContextWindow, source: dict) -> list[Evidence]:
        items: list[Evidence] = []

        def add(p: Passage, role: str) -> None:
            items.append(Evidence(id=f"E{len(items) + 1}", passage_id=p.id, source_id=p.source_id,
                                  reference=p.reference, text=p.original_text, role=role,
                                  source_title=source["title"], edition=source["edition"],
                                  metadata=_public_meta(p), source_type=source["source_type"],
                                  verification_status=source["verification_status"]))

        for p in ctx.matched:
            add(p, "matched_source")
        for p in ctx.before:
            add(p, "preceding_context")
        for p in ctx.after:
            add(p, "following_context")
        if source.get("source_type") == "quran" and self.tafsir is not None:
            for p in ctx.matched:
                raw, book = self._tafsir_for(p)
                if not raw:
                    continue
                tafsir_text, truncated = _truncate(raw, self.tafsir_max_chars)
                items.append(Evidence(
                    id=f"E{len(items) + 1}", passage_id=None, source_id=p.source_id, reference=p.reference,
                    text=format_evidence_text(p.original_text, tafsir_text), role="source_commentary",
                    source_title=book or source["title"], edition=source["edition"],
                    metadata={**_public_meta(p), "layers": [QURAN_LABEL, TAFSIR_LABEL],
                              "commentary_of": p.id, "tafsir_book": book, "tafsir_truncated": truncated},
                    source_type=source["source_type"], verification_status=source["verification_status"]))

        for s in ctx.supporting_material:  # none in Phase 2
            items.append(Evidence(id=f"E{len(items) + 1}", passage_id=s.get("passage_id"),
                                  source_id=s["source_id"], reference=s.get("reference"), text=s["text"],
                                  role="source_commentary", source_title=s.get("source_title")))
        items.append(Evidence(
            id=f"E{len(items) + 1}", passage_id=None, source_id=source["id"], reference=None,
            text=f"{source['title']} — {source['edition']}", role="metadata",
            source_title=source["title"], edition=source["edition"],
            metadata={"publisher": source.get("publisher"), "source_url": source.get("source_url"),
                      "verification_status": source["verification_status"]},
            source_type=source["source_type"], verification_status=source["verification_status"],
        ))
        return items
