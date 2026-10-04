"""Unit tests: one per normalization rule. Inputs are synthetic, non-religious words."""

import unicodedata

from app.services.normalizer import VERSION, normalize_for_search, tokens


def test_version_label():
    assert VERSION == "norm-v1"


def test_r1_unicode_nfc():
    decomposed = unicodedata.normalize("NFD", "آلة")  # alef madda decomposes to alef + U+0653
    assert normalize_for_search(decomposed) == normalize_for_search("آلة")


def test_r2_tatweel_removed():
    assert normalize_for_search("كـــتاب") == "كتاب"


def test_r3_diacritics_removed():
    assert normalize_for_search("كَتَبَ الطَّالِبُ") == "كتب الطالب"


def test_r3_tanween_and_sukun_removed():
    assert normalize_for_search("كِتَابًا مُلَخَّصْ") == "كتابا ملخص"


def test_r3_superscript_alef_and_small_marks_removed():
    assert normalize_for_search("هٰذا") == "هذا"
    assert normalize_for_search("كتبۡ") == "كتب"  # small high dotless head of khah (sukun form)


def test_r4_symbols_punctuation_digits_become_space():
    assert normalize_for_search("﴿ذهب، الطالب؟﴾ (12)") == "ذهب الطالب"
    assert normalize_for_search("«مرحبا» ٣٤ ۞ بيت") == "مرحبا بيت"


def test_r5_alef_forms_unified():
    assert normalize_for_search("أحمد إلى آخر ٱلبيت") == "احمد الى اخر البيت"


def test_r6_whitespace_and_nbsp():
    assert normalize_for_search("  كتاب   جديد\t\n") == "كتاب جديد"


def test_not_applied_ta_marbuta():
    assert normalize_for_search("مدرسة") == "مدرسة"
    assert normalize_for_search("مدرسه") == "مدرسه"


def test_not_applied_alef_maqsura():
    assert normalize_for_search("على") != normalize_for_search("علي")


def test_not_applied_hamza_seats():
    assert normalize_for_search("مسؤول") == "مسؤول"


def test_input_object_not_mutated():
    s = "كَتَبَ"
    normalize_for_search(s)
    assert s == "كَتَبَ"


def test_tokens_split():
    assert tokens(" ذهب   الطالب ") == ["ذهب", "الطالب"]
    assert tokens("") == []
