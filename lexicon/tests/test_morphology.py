"""構詞拆解: the local analyzer, Wiktionary affix markup, validation, and
the fields through the pipeline and export."""

import sqlite3

import pytest

from app import config, exporter, pipeline
from app.adapters import ADAPTERS, Candidate, Context
from app.adapters.base import validate
from app.morphology import Evidence, analyze, parts_from_affix_template, reconstructs, template_gloss
from conftest import apple_data

LATIN = Evidence("la", etym_without_affix=True)
OLD_ENGLISH = Evidence("ang", etym_without_affix=True)


def shown(word, ev=None):
    return [p.shown for p in analyze(word, ev).parts]


@pytest.mark.parametrize("word, ev, parts", [
    ("exterior", LATIN, ["ex", "-ter", "-ior"]),
    # 問題回報 #83
    ("decorative", Evidence("la"), ["decorate", "-ive"]),  # not de- + cor(心) + -ative
    ("grated", None, ["grate", "-ed"]),  # not grat(感謝) + -ed
    ("artisan", Evidence("fr", etym_without_affix=True), ["artisan"]),  # not arti + san
    ("flower", Evidence("fro", etym_without_affix=True), ["flower"]),  # not flow + -er
    ("natural", Evidence("fro"), ["nature", "-al"]),  # nature stays whole
    ("photograph", Evidence("grc"), ["photo", "graph"]),
    ("interior", LATIN, ["inter", "-ior"]),
    ("transportation", None, ["trans-", "port", "-ation"]),
    ("unhappiness", None, ["un-", "happy", "-ness"]),
    ("happiness", None, ["happy", "-ness"]),
    ("prediction", None, ["pre-", "dict", "-ion"]),
    ("inspection", LATIN, ["in-", "spect", "-ion"]),
    ("invisible", None, ["in-", "vis", "-ible"]),
    ("impossible", None, ["im-", "possible"]),
    ("reusable", None, ["re-", "use", "-able"]),
    ("understand", None, ["under-", "stand"]),
    ("breakfast", None, ["break", "fast"]),
    ("butter knife", None, ["butter", "knife"]),
    ("apple", OLD_ENGLISH, ["apple"]),
    ("bread", OLD_ENGLISH, ["bread"]),
    ("butter", OLD_ENGLISH, ["butter"]),  # not butt + -er
    ("example", LATIN, ["example"]),  # not ex- + ample
    ("ability", None, ["ability"]),
])
def test_breakdowns(word, ev, parts):
    assert shown(word, ev) == parts


def test_meanings_follow_what_the_prefix_attaches_to():
    def meaning(word, i=0):
        return analyze(word).parts[i].zh
    assert meaning("impossible") == "不、無"  # before an adjective
    assert meaning("invisible") == "不、無"
    assert meaning("income") == "在內、向內"
    assert meaning("information") == "在內、向內"
    assert meaning("unlock") == "反轉動作、解開"
    assert meaning("unhappiness") == "不"
    assert analyze("exterior", LATIN).parts[2].zh == "較…的（比較級）"


def test_letters_add_up_to_the_word():
    for w in ("happiness", "transportation", "unbelievable", "running", "exterior"):
        a = analyze(w, LATIN if w == "exterior" else None)
        assert "".join(p.text for p in a.parts) == w


def test_wiktionary_affix_templates():
    assert parts_from_affix_template({"1": "en", "2": "unhappy", "3": "-ness"}, "af") == \
        ["unhappy", "-ness"]
    assert parts_from_affix_template({"1": "en", "2": ":af", "3": "transport", "4": "-ation"},
                                     "ety") == ["transport", "-ation"]
    assert parts_from_affix_template({"1": "en", "2": "un", "3": "happy"}, "prefix") == \
        ["un-", "happy"]
    assert parts_from_affix_template({"1": "en", "2": "hap<t:luck>", "3": "y"}, "suffix") == \
        ["hap", "-y"]
    assert template_gloss("hap<t:chance, luck>") == "chance, luck"


def test_kaikki_breakdown_expands_word_parts():
    entries = [{"word": "unhappiness", "lang_code": "en", "pos": "noun",
                "etymology_templates": [{"name": "af", "args": {"1": "en", "2": "un-",
                                                                "3": "happiness"}}]}]
    k = ADAPTERS["kaikki"]
    c = k.normalize("morphemes", entries, Context("en", "zh-TW", "unhappiness", "unhappiness"))
    assert c[0].value["summary"] == "un- + happy + -ness"


def test_reconstructs_with_spelling_changes():
    assert reconstructs("happiness", ["happy", "-ness"])
    assert reconstructs("making", ["make", "-ing"])
    assert reconstructs("running", ["run", "-ing"])
    assert not reconstructs("exterior", ["ex", "terior", "-s"])


def test_validation_rejects_parts_that_do_not_spell_the_word():
    ctx = Context("en", "zh-TW", "exterior", "exterior")

    def v(parts):
        return validate(Candidate("morphemes", "en", {"parts": parts}, "k"), ctx)

    assert v([{"part": "ex", "kind": "root"}, {"part": "-ter", "kind": "suffix"},
              {"part": "-ior", "kind": "suffix"}]) is None
    assert v([{"part": "extra", "kind": "root"}, {"part": "-ior", "kind": "suffix"}]) == \
        "拆出的部件拼不回原字"
    assert v([{"part": "ex", "kind": "stem"}]) is not None


def test_pipeline_breakdown_native_meanings_and_export(session, fakes, tmp_path, monkeypatch):
    from app.adapters.morph import MorphLocal
    monkeypatch.setitem(ADAPTERS, "morph_local", MorphLocal())  # the real analyzer
    apple_data(fakes)
    fakes["kaikki"].data["origin_language"] = [({"language": "Latin", "code": "la"}, "la", "")]
    fakes["kaikki"].data["etymology_text"] = [({"text": "From Latin exterior.",
                                                "affix_templates": 0}, "e", "")]
    reports = {r.field: r for r in pipeline.process_word(session, "en", "zh-TW", "exterior", None,
                                                         "fill_missing")}
    bd = reports["morphemes"]
    assert bd.status == "complete" and bd.items[0]["summary"] == "ex + -ter + -ior"
    assert bd.items[0]["source"] == "morph_local"
    nat = reports["morphemes_native"]
    assert nat.status == "complete"
    assert [i["text"] for i in nat.items] == ["向外、出", "（拉丁字尾，表「…側」）", "較…的（比較級）"]
    assert [i["morpheme"] for i in reports["suffix"].items] == ["-ter", "-ior"]
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    assert rel.status == "ready", rel.error
    con = sqlite3.connect(tmp_path / rel.file_name / f"{rel.file_name}.sqlite")
    rows = con.execute("SELECT part, kind, native_meaning FROM morphemes ORDER BY ordinal").fetchall()
    assert rows == [("ex", "root", "向外、出"), ("-ter", "suffix", "（拉丁字尾，表「…側」）"),
                    ("-ior", "suffix", "較…的（比較級）")]


def test_surface_analysis_template_with_its_kind_first():
    # {{surf|+suf|en|nature|al}}: every argument one place later.
    assert parts_from_affix_template({"1": "+suf", "2": "en", "3": "nature", "4": "al"},
                                     "surf") == ["nature", "-al"]
