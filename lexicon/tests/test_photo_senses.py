"""#194 / #195: independent inflected forms stay, photo tags get a fitting sense."""

import importlib.util
from pathlib import Path

from app import quality as q

_spec = importlib.util.spec_from_file_location(
    "apply_quality_decisions", Path(__file__).resolve().parents[1] / "tools" / "apply_quality_decisions.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def test_full_inflected_form_is_not_redirected():
    rows = [(1, "arch", "noun", "full", "B2"), (2, "arched", "adj", "full", "C1"),
            (3, "tore", "unknown", "stub", "B2"), (4, "tear", "verb", "full", "B1")]
    flags = {"arched|adj": {"inflected_form": "arch", "excluded_has_cefr": "C1"},
             "tore|unknown": {"inflected_form": "tear", "excluded_has_cefr": "B2"}}
    d, log, counts = tool.plan(rows, flags)
    assert d["redirect"] == {"3": 4}
    assert 2 not in d["strip_cefr"] and "2" not in d["redirect"]
    assert counts["keep_independent_form"] == 1


def _c(i, pos, ordinal, definition, native, ai=False, low=False):
    return {"id": i, "lexeme_pos": pos, "ordinal": ordinal, "definition": definition,
            "native": native, "native_ai": ai, "labels": [], "low": low}


def test_choose_sense_uses_photo_context():
    screen = [_c(1, "noun", 0, "A physical divider intended to block an area from view.", "屏風"),
              _c(2, "noun", 1, "A flat electronic panel that shows pictures or text, such as a monitor, TV or phone screen.",
                 "螢幕")]
    best, top, second = q.choose_sense(screen, q.tokens("phone antenna flip phone"), 1, "noun")
    assert best["id"] == 2 and top > second


def test_choose_sense_skips_low_and_chinese_less():
    cands = [_c(1, "noun", 0, "A slang word for a person.", "傢伙", low=True),
             _c(2, "noun", 1, "A curved structure over an opening.", None),
             _c(3, "noun", 2, "An arched structure in a building or bridge.", "拱")]
    best, _, _ = q.choose_sense(cands, q.tokens("bridge stone"), 1)
    assert best["id"] == 3
    assert q.choose_sense([_c(1, "noun", 0, "x", None)], set())[0] is None


def test_fix_catalog_senses_follows_redirect_and_falls_back():
    pack = {"lexemes": [{"id": 10, "senses": [{"id": 100, "native": "", "priority": "main"},
                                              {"id": 101, "native": "靜脈", "priority": "low"},
                                              {"id": 102, "native": "葉脈", "priority": "main"}]},
                        {"id": 11, "senses": [{"id": 110, "native": "拱", "priority": "main"}]}],
            "redirects": {"12": 11},
            "catalog_images": [{"tags": [{"lexeme_id": 10, "sense_id": 100}, {"lexeme_id": 10, "sense_id": 101},
                                         {"lexeme_id": 12, "sense_id": 999}],
                                "labels": [{"lexeme_id": 12}]}]}
    assert q.fix_catalog_senses(pack) == 3
    tags = pack["catalog_images"][0]["tags"]
    assert [t["sense_id"] for t in tags] == [102, 102, 110]
    assert tags[0]["sense_id_before"] == 100 and tags[2]["lexeme_id"] == 11
    assert pack["catalog_images"][0]["labels"][0]["lexeme_id"] == 11
    assert q.fix_catalog_senses(pack) == 0  # idempotent


def test_etymology_sense_is_low():
    assert q.sense_is_low({"labels": ["etymology-2"], "native": "語音", "native_ai": False}, False)