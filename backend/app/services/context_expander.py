"""Source-aware context retrieval.

Quran: the matched ayah (or ayat), plus up to N preceding and N following ayat within the
same surah (N = CONTEXT_WINDOW, default 2). This is a *retrieved context window*, not the
complete Islamic context of the passage.

Hadith: the full hadith text with its source/reference/book/chapter metadata only.
Adjacent hadith are NOT treated as interpretive context.

supporting_material is reserved for approved commentary (none ingested yet).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.repositories.corpus import CorpusRepository
from app.services.types import Passage


@dataclass
class ContextWindow:
    before: list[Passage] = field(default_factory=list)
    matched: list[Passage] = field(default_factory=list)
    after: list[Passage] = field(default_factory=list)
    supporting_material: list[dict] = field(default_factory=list)
    kind: str = "retrieved_context_window"


class ContextExpander:
    def __init__(self, repo: CorpusRepository, window: int = 2):
        self.repo = repo
        self.window = window

    @staticmethod
    def policy(source: dict) -> str:
        """sequential_window for Quran; single_unit for hadith and anything else unless declared."""
        meta = json.loads(source.get("metadata_json") or "{}")
        if meta.get("context_policy") in ("sequential_window", "single_unit"):
            return meta["context_policy"]
        return "sequential_window" if source["source_type"] == "quran" else "single_unit"

    def expand(self, matched: list[Passage], source: dict) -> ContextWindow:
        ctx = ContextWindow(matched=list(matched))
        if self.policy(source) != "sequential_window" or not matched:
            return ctx
        cur = matched[0]
        for _ in range(self.window):
            cur = self.repo.neighbor(cur.id, "previous")
            if cur is None:
                break
            ctx.before.insert(0, cur)
        cur = matched[-1]
        for _ in range(self.window):
            cur = self.repo.neighbor(cur.id, "next")
            if cur is None:
                break
            ctx.after.append(cur)
        return ctx
