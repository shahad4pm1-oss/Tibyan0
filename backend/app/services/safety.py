"""Scientific-safety service (SCIENTIFIC_POLICY SP-04/05/06/07/08/11/13).

Three jobs, all real code paths:
1. screen_input(): flags prompt-injection markers in user data. Flags are logged as codes only and
   NEVER change routing, gating or the prompt structure; user text always stays inside the escaped
   untrusted-data block (see claim_analyzer.render_user_message).
2. lint_output(): rejects AI text that issues personal rulings, judges people or groups, profiles the
   user's religion, or asserts unsupported certainty/consensus. Feeds the analyzer's single retry.
3. finalize(): applies non-negotiable routing to the final result: level D never gets a model verdict;
   level C is SCOPED: a substantive verdict about what the text and its context say is kept, flagged
   LEVEL_C_SCOPED_TO_TEXT and always carries a referral (ruling language was already rejected by the lint);
   needs_specialist forces referral;
   gate failures abstain; provider failures produce no verdict.
Fixed Arabic templates below are DRAFT until reviewed by a qualified specialist (SCIENTIFIC_POLICY §6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.claim_analysis import SUBSTANTIVE, LLMClaimOutput
from app.services.content_level_router import Level
from app.services.evidence_gate import GateDecision, GateResult
from app.services.normalizer import normalize_for_search

DISCLOSURE = ("هذا التحليل صادر عن أداة مدعومة بالذكاء الاصطناعي، وهو مقيّد بالأدلة المعروضة فقط. "
              "تبيان ليس مفتيًا ولا بديلًا عن المختص.")

TEMPLATES = {
    "SOURCE_NOT_FOUND": "لم نعثر على مرجع كافٍ في المصادر المتاحة.",
    "SOURCE_AMBIGUOUS": "يطابق الاقتباس أكثر من موضع محتمل، ولم يُنسب إلى موضع بعينه، فلا يمكن الحكم على الادعاء.",
    "NEAR_MATCH_UNCONFIRMED": "لا يطابق الاقتباس نصًا في المصادر حرفيًا، فلم يُنسب إلى موضع بعينه، ولا يمكن الحكم على الادعاء.",
    "INSUFFICIENT": "الأدلة المعتمدة المتاحة لا تكفي للوصول إلى نتيجة موثوقة.",
    "SPECIALIST": "هذه المسألة تحتاج إلى مراجعة مختص مؤهل.",
    "PERSONAL_CASE": ("يبدو أن الادعاء أو السؤال يتعلق بحالة شخصية تحتاج إلى فتوى. لا يصدر تبيان أحكامًا في "
                      "الحالات الشخصية؛ يُرجى الرجوع إلى جهة إفتاء معتمدة أو عالم مؤهل."),
    "LEVEL_C": ("تتعلق هذه المسألة بأمر خلافي أو حساس يحتاج إلى تحرير علمي، فلا يقطع تبيان فيها. "
                "النص والسياق المعروضان موثّقان، ويُرجى عرض المسألة على مختص."),
    "ANALYSIS_UNAVAILABLE": ("تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً. المصدر والنص والسياق المعروضة موثّقة من قاعدة "
                             "المصادر، ولم يصدر حكم على الادعاء."),
    "NOT_ENABLED_FOR_SOURCE_TYPE": ("تحليل الادعاء غير مفعّل لهذا النوع من المصادر بعد. النص ومصدره وبيانات "
                                    "الحكم عليه معروضة كما هي في المصدر المعتمد، ولم يصدر حكم على الادعاء."),
    "AI_OUTPUT_REJECTED": ("رُفضت مخرجات التحليل الآلي لأنها لم تجتز التحقق من الاستشهاد أو الإسناد، "
                           "فلا يمكن الوصول إلى نتيجة موثوقة."),
}
REFERRAL = "للمسائل الشرعية التي تحتاج إلى نظر، يُرجى الرجوع إلى عالم مؤهل أو جهة إفتاء معتمدة."

# Output lint (normalized patterns)
_PERSONAL_RULING = ["يجوز لك", "لا يجوز لك", "يحرم عليك", "يجب عليك", "حرام عليك", "حلال لك", "عليك ان",
                    "افتيك", "فتواي", "حكمك", "صلاتك", "صيامك", "زواجك", "طلاقك"]
_PERSON_JUDGMENT = ["كاذب", "كذاب", "يكذب", "تكذب", "سوء نية", "سيئ النية", "سيء النية", "متعمد", "يتعمد",
                    "منافق", "جاهل", "حاقد", "مغرض", "مدلس", "عدو الاسلام", "معاد للاسلام", "صاحب الادعاء مضلل",
                    "الكاتب مضلل"]
_PROFILING = ["انت مسلم", "انت غير مسلم", "ايمانك", "عقيدتك", "دينك", "انك ملحد", "انك كافر"]
_CERTAINTY = ["اجمع العلماء", "بالاجماع", "باجماع", "بلا خلاف", "لا خلاف", "اتفق العلماء", "قطعا", "قطعيا",
              "بلا شك", "يقينا"]
# Standalone rulings / takfir in AI text (never allowed, enforced strictly for level C scoped analysis)
# (bare "هو كافر" is not listed: the model may need to restate what the claim itself says)
_STANDALONE_RULING = ["فهو كافر", "فهم كفار", "يحكم بكفره", "يحكم بكفرهم", "نحكم بكفر",
                      "حكمنا", "نفتي", "الفتوى ان", "فتوانا", "خارج عن الملة", "خارج من الملة", "مرتد عن الاسلام",
                      "الحكم الشرعي ان", "حكمه الشرعي"]
_INJECTION = ["ignore", "system", "instruction", "previous instructions", "تجاهل", "التعليمات", "تعليمات النظام",
              "اعد supported", "return supported", "supported", "use your own knowledge", "invent", "اخترع",
              "معرفتك الخاصة", "<evidence", "evidence id", "=== "]


def _rx(p: str) -> re.Pattern:
    n = normalize_for_search(p).lower()
    article = "" if n.startswith("ال") else "(?:ال)?"
    return re.compile(r"(?:^|\s)(?:[وف])?(?:[بلك])?" + article + re.escape(n) + r"(?=(?:ا|ه|ة|ي|ان|ون|ين)?(?:\s|$))")


_LINT = {
    "PERSONAL_RULING_LANGUAGE": [_rx(p) for p in _PERSONAL_RULING],
    "PERSON_JUDGMENT_LANGUAGE": [_rx(p) for p in _PERSON_JUDGMENT],
    "USER_PROFILING_LANGUAGE": [_rx(p) for p in _PROFILING],
    "UNSUPPORTED_CERTAINTY": [_rx(p) for p in _CERTAINTY],
    "STANDALONE_RULING_LANGUAGE": [_rx(p) for p in _STANDALONE_RULING],
}


def screen_input(quote: str, claim: str) -> list[str]:
    text = (quote + " " + claim).lower()
    return ["PROMPT_INJECTION_MARKERS"] if any(m in text for m in _INJECTION) else []


def lint_output(o: LLMClaimOutput) -> list[str]:
    text = normalize_for_search(" ".join([o.summary, o.reason, o.uncertainty_reason or ""]
                                         + [k.relevance for k in o.key_evidence])).lower()
    return sorted(code for code, rxs in _LINT.items() if any(rx.search(text) for rx in rxs))


@dataclass
class Final:
    status: str  # COMPLETED | ABSTAINED | REFERRED | ANALYSIS_UNAVAILABLE | AI_OUTPUT_REJECTED
    relation: str | None
    summary: str | None
    summary_source: str | None  # "ai" | "system_template" | None
    reason: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    key_evidence: list[dict] = field(default_factory=list)
    needs_specialist: bool = False
    uncertainty_reason: str | None = None
    referral: str | None = None
    safety_overrides: list[str] = field(default_factory=list)
    verdict: str | None = None                                  # claim-centric verdict (minimal schema)
    assertions: list[dict] = field(default_factory=list)        # micro-assertions (minimal schema)


def finalize(level: Level, gate: GateResult, outcome) -> Final:
    """`outcome` is a claim_analyzer.AnalyzerOutcome or None (when the LLM was not called)."""
    if gate.decision is GateDecision.SPECIALIST_REQUIRED:
        return Final("REFERRED", "REQUIRES_SPECIALIST", TEMPLATES["PERSONAL_CASE"], "system_template",
                     needs_specialist=True, uncertainty_reason="PERSONAL_CASE_LEVEL_D", referral=REFERRAL)
    if gate.decision is GateDecision.INSUFFICIENT and gate.reasons == ["CLAIM_ANALYSIS_NOT_ENABLED_FOR_SOURCE_TYPE"]:
        return Final("ANALYSIS_UNAVAILABLE", None, TEMPLATES["NOT_ENABLED_FOR_SOURCE_TYPE"], "system_template",
                     uncertainty_reason="CLAIM_ANALYSIS_NOT_ENABLED_FOR_SOURCE_TYPE")
    if gate.decision is GateDecision.INSUFFICIENT:
        key = next((r for r in gate.reasons if r in TEMPLATES), "INSUFFICIENT")
        return Final("ABSTAINED", "INSUFFICIENT_EVIDENCE", TEMPLATES[key], "system_template",
                     uncertainty_reason=",".join(gate.reasons))
    if outcome is None or outcome.status in ("NOT_CONFIGURED", "PROVIDER_ERROR"):
        reason = outcome.error_category if outcome else "NOT_CALLED"
        detail = getattr(outcome, "error_detail", None)
        if detail:
            reason = f"{reason}: {detail}"
        return Final("ANALYSIS_UNAVAILABLE", None, TEMPLATES["ANALYSIS_UNAVAILABLE"], "system_template",
                     uncertainty_reason=reason)
    if outcome.status == "REJECTED":
        return Final("AI_OUTPUT_REJECTED", "INSUFFICIENT_EVIDENCE", TEMPLATES["AI_OUTPUT_REJECTED"],
                     "system_template", uncertainty_reason="AI_OUTPUT_REJECTED:" + ",".join(outcome.last_issues))

    o: LLMClaimOutput = outcome.output
    ke = [k.model_dump() for k in o.key_evidence]
    extra = {"verdict": o.verdict, "assertions": [a.model_dump() for a in o.assertions]}
    notes = list(o.notes)
    if o.relation == "REQUIRES_SPECIALIST":
        return Final("REFERRED", o.relation, o.summary, "ai", o.reason, o.evidence_ids, ke, True,
                     o.uncertainty_reason, REFERRAL, safety_overrides=notes, **extra)
    status = "ABSTAINED" if o.relation == "INSUFFICIENT_EVIDENCE" else "COMPLETED"
    if level is Level.C:
        # SCOPED: the verdict is about what the text and its context say, never a ruling on the matter itself
        return Final(status, o.relation, o.summary, "ai", o.reason, o.evidence_ids, ke, False,
                     o.uncertainty_reason or ("LEVEL_C_TEXT_SCOPE_ONLY" if o.relation in SUBSTANTIVE else None),
                     REFERRAL, safety_overrides=["LEVEL_C_SCOPED_TO_TEXT", *notes], **extra)
    return Final(status, o.relation, o.summary, "ai", o.reason, o.evidence_ids, ke, False, o.uncertainty_reason,
                 safety_overrides=notes, **extra)
