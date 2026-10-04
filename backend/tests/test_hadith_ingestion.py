"""Hadith (Sahih al-Bukhari, Sahih Muslim) parsing and ingestion.

Parser behaviour is tested on SYNTHETIC NON-RELIGIOUS text in the OpenITI format; the real corpus is
checked for shape, ids, metadata and the absence of source-file markup.
"""

import json
from pathlib import Path

import pytest

from app.corpus.openiti_hadith import clean, parse_bukhari, parse_muslim

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]


def test_bukhari_format_parser_on_synthetic_fixture():
    recs, st = parse_bukhari((FIX / "openiti_synthetic_bukhari_format.txt").read_text(encoding="utf-8"))
    by = {r.number: r for r in recs}
    assert sorted(by) == [1, 2, 3, 5]                     # the introduction's "1 -" is skipped
    assert by[1].text == "قال أمين المكتبة: افتح النافذة صباحا، ثم رتب الكتب على الرفوف الخشبية"
    assert by[2].text == "قالت المعلمة: الدرس يبدأ في الثامنة ويستمر ساعتين ثم قالت: لا تنسوا الدفاتر"
    assert "تعليق" not in by[2].text                       # editor commentary never enters a hadith
    assert by[1].book == "بدء الوحي" and by[1].chapter == "باب وصف المكتبة"
    assert by[3].numbers_covered == [3, 4] and by[3].book == "كتاب الطقس"
    assert by[3].chapter == "باب المطر في الربيع"           # bare "باب" heading + next line; HTML removed
    assert by[5].text == "قال الطالب: انتهى الامتحان"       # heading with a milestone token
    assert st["gaps"] == [] and st["duplicates"] == []


def test_muslim_format_parser_groups_narrations_and_skips_unnumbered():
    recs, st = parse_muslim((FIX / "openiti_synthetic_muslim_format.txt").read_text(encoding="utf-8"))
    assert [r.number for r in recs] == [100, 101]
    r100 = recs[0]
    assert r100.narrations == 2
    assert r100.text == "قال الدليل: الطريق طويل فاحملوا الماء والزاد\nوفي رواية: الطريق طويل فاحملوا الماء"
    assert r100.book == "كتاب السفر" and r100.chapter == "باب الاستعداد"
    assert recs[1].chapter == "باب الوصول"
    assert all("جهزت الحقيبة" not in r.text for r in recs)   # unnumbered text is never ingested
    assert st["gaps"][:3] == [1, 2, 3]                        # numbers absent from the file are reported


def test_clean_only_removes_markup():
    assert clean("نص ms0001 ثم PageV01P002 نص</span>  آخر") == "نص ثم نص آخر"


@pytest.mark.real_corpus
def test_real_hadith_corpus_shape(real_repo):
    c = real_repo.conn
    counts = dict(c.execute("SELECT source_id, count(*) FROM passages WHERE source_id LIKE 'hadith:%' GROUP BY 1"))
    assert counts == {"hadith:bukhari": 7380, "hadith:muslim": 2922 + 192}   # 192 unnumbered narrations
    for sid in ("hadith:bukhari", "hadith:muslim"):
        s = real_repo.source(sid)
        assert s["source_type"] == "hadith" and s["verification_status"] == "APPROVED"
        meta = json.loads(s["metadata_json"])
        assert meta["provenance"].startswith("https://github.com/OpenITI/0275AH @ 44e1c367")
    ids = [r[0] for r in c.execute("SELECT id FROM passages WHERE source_id LIKE 'hadith:%'")]
    assert len(ids) == len(set(ids))
    assert "hadith:bukhari:1" in ids and "hadith:bukhari:7563" in ids and "hadith:muslim:1907" in ids
    assert "hadith:muslim:8" not in ids        # Kitab al-Iman 1-99 are unnumbered in the file: not ingested


@pytest.mark.real_corpus
def test_real_hadith_text_is_the_source_file_text(real_repo):
    """bukhari:1 equals the paragraph lines under '### | 1 - ' in the pinned raw file, markup removed."""
    meta = json.loads((ROOT / "data/metadata/hadith_sahihayn_openiti.json").read_text(encoding="utf-8"))
    raw = (ROOT / meta["collections"][0]["file"]["local_path"]).read_text(encoding="utf-8").split("\n")
    start = next(i for i, ln in enumerate(raw) if ln.startswith("### | كيف كان بدء الوحي"))
    h = next(i for i in range(start, len(raw)) if raw[i].startswith("### | 1 -"))
    block = []
    for ln in raw[h + 1:]:
        if ln.startswith("###"):
            break
        block.append(ln[2:] if ln.startswith(("# ", "~~")) else ln)
    expected = clean(" ".join(block))
    p = real_repo.get("hadith:bukhari:1")
    assert p.original_text == expected
    assert "إنما الأعمال بالنيات" in p.original_text
    for pid in ("hadith:bukhari:1", "hadith:muslim:1907", "hadith:bukhari:7563"):
        t = real_repo.get(pid).original_text
        assert not any(m in t for m in ("PageV", "~~", "###", " ms0"))


@pytest.mark.real_corpus
def test_real_hadith_metadata(real_repo):
    p = real_repo.get("hadith:muslim:1907")
    m = p.metadata
    assert m["collection"] == "muslim" and m["collection_ar"] == "صحيح مسلم" and m["hadith_number"] == "1907"
    assert m["book"] == "كتاب الإمارة" and m["chapter"].startswith("باب")
    assert p.parent_id.startswith("hadith:muslim:book:")
    # no previous/next links for hadith: adjacent hadith are not context
    n = real_repo.conn.execute("SELECT count(*) FROM context_links WHERE passage_id LIKE 'hadith:%'").fetchone()[0]
    assert n == 0
