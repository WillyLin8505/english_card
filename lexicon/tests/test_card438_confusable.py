"""Card #438 (問題回報 #420): 「容易混淆的字」 rows the exporter hides."""
from types import SimpleNamespace

from app import exporter


def _target(status="full"):
    return SimpleNamespace(status=status)


def test_stub_target_is_hidden():
    # gul/gol/gump are only link stubs in the lexicon
    assert exporter.confusable_problem("gul", "gulp", _target("stub"), "一口量", set()) == "not_in_lexicon"


def test_same_meaning_as_headword_is_hidden():
    head = {exporter.zh_key("充足的、足夠的")}
    assert exporter.confusable_problem("amble", "ample", _target(), "充足的 、足夠的。", head) == "same_meaning"


def test_real_confusable_word_is_kept():
    assert exporter.confusable_problem("lot", "hot", _target(), "運氣", {"熱的"}) is None


def test_spelling_variant_is_hidden():
    assert exporter.confusable_problem("colour", "color", _target(), "顏色", set()) == "spelling_variant"
    assert exporter.confusable_problem("centre", "center", _target(), "中心", set()) == "spelling_variant"
    assert exporter.confusable_problem("patronize", "patronise", _target(), "栽培", set()) == "spelling_variant"


def test_four_for_is_not_a_variant():
    assert exporter.confusable_problem("for", "four", _target(), "為了", set()) is None


def test_melancholic_is_not_a_variant_of_melancholy():
    assert exporter.confusable_problem("melancholic", "melancholy", _target(), "憂鬱的", set()) is None
