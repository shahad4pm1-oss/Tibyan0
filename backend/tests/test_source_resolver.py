import dataclasses

from app.services.source_resolver import SourceResolver
from app.services.types import MatchStatus, QuoteMatch, ResolutionStatus


def test_resolved(synthetic_repo):
    p = synthetic_repo.get("synth:1:1")
    r = SourceResolver(synthetic_repo).resolve(QuoteMatch(MatchStatus.EXACT, "phrase", [p]))
    assert r.status is ResolutionStatus.RESOLVED and r.source["id"] == "synth"


def test_ambiguous(synthetic_repo):
    alts = [synthetic_repo.get("synth:1:4"), synthetic_repo.get("synth:2:4")]
    r = SourceResolver(synthetic_repo).resolve(QuoteMatch(MatchStatus.AMBIGUOUS, "phrase", alternatives=alts,
                                                          alternatives_total=2))
    assert r.status is ResolutionStatus.AMBIGUOUS and r.alternatives_total == 2


def test_not_found(synthetic_repo):
    r = SourceResolver(synthetic_repo).resolve(QuoteMatch(MatchStatus.NOT_FOUND, "none"))
    assert r.status is ResolutionStatus.NOT_FOUND


def test_tampered_passage_fails_reverification(synthetic_repo):
    p = dataclasses.replace(synthetic_repo.get("synth:1:1"), original_text="نص مزور")
    r = SourceResolver(synthetic_repo).resolve(QuoteMatch(MatchStatus.EXACT, "phrase", [p]))
    assert r.status is ResolutionStatus.NOT_FOUND


def test_pending_passage_cannot_resolve(synthetic_repo):
    pending = synthetic_repo.conn.execute("SELECT id FROM passages WHERE source_id='synth_pending'").fetchone()[0]
    assert synthetic_repo.get(pending) is None  # not even retrievable
