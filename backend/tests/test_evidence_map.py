"""Evidence & context map (app/services/evidence_map.py): a projection of the response's own data.

Checks: every evidence id exists, nothing is invented, source links are correct, Quran neighbours map to the right
side, hadith never presents adjacent records as context, AMBIGUOUS / NOT_FOUND get no map, and context relevance
comes only from a verified analysis (never inferred without a model).
"""

import json

import pytest

from tests.conftest import ask, good_output, make_pipeline

pytestmark = pytest.mark.real_corpus
LSA = {"embedding_provider": "local_lsa", "embedding_model": "char-ngram-lsa-v1"}
CLAIM = "الآية تأمر بالقتال مطلقا"


@pytest.fixture(scope="module")
def pipe(real_db):
    return make_pipeline(real_db, provider=None, **LSA)


def quote_2_191(repo, n=4):
    return " ".join(repo.get("quran:2:191").metadata["publisher_aya_text_emlaey"].split()[:n])


def assert_traceable(r, repo):
    m = r.evidence_map
    ids = [e.id for e in r.evidence.items]
    assert [e.id for e in m.evidence] == ids                         # all, and only, the response's evidence
    node_ids = {n.id for n in m.nodes} | {"source"}
    for e, src in zip(m.evidence, r.evidence.items, strict=True):
        assert e.passage_id == src.passage_id and e.role == src.role and e.node_id in node_ids
        if e.node_id != "source":
            node = next(n for n in m.nodes if n.id == e.node_id)
            assert node.passage_id == e.passage_id and e.id in node.evidence_ids
    for n in m.nodes:                                                # stored text, unchanged, in order
        assert " ".join(s.text for s in n.segments).split() == repo.get(n.passage_id).original_text.split()
    assert m.source["source_id"] == r.source.source_id


def test_quran_map_neighbours_and_traceability(pipe, real_repo):
    r = ask(pipe, quote_2_191(real_repo), CLAIM)
    m = r.evidence_map
    assert m is not None
    kinds = [(n.kind, n.passage_id) for n in m.nodes]
    assert kinds == ([("preceding_context", u.passage_id) for u in r.context.before]
                     + [("matched", u.passage_id) for u in r.context.matched]
                     + [("following_context", u.passage_id) for u in r.context.after])
    matched = next(n for n in m.nodes if n.kind == "matched")
    assert [s.kind for s in matched.segments] == ["quoted", "near_context"]
    assert len(matched.segments[0].text.split()) == 4
    assert {s.kind for n in m.nodes if n.kind != "matched" for s in n.segments} == {"context"}
    roles = {e.id: e.role for e in r.evidence.items}
    for n in m.nodes:
        want = {"matched": "matched_source", "preceding_context": "preceding_context",
                "following_context": "following_context"}[n.kind]
        assert all(roles[i] == want for i in n.evidence_ids)
    assert m.facts["quoted_words"] == 4 and m.facts["omitted_words_in_matched"] > 0
    assert_traceable(r, real_repo)


def test_hadith_map_has_no_neighbouring_records(pipe, real_repo):
    r = ask(pipe, "إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى", CLAIM)
    m = r.evidence_map
    assert r.source.source_type == "hadith"
    assert [n.kind for n in m.nodes] == ["matched"] and m.facts["context_kind"] == "hadith_only"
    assert m.facts["preceding_units"] == 0 and m.facts["following_units"] == 0
    assert "quoted" in {s.kind for s in m.nodes[0].segments}
    assert m.result.context_relevance.value == "UNDETERMINED"
    assert m.result.context_relevance.basis == "NOT_ENABLED_FOR_SOURCE"
    assert_traceable(r, real_repo)


@pytest.mark.parametrize("quote", ["فبأي آلاء ربكما تكذبان", "إنما الأعمال بالنية"])
def test_ambiguous_gets_no_map(pipe, quote):
    r = ask(pipe, quote, CLAIM)
    assert r.quote_analysis.match_status == "AMBIGUOUS" and r.evidence_map is None


def test_not_found_gets_no_map(pipe):
    r = ask(pipe, "هذا نص عربي عادي لا يوجد في المصادر المعتمدة اطلاقا", CLAIM)
    assert r.quote_analysis.match_status == "NOT_FOUND" and r.evidence_map is None


def test_no_llm_infers_nothing_about_context(pipe, real_repo):
    r = ask(pipe, quote_2_191(real_repo), CLAIM)
    rel = r.evidence_map.result.context_relevance
    assert rel.value == "UNDETERMINED" and rel.basis == "NO_ANALYSIS" and rel.cited_evidence_ids == []


def test_verified_ai_analysis_citing_context_is_relevant(real_db, real_repo):
    out = good_output(relation="OVERSTATED", ids=("E1", "E3"))
    p = make_pipeline(real_db, script=[json.dumps(out, ensure_ascii=False)], **LSA)
    r = ask(p, quote_2_191(real_repo), CLAIM)
    rel = r.evidence_map.result.context_relevance
    ctx = {e.id for e in r.evidence.items if e.role in ("preceding_context", "following_context")}
    assert r.claim_analysis.status == "COMPLETED"
    assert rel.value == "RELEVANT" and rel.cited_evidence_ids and set(rel.cited_evidence_ids) <= ctx


def test_verified_ai_analysis_citing_only_the_match_is_limited(real_db, real_repo):
    p = make_pipeline(real_db, script=[json.dumps(good_output(ids=("E1",)), ensure_ascii=False)], **LSA)
    r = ask(p, quote_2_191(real_repo), CLAIM)
    assert r.evidence_map.result.context_relevance.value == "LIMITED"


def test_rejected_ai_output_is_not_used(real_db, real_repo):
    bad = json.dumps(good_output(ids=("E40",)), ensure_ascii=False)   # cites evidence that does not exist
    p = make_pipeline(real_db, script=[bad, bad], **LSA)
    r = ask(p, quote_2_191(real_repo), CLAIM)
    assert r.claim_analysis.status == "AI_OUTPUT_REJECTED"
    assert r.evidence_map.result.context_relevance.value == "UNDETERMINED"


def test_specialist_routing_needs_review(pipe, real_repo):
    r = ask(pipe, quote_2_191(real_repo), "هل يجوز لي أن أقاتل جاري الآن")
    assert r.claim_analysis.status == "REFERRED"
    assert r.evidence_map.result.context_relevance.value == "NEEDS_REVIEW"
