import pytest

from app.services.context_expander import ContextExpander


def ids(ps):
    return [p.id for p in ps]


def test_sequential_window_synthetic(synthetic_repo):
    src = synthetic_repo.source("synth")
    ctx = ContextExpander(synthetic_repo, 2).expand([synthetic_repo.get("synth:1:3")], src)
    assert ids(ctx.before) == ["synth:1:1", "synth:1:2"]
    assert ids(ctx.after) == ["synth:1:4", "synth:1:5"]
    assert ctx.kind == "retrieved_context_window"


def test_window_never_crosses_group(synthetic_repo):
    src = synthetic_repo.source("synth")
    ctx = ContextExpander(synthetic_repo, 2).expand([synthetic_repo.get("synth:1:6")], src)
    assert ids(ctx.after) == []
    ctx = ContextExpander(synthetic_repo, 2).expand([synthetic_repo.get("synth:2:1")], src)
    assert ids(ctx.before) == []


def test_hadith_single_unit_no_neighbours(synthetic_repo):
    src = synthetic_repo.source("synth_collection")
    h = synthetic_repo.get("synth_collection:2")
    ctx = ContextExpander(synthetic_repo, 2).expand([h], src)
    assert ctx.before == [] and ctx.after == [] and ids(ctx.matched) == ["synth_collection:2"]
    assert h.metadata["book"] and h.metadata["chapter"] and h.metadata["grading"]


@pytest.mark.real_corpus
def test_real_quran_window(real_repo):
    src = real_repo.source("quran")
    e = ContextExpander(real_repo, 2)
    ctx = e.expand([real_repo.get("quran:2:191")], src)
    assert ids(ctx.before) == ["quran:2:189", "quran:2:190"] and ids(ctx.after) == ["quran:2:192", "quran:2:193"]
    first = e.expand([real_repo.get("quran:1:1")], src)
    assert first.before == [] and ids(first.after) == ["quran:1:2", "quran:1:3"]
    last = e.expand([real_repo.get("quran:1:7")], src)
    assert last.after == []  # never crosses into the next surah


@pytest.mark.real_corpus
def test_real_span_window(real_repo):
    ctx = ContextExpander(real_repo, 2).expand([real_repo.get("quran:2:190"), real_repo.get("quran:2:191")],
                                               real_repo.source("quran"))
    assert ids(ctx.before) == ["quran:2:188", "quran:2:189"] and ids(ctx.after) == ["quran:2:192", "quran:2:193"]
