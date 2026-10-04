"""Lazy-loading local Tafsir corpus (one JSON file per surah, loaded on first request)."""

from __future__ import annotations

import html
import json
import logging
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("tibyan.tafsir")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")
_NL_RE = re.compile(r"\n{3,}")
_AYAH_KEYS = ("ayah", "ayah_id", "ayah_number", "aya", "verse")
_TEXT_KEYS = ("content", "text", "tafsir", "tafseer")

MIN_SURAH, MAX_SURAH = 1, 114


def _clean(text: str) -> str:
    """Strip markup, unescape entities, and remove characters that could forge prompt tags."""
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace("<", "").replace(">", "")
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _NL_RE.sub("\n\n", text).strip()


def _flatten(node) -> list[str]:
    """Normalise the possible 'content' shapes into a list of raw strings."""
    if node is None:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        for key in _TEXT_KEYS:
            if key in node:
                return _flatten(node[key])
        return []
    if isinstance(node, (list, tuple)):
        out: list[str] = []
        for item in node:
            out.extend(_flatten(item))
        return out
    return []


def _ayah_number(entry: dict) -> int | None:
    for key in _AYAH_KEYS:
        if key in entry:
            try:
                return int(entry[key])
            except (TypeError, ValueError):
                return None
    return None


def _index_surah(data) -> dict[int, str]:
    """Build {ayah_number: tafsir_text} from a parsed surah file."""
    index: dict[int, list[str]] = {}

    def put(ayah: int, node) -> None:
        parts = [c for c in (_clean(s) for s in _flatten(node)) if c]
        if parts:
            index.setdefault(ayah, []).extend(parts)

    if isinstance(data, dict) and isinstance(data.get("ayahs"), (list, dict)):
        data = data["ayahs"]

    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                n = _ayah_number(entry)
                if n is not None:
                    put(n, entry)
    elif isinstance(data, dict):
        for key, value in data.items():
            if str(key).isdigit():
                put(int(key), value)

    return {n: "\n\n".join(parts) for n, parts in index.items()}


@dataclass
class _Surah:
    index: dict[int, str]
    book_name: str | None = None
    author: str | None = None


def default_data_dir() -> Path:
    env = os.environ.get("TAFSIR_DATA_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "json-data"
        if candidate.is_dir():
            return candidate
    return Path.cwd() / "data" / "json-data"


class LocalTafsirCorpus:
    """Reads tafsir from data/json-data/{surah:03d}_*.json.

    Only the requested surah file is parsed; parsed surahs live in a small LRU cache
    (default 8 surahs) so memory stays bounded however many surahs are queried.
    """

    def __init__(self, data_dir: str | Path | None = None, cache_size: int = 8):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.cache_size = max(1, int(cache_size))
        self._cache: OrderedDict[int, _Surah] = OrderedDict()
        self._files: dict[int, Path] | None = None
        self._describe: dict | None = None
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        return bool(self._file_map())

    def _file_map(self) -> dict[int, Path]:
        """Index file names only (no content is read): surah number -> path."""
        if self._files is None:
            files: dict[int, Path] = {}
            if self.data_dir.is_dir():
                for p in sorted(self.data_dir.glob("*.json")):
                    prefix = p.name.split("_", 1)[0]
                    if prefix.isdigit():
                        files.setdefault(int(prefix), p)
            else:
                log.warning("tafsir data directory not found: %s", self.data_dir)
            self._files = files
        return self._files

    def _load_surah(self, surah_id: int) -> _Surah | None:
        with self._lock:
            cached = self._cache.get(surah_id)
            if cached is not None:
                self._cache.move_to_end(surah_id)
                return cached
            path = self._file_map().get(surah_id)
            if path is None:
                log.warning("no tafsir file for surah %s in %s", surah_id, self.data_dir)
                return None
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as exc:
                log.error("failed to load tafsir file %s: %s", path.name, exc)
                return None
            book = data.get("book") if isinstance(data, dict) else None
            book = book if isinstance(book, dict) else {}
            author = book.get("author")
            surah = _Surah(index=_index_surah(data), book_name=book.get("name"),
                           author=author.get("ar_name") if isinstance(author, dict) else None)
            self._cache[surah_id] = surah
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return surah

    @staticmethod
    def _validate(surah_id: int, ayah_id: int) -> tuple[int, int]:
        if isinstance(surah_id, bool) or isinstance(ayah_id, bool):
            raise ValueError("surah_id and ayah_id must be integers")
        try:
            surah, ayah = int(surah_id), int(ayah_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("surah_id and ayah_id must be integers") from exc
        if not MIN_SURAH <= surah <= MAX_SURAH:
            raise ValueError(f"surah_id must be between {MIN_SURAH} and {MAX_SURAH}")
        if ayah < 1:
            raise ValueError("ayah_id must be >= 1")
        return surah, ayah

    def get_tafsir(self, surah_id: int, ayah_id: int) -> str:
        """Return the tafsir text for surah:ayah, or '' when none exists."""
        surah, ayah = self._validate(surah_id, ayah_id)
        loaded = self._load_surah(surah)
        return loaded.index.get(ayah, "") if loaded else ""

    def get_source_name(self, surah_id: int) -> str | None:
        """Title of the tafsir book (e.g. for attribution), read from the surah file."""
        surah, _ = self._validate(surah_id, 1)
        loaded = self._load_surah(surah)
        return loaded.book_name if loaded else None

    def describe(self) -> dict | None:
        """Book metadata and size for the sources page; None when no tafsir files exist. Cached after first call."""
        if getattr(self, "_describe", None) is not None:
            return self._describe or None
        files = self._file_map()
        info: dict = {}
        ayahs = 0
        for path in files.values():
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                ayahs += len(data["ayahs"]) if isinstance(data.get("ayahs"), list) else 0
                if not info and isinstance(data.get("book"), dict):
                    info = {**data["book"], "dump_version": data.get("dump_version"), "dump_source": data.get("source")}
        if info:
            info["ayahs"] = ayahs
        self._describe = info
        return info or None

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def cached_surahs(self) -> list[int]:
        with self._lock:
            return list(self._cache.keys())
