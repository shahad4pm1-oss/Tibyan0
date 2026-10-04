from app.services.context_expander import ContextExpander
from app.services.evidence_builder import EvidenceBuilder


def test_ids_roles_and_text(synthetic_repo):
    src = synthetic_repo.source("synth")
    ctx = ContextExpander(synthetic_repo, 2).expand([synthetic_repo.get("synth:1:3")], src)
    items = EvidenceBuilder().build(ctx, src)
    assert [e.id for e in items] == [f"E{i}" for i in range(1, len(items) + 1)]
    assert [e.role for e in items] == ["matched_source", "preceding_context", "preceding_context",
                                       "following_context", "following_context", "metadata"]
    for e in items:
        if e.passage_id:
            assert e.text == synthetic_repo.get(e.passage_id).original_text  # canonical text, not normalized
            assert e.source_id == "synth" and e.reference
