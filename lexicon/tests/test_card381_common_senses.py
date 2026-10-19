"""Card #381 (問題回報 #341): a translation table that matches no sense no
longer lands on the first sense, reviewed common English senses come first,
and a first sense keeps its main rank under another etymology."""
from app import quality, sense_order
from app.adapters.base import Context
from app.adapters.kaikki import Kaikki


def _zh(word, title, dis1=""):
    return {"lang": "Chinese Mandarin", "lang_code": "zh", "word": word, "sense": title, "_dis1": dis1}


def _native(entry, lemma="moment"):
    ad = Kaikki()
    ctx = Context("en", "zh-TW", lemma, lemma)
    out = {}
    ad._native_definitions([entry], ctx, lambda v, k, **kw: out.__setitem__(v["sense_key"], v["text"]))
    gloss = {s["sense_key"]: s["gloss"] for s in ad.senses([entry], ctx)}
    return {gloss[k]: t for k, t in out.items()}


def test_unmatched_tables_follow_dis1_or_leave_the_first_sense():
    senses = [{"glosses": ["A particular point of space; a spot."]},
              {"glosses": ["A particular point of time; an instant."]},
              {"glosses": ["Ellipsis of moment of force."], "tags": ["form-of"], "form_of": [{"word": "x"}]},
              {"glosses": ["A brief, unspecified amount of time."]}]
    senses[1]["translations"] = [_zh("刻", "moment in time")]
    senses[2]["translations"] = [_zh("力矩", "moment of force", "0 0 100 0")]  # a sense not kept
    entry = {"word": "moment", "pos": "noun", "lang_code": "en", "senses": senses,
             "translations": [_zh("瞬間 /瞬间", "very brief period of time", "0 0 0 95")]}
    got = _native(entry)
    assert "A particular point of space; a spot." not in got  # was 力矩
    assert got["A particular point of time; an instant."] == "刻"
    assert got["A brief, unspecified amount of time."] == "瞬間"


def test_a_domain_title_does_not_fall_back_to_the_first_sense():
    entry = {"word": "top", "pos": "noun", "lang_code": "en",
             "senses": [{"glosses": ["The highest or uppermost part of something."]},
                        {"glosses": ["The dominant partner."], "tags": ["slang"]}],
             "translations": [_zh("頂 /顶", "uppermost part"),
                              _zh("主動 /主动", "gay sexual slang: one who penetrates", "40 45")]}
    assert _native(entry, "top") == {"The highest or uppermost part of something.": "頂"}


def test_an_unmatched_plain_table_still_goes_to_the_first_sense():
    entry = {"word": "hot", "pos": "adj", "lang_code": "en",
             "senses": [{"glosses": ["Having or giving off a high temperature."]},
                        {"glosses": ["Feverish."]}],
             "translations": [_zh("熱 /热", "of the weather")]}
    assert _native(entry, "hot") == {"Having or giving off a high temperature.": "熱"}


def test_reviewed_common_senses_come_first(monkeypatch):
    monkeypatch.setattr(sense_order, "english_common_senses",
                        lambda: {"train|noun": {"first": ["A group of animals, vehicles"]}})
    items = [{"pos": "noun", "gloss": "The elongated back portion of a dress."},
             {"pos": "noun", "gloss": "A trail of gunpowder."},
             {"pos": "noun", "gloss": "A group of animals, vehicles, or people in a line."}]
    assert [i["gloss"][:7] for i in sense_order.order_senses(items, "en", "train")] == \
        ["A group", "The elo", "A trail"]


def test_a_first_sense_under_another_etymology_stays_main():
    ranked = quality.rank_senses([
        {"id": 1, "native": "日期", "labels": ["etymology-2"]},
        {"id": 2, "native": "椰棗", "labels": []},
        {"id": 3, "native": "約會", "labels": ["etymology-2"]}])
    assert {s["id"]: s["priority"] for s in ranked} == {1: "main", 2: "main", 3: "low"}
