"""Deterministic content-level routing (Scientific Package p.2, levels A–D).

Input: the user's CLAIM (the quote itself is checked against the corpus elsewhere). Matching is done
on normalize_for_search() output, with optional Arabic proclitics (و/ف then ب/ل/ك, then ال) before a pattern
and common suffixes after it.

Order and precedence: D (personal case / fatwa) > C (disputed / sensitive) > A (purely textual) > B.
When several levels match, the stricter one wins (SCIENTIFIC_POLICY §3, ambiguity rule).

Policy per level (claim-centric analyzer):
  A, B  ANALYZE  full claim-vs-evidence analysis.
  C     SCOPED   disputed / sensitive claims (takfir, rulings, consensus, creed, contested history) are no
                 longer blocked: the model analyses what the verified text and its context say about each
                 micro-assertion of the claim, and is strictly restricted from issuing a standalone ruling or
                 fatwa. Any part that needs a ruling is labelled requires_specialist; the result always
                 carries a referral, and ruling language in the AI text is rejected by the safety lint.
  D     BLOCKED  personal case / fatwa request: never sent to the model.

This is a transparent keyword heuristic, NOT a classifier and NOT calibrated. It is deliberately
conservative: it will route some harmless claims to C or D (false positives) rather than let a
personal fatwa or a disputed matter through. Rule lists are reviewable here and in docs/AI_SAFETY.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from app.services.normalizer import normalize_for_search


class Level(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class Policy(str, Enum):
    ANALYZE = "ANALYZE"
    SCOPED = "SCOPED"      # analyse the text and its context only; no standalone ruling
    BLOCKED = "BLOCKED"    # never sent to the model


POLICY = {Level.A: Policy.ANALYZE, Level.B: Policy.ANALYZE, Level.C: Policy.SCOPED, Level.D: Policy.BLOCKED}


RULES: dict[str, dict[str, list[str]]] = {
    "D": {
        "first_person_ruling": ["يجوز لي", "يحل لي", "هل علي", "يلزمني", "يجب علي", "هل اثم", "اثم علي",
                                "افتوني", "افتني", "فتوى لي", "ماذا افعل", "حكم حالتي"],
        "personal_situation": ["حالتي", "وضعي", "انا في", "في بلدي", "في دولتي", "زوجي", "زوجتي", "طلقني",
                               "طلاقي", "زواجي", "خطيبتي", "خطيبي", "ورثت", "ميراثي", "عقدي", "قرضي", "صلاتي",
                               "صيامي", "صومي", "زكاتي", "حجي", "علاجي", "دوائي", "مرضي"],
    },
    "C": {
        "fiqh_ruling": ["حلال", "حرام", "يحرم", "محرم", "تحريم", "يجوز", "لا يجوز", "جائز", "واجب", "فرض",
                        "مكروه", "مستحب", "بدعة", "حكم"],
        "consensus": ["اجماع", "اجمع", "مجمع عليه", "جميع المسلمين", "كل المسلمين", "جميع العلماء",
                      "كل العلماء", "اتفق العلماء", "باتفاق العلماء", "لا خلاف", "بلا خلاف"],
        "takfir": ["كافر", "كفار", "تكفير", "يكفر", "مرتد", "ردة", "خارج عن الملة", "خارج من الملة"],
        "judging_groups": ["الشيعة", "الرافضة", "الصوفية",
                           "الاشاعرة", "السلفية", "المعتزلة", "الخوارج", "الوهابية", "اهل السنة"],
        "detailed_creed": ["صفات الله", "الاستواء", "خلق القران", "القضاء والقدر", "رؤية الله"],
        "contested_history": ["الفتنة الكبرى", "معاوية", "يزيد", "الصحابة", "ام المؤمنين"],
    },
    "A": {
        "textual": ["النص يقول", "الاية تقول", "الاية تذكر", "تذكر الاية", "ورد في", "جاء في", "نص الاية",
                    "لفظ الاية", "الاية رقم", "من سورة", "في سورة"],
    },
}

LEVEL_GUIDANCE = {
    "A": "Level A (stable original text). Verify the claim strictly against the cited text.",
    "B": "Level B (explanation / general reasoning). Answer only from the supplied evidence and avoid "
         "certainty where interpretation could differ; qualify the conclusion.",
    "C": "Level C (disputed or highly sensitive: takfir, rulings, consensus, creed, contested history). SCOPED "
         "analysis: judge ONLY what the supplied text and its retrieved context say about each part of the claim "
         "(does the text mention it, does the context limit it, is the text being stretched). Never issue a "
         "standalone ruling or fatwa, never declare any person or group a disbeliever, never state that "
         "something is halal, haram or obligatory as your own conclusion, and never resolve the disputed matter "
         "itself. Label any part that needs such a ruling requires_specialist (REQUIRES_SPECIALIST).",
    "D": "Level D (personal case). Not sent to the model.",
}

_CLITICS = r"(?:[وف])?(?:[بلك])?"  # conjunction then preposition, e.g. فب + الاجماع
_PREFIX = r"(?:^|\s)" + _CLITICS + r"(?:ال)?"
_SUFFIX = r"(?:ا|ه|ة|ات|ان|ين|ون|ي|ها|هم)?(?=\s|$)"


def _compile(p: str) -> re.Pattern:
    n = normalize_for_search(p)
    if n.startswith("ال"):
        return re.compile(r"(?:^|\s)" + _CLITICS + re.escape(n) + _SUFFIX)
    return re.compile(_PREFIX + re.escape(n) + _SUFFIX)


_COMPILED = {lvl: {grp: [(p, _compile(p)) for p in pats] for grp, pats in groups.items()}
             for lvl, groups in RULES.items()}


SCOPE_RESTRICTIONS = {
    Policy.SCOPED: ["TEXT_AND_CONTEXT_ONLY", "NO_STANDALONE_RULING", "NO_TAKFIR", "NO_DISPUTE_RESOLUTION",
                    "REFERRAL_ATTACHED"],
}


@dataclass
class Routing:
    level: Level
    matched: list[str] = field(default_factory=list)  # "C.consensus:اجماع" style codes

    @property
    def policy(self) -> Policy:
        return POLICY[self.level]

    @property
    def scope(self) -> list[str]:
        return SCOPE_RESTRICTIONS.get(self.policy, [])


def route(claim: str) -> Routing:
    text = normalize_for_search(claim)
    hits: dict[str, list[str]] = {}
    for lvl, groups in _COMPILED.items():
        for grp, pats in groups.items():
            for raw, rx in pats:
                if rx.search(text):
                    hits.setdefault(lvl, []).append(f"{lvl}.{grp}:{raw}")
    for lvl in ("D", "C", "A"):
        if lvl in hits:
            return Routing(Level(lvl), hits[lvl] + [h for k, v in hits.items() if k != lvl for h in v])
    return Routing(Level.B, [])
