"""Card #539 (問題回報 #579): an established sense under a later etymology
(second 「unit of time」, tip 「gratuity」) is not labelled etymology-N by the
Kaikki adapter, and the etymology with the most established senses comes
first in the English sense order."""
from app import sense_order
from app.adapters.base import Context
from app.adapters.kaikki import Kaikki, established_sense, translation_counts


def _tr(n, lang="de"):
    return [{"lang_code": lang, "word": f"w{i}"} for i in range(n)]


SECOND = [
    {"word": "second", "pos": "noun", "lang_code": "en", "etymology_number": 1,
     "senses": [{"glosses": ["Something that is number two in a series."], "translations": _tr(17)},
                {"glosses": ["A second-class honours degree."], "tags": ["informal"]}]},
    {"word": "second", "pos": "noun", "lang_code": "en", "etymology_number": 2,
     "senses": [{"glosses": ["A unit of time, one sixtieth of a minute."], "translations": _tr(214)},
                {"glosses": ["A unit of angle equal to one-sixtieth of a minute of arc."]}]},
    {"word": "second", "pos": "noun", "lang_code": "en", "etymology_number": 3,
     "senses": [{"glosses": ["Aid; assistance; help."], "tags": ["obsolete"], "translations": _tr(30)}]},
]


def test_translation_counts_include_attached_entry_tables():
    e = {"word": "tip", "pos": "noun",
         "senses": [{"glosses": ["The extreme end of something, especially when pointed."]},
                    {"glosses": ["A small piece of meat."]}],
         "translations": [{"sense": "extreme end of something", "lang_code": "fr", "word": "pointe"},
                          {"sense": "extreme end of something", "lang_code": "de", "word": "Spitze"}]}
    assert translation_counts(e) == [2, 0]


def test_established_sense_needs_ten_translations():
    assert established_sense(SECOND[1], SECOND[1]["senses"][0])
    assert not established_sense(SECOND[1], SECOND[1]["senses"][1])
    assert established_sense(SECOND[0], SECOND[0]["senses"][0])  # 17 ≥ 10


def test_adapter_keeps_the_label_off_established_senses():
    ctx = Context("en", "zh-TW", "second", "second")
    defs = {d.value["gloss"]: d.value["labels"] for d in Kaikki().normalize("definition", SECOND, ctx)}
    assert defs["A unit of time, one sixtieth of a minute."] == []
    assert defs["A unit of angle equal to one-sixtieth of a minute of arc."] == ["etymology-2"]
    # an obsolete sense stays another word however large its table
    assert "etymology-3" in defs["Aid; assistance; help."]


def test_english_order_puts_the_heavier_etymology_first(monkeypatch):
    monkeypatch.setattr("app.kaikki_index.lookup",
                        lambda target, word, path=None: SECOND if word == "second" else [])
    sense_order.kaikki_sense_info.cache_clear()
    sense_order.etymology_weights.cache_clear()
    items = [{"pos": "noun", "gloss": "Something that is number two in a series.", "labels": []},
             {"pos": "noun", "gloss": "A second-class honours degree.", "labels": ["informal"]},
             {"pos": "noun", "gloss": "A unit of time, one sixtieth of a minute.", "labels": []},
             {"pos": "noun", "gloss": "A unit of angle equal to one-sixtieth of a minute of arc.",
              "labels": ["etymology-2"]},
             {"pos": "noun", "gloss": "Aid; assistance; help.", "labels": ["obsolete", "etymology-3"]}]
    assert dict(sense_order.etymology_weights("en", "second", "noun")) == {"1": 17, "2": 214, "3": 0}
    got = [it["gloss"][:12] for it in sense_order.order_senses(items, "en", "second")]
    assert got == ["A unit of ti", "A unit of an", "Something th", "A second-cla", "Aid; assista"]
    # French keeps the dictionary's order for the same labels
    assert [it["gloss"][:12] for it in sense_order.order_senses(items, "fr", "second")][0] == "Something th"


def test_a_later_etymology_needs_clearly_stronger_evidence():
    # phone: the telephone's table sits under telephone (0), phonetics has 31
    assert sense_order.etymology_order({"1": 0, "2": 31}) == ["1", "2"]
    assert sense_order.etymology_order({"1": 0, "2": 506}) == ["2", "1"]          # duck 鴨子
    assert sense_order.etymology_order({"1": 122, "2": 294, "3": 42}) == ["2", "1", "3"]  # second
    assert sense_order.etymology_order({"1": 83, "2": 16, "4": 115, "5": 72}) == ["1", "4", "5", "2"]  # tip
    assert sense_order.etymology_order({"1": 4, "2": 22, "3": 110}) == ["3", "1", "2"]  # down
