"""Citation verifier: the LLM may cite ONLY backend evidence ids, and may not name any source,
reference, collection, book or scholar that the backend did not supply.

Rule: set(output.evidence_ids) ⊆ set(backend evidence ids). Any violation rejects the output.
"""

from __future__ import annotations

import re

from app.schemas.claim_analysis import SUBSTANTIVE, LLMClaimOutput
from app.services.evidence_builder import Evidence, has_tafsir_layer
from app.services.normalizer import normalize_for_search

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_NUM_REF = re.compile(r"(\d{1,3})\s*[:：/]\s*(\d{1,3})")
_AYAH_NUM = re.compile(r"(?:^|\s)(?:ال)?ايه\s+(?:رقم\s+)?(\d{1,3})|(?:^|\s)(?:ال)?اية\s+(?:رقم\s+)?(\d{1,3})")
_SURAH = re.compile(r"سورة\s+(\S+)")

# Source/authority names the backend never supplies in the current corpus (normalized forms).
EXTERNAL_SOURCE_TERMS = [
    "رواه", "اخرجه", "البخاري", "صحيح مسلم", "رواه مسلم", "الترمذي", "ابو داود", "النسائي", "ابن ماجه",
    "مسند احمد", "الموطا", "قال رسول الله", "قال النبي", "في الحديث", "حديث صحيح", "الحديث الصحيح",
    "ابن كثير", "الطبري", "القرطبي", "السعدي", "البغوي", "النووي", "ابن تيمية", "ابن القيم", "ابن عباس",
    "تفسير", "قال العلماء", "قال المفسرون", "المفسرون", "اهل العلم", "الفقهاء", "المذاهب", "فتوى",
    "الدرر السنية", "islamqa", "dorar", "bukhari", "sahih", "ibn kathir", "tafsir", "hadith",
]
def _term_rx(t: str) -> re.Pattern:
    n = normalize_for_search(t).lower()
    article = "" if n.startswith("ال") else "(?:ال)?"
    return re.compile(r"(?:^|\s)(?:[وف])?(?:[بلك])?" + article + re.escape(n))


_TERMS = [(t, _term_rx(t)) for t in EXTERNAL_SOURCE_TERMS]
_TAFSIR_WORDS = {"تفسير", "tafsir"}


def _free_text(o: LLMClaimOutput) -> str:
    return " ".join([o.summary, o.reason, o.uncertainty_reason or ""] + [k.relevance for k in o.key_evidence])


_DIAC = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u0640\u06d6-\u06ed]")
_ALEF = str.maketrans({"\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627", "\u0671": "\u0627"})


def _light(t: str) -> str:
    """Diacritics removed and alef unified, digits KEPT (normalize_for_search drops digits)."""
    return _DIAC.sub("", t).translate(_ALEF)


def _strip_al(s: str) -> str:
    return s.removeprefix("ال")


def verify(o: LLMClaimOutput, evidence: list[Evidence]) -> list[str]:
    issues: list[str] = []
    backend = {e.id: e for e in evidence}
    cited = set(o.evidence_ids) | {k.evidence_id for k in o.key_evidence}
    if cited - set(backend):
        issues.append("UNKNOWN_EVIDENCE_ID")
    if o.relation in SUBSTANTIVE:
        roles = {backend[i].role for i in o.evidence_ids if i in backend}
        if not roles - {"metadata"}:
            issues.append("NO_SUBSTANTIVE_EVIDENCE_CITED")

    raw = _free_text(o).translate(_AR_DIGITS)
    refs = {e.reference for e in evidence if e.reference}
    ayahs = {str(e.metadata.get("ayah_number")) for e in evidence if e.metadata and e.metadata.get("ayah_number")}
    surahs = {_strip_al(normalize_for_search(str(e.metadata["surah_name"])))
              for e in evidence if e.metadata and e.metadata.get("surah_name")}
    for a, b in _NUM_REF.findall(raw):
        if f"{int(a)}:{int(b)}" not in refs:
            issues.append("EXTERNAL_REFERENCE")
            break
    for m in _AYAH_NUM.finditer(_light(raw)):
        n = m.group(1) or m.group(2)
        if n and n not in ayahs:
            issues.append("EXTERNAL_REFERENCE")
            break
    norm = normalize_for_search(raw).lower()
    for m in _SURAH.finditer(norm):
        if _strip_al(m.group(1)) not in surahs:
            issues.append("EXTERNAL_REFERENCE")
            break
    # When the backend supplied a tafsir layer, naming "tafsir" is grounded, and so is any name that appears
    # inside the supplied commentary text itself. Names that are NOT in the evidence stay rejected.
    tafsir_on = has_tafsir_layer(evidence)
    commentary_norm = normalize_for_search(" ".join(
        [e.text for e in evidence if e.role == "source_commentary"]
        + [str((e.metadata or {}).get("tafsir_book") or "") for e in evidence if e.role == "source_commentary"])).lower()
    for t, rx in _TERMS:
        if rx.search(norm):
            if tafsir_on and (t in _TAFSIR_WORDS or rx.search(commentary_norm)):
                continue
            issues.append("UNSUPPORTED_SOURCE_MENTION")
            break
    return sorted(set(issues))
