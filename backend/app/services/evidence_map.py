"""Evidence & context map: a projection of data the pipeline already produced. No retrieval, no LLM, no new text.

Built only for a RESOLVED source. AMBIGUOUS and NOT_FOUND results get no map (nothing is attributed to one
source), so the map can never suggest an attribution the pipeline did not make.

What it contains (all traceable to source_id / passage_id / evidence id / reference):
  - source        the resolved source
  - nodes         the canonical passages shown, in reading order: preceding context, the matched passage(s),
                  following context. Each node is split into display segments of the stored text, labelled
                    quoted       words present in the user's quote and matching the source (deterministic diff)
                    near_context words of the matched passage that are not in the quote (omitted, a textual fact)
                    context      neighbouring passages (additional context)
                  Hadith: one node, the hadith itself; adjacent records are never presented as context.
  - evidence      E1..En connected to the node they are (the metadata item connects to the source)
  - result        the claim-analysis outcome as already decided by the pipeline, and the context relevance:
                    UNDETERMINED  no analysis (no model, analysis not enabled, abstained) - nothing is inferred
                    LIMITED       the verified AI analysis cited only the matched text
                    RELEVANT      the verified AI analysis cited context evidence (the cited ids are listed)
                    NEEDS_REVIEW  the matter was routed to a specialist or certainty was restricted
                  Omitting surrounding text is reported as a fact; whether it matters is never inferred here.
"""

from __future__ import annotations

VERSION = "map-v1"

_QUOTED = {"MATCHED", "NORMALIZATION_ONLY", "SUBSTITUTED"}


def _segments(tokens: list[tuple[str, str]]) -> list[dict]:
    out: list[dict] = []
    for text, kind in tokens:
        if out and out[-1]["kind"] == kind:
            out[-1]["text"] += " " + text
        else:
            out.append({"text": text, "kind": kind})
    return out


def _context_relevance(claim: dict, items: list) -> dict:
    cited = list(dict.fromkeys(list(claim.get("evidence_ids") or []) +
                               [k["evidence_id"] for k in claim.get("key_evidence") or []]))
    ctx_ids = {e.id for e in items if e.role in ("preceding_context", "following_context")}
    if claim.get("status") == "REFERRED" or claim.get("needs_specialist") or \
            "LEVEL_C_CERTAINTY_RESTRICTED" in (claim.get("safety_overrides") or []):
        return {"value": "NEEDS_REVIEW", "basis": "SPECIALIST_OR_RESTRICTED", "cited_evidence_ids": cited}
    if claim.get("status") == "COMPLETED" and claim.get("summary_source") == "ai":
        cited_ctx = [i for i in cited if i in ctx_ids]
        if cited_ctx:
            return {"value": "RELEVANT", "basis": "AI_CITED_CONTEXT", "cited_evidence_ids": cited_ctx}
        return {"value": "LIMITED", "basis": "AI_CITED_MATCHED_ONLY", "cited_evidence_ids": cited}
    basis = "NOT_ENABLED_FOR_SOURCE" if claim.get("uncertainty_reason") == "CLAIM_ANALYSIS_NOT_ENABLED_FOR_SOURCE_TYPE" \
        else "NO_ANALYSIS"
    return {"value": "UNDETERMINED", "basis": basis, "cited_evidence_ids": []}


def project(source: dict | None, context, items: list, comparison: dict | None, claim_text: str,
            claim: dict) -> dict | None:
    """source/context/items/comparison/claim are the pipeline's own outputs for this request."""
    if source is None or not context.matched:
        return None
    hadith = source.get("source_type") == "hadith"

    # canonical display tokens of the matched passage(s) with their quoted/omitted status from the comparison
    status_by_pos: dict[tuple[str, int], str] = {}
    if comparison and comparison.get("definitive"):
        counters: dict[str, int] = {}
        for t in comparison["canonical_tokens"]:
            pid = t["passage_id"]
            k = counters.get(pid, 0)
            counters[pid] = k + 1
            status_by_pos[(pid, k)] = t["status"]

    nodes: list[dict] = []

    def add_node(kind: str, unit, seg_tokens: list[tuple[str, str]]) -> str:
        nid = f"{kind}:{unit.passage_id}"
        nodes.append({"id": nid, "kind": kind, "passage_id": unit.passage_id, "reference": unit.reference,
                      "segments": _segments(seg_tokens), "evidence_ids": []})
        return nid

    if not hadith:
        for u in context.before:
            add_node("preceding_context", u, [(w, "context") for w in u.text.split()])
    quoted_words = omitted_words = 0
    for u in context.matched:
        toks = []
        for k, w in enumerate(u.text.split()):
            st = status_by_pos.get((u.passage_id, k))
            if st is None and not status_by_pos:
                kind = "quoted"                    # no comparison available: the whole matched unit
            elif st in _QUOTED:
                kind = "quoted"
            elif st == "IGNORED":
                kind = toks[-1][1] if toks else "quoted"
            else:
                kind = "near_context"
            toks.append((w, kind))
            quoted_words += kind == "quoted"
            omitted_words += kind == "near_context"
        add_node("matched", u, toks)
    if not hadith:
        for u in context.after:
            add_node("following_context", u, [(w, "context") for w in u.text.split()])

    by_passage = {n["passage_id"]: n for n in nodes}
    evidence = []
    for e in items:
        node = by_passage.get(e.passage_id) if e.passage_id else None
        target = node["id"] if node else "source"
        if node:
            node["evidence_ids"].append(e.id)
        evidence.append({"id": e.id, "role": e.role, "passage_id": e.passage_id, "reference": e.reference,
                         "node_id": target})

    return {
        "version": VERSION,
        "source": {"source_id": source["id"], "title": source["title"], "source_type": source.get("source_type"),
                   "reference": ", ".join(u.reference for u in context.matched)},
        "nodes": nodes,
        "evidence": evidence,
        "claim": {"text": claim_text},
        "facts": {"quoted_words": quoted_words, "omitted_words_in_matched": omitted_words,
                  "preceding_units": len(context.before), "following_units": len(context.after),
                  "context_kind": "hadith_only" if hadith else "neighbouring_ayat"},
        "result": {"claim_status": claim.get("status"), "relation": claim.get("relation"),
                   "summary_source": claim.get("summary_source"),
                   "context_relevance": _context_relevance(claim, items)},
    }
