"""#194 / #195: independent inflected forms stay, photo tags get a fitting sense."""

import importlib.util
from pathlib import Path

from app import quality as q

_spec = importlib.util.spec_from_file_location(
    "apply_quality_decisions", Path(__file__).resolve().parents[1] / "tools" / "apply_quality_decisions.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


ARCHED_ENTRIES = [
    {"pos": "adj", "senses": [{"tags": [], "glosses": ["Curved."]}]},
    {"pos": "verb", "senses": [{"tags": ["form-of", "participle", "past"],
                                "form_of": [{"word": "arch"}],
                                "glosses": ["simple past and past participle of arch"]}]},
]


def test_inflected_form_scoped_to_its_own_pos():
    """#194: arched the adjective (its own sense) is never redirected, even
    though arched the verb (same spelling, only sense is a past participle)
    is. 問題回報 #217/#222/#223: this must be decided per pos+entry in
    quality.inflection_base, not by a DB status check in apply_quality_decisions."""
    assert q.inflection_base("arched", "adj", ARCHED_ENTRIES, {"arch": ["B2"]}) is None
    assert q.inflection_base("arched", "verb", ARCHED_ENTRIES, {"arch": ["B2"]}) == "arch"


def test_full_inflected_form_is_not_redirected():
    rows = [(1, "arch", "noun", "full", "B2"), (2, "arched", "adj", "full", "C1"),
            (3, "tore", "unknown", "stub", "B2"), (4, "tear", "verb", "full", "B1")]
    # lint_lexicon.py no longer flags arched|adj at all (its own sense keeps it
    # independent at the quality.inflection_base layer, see test above).
    flags = {"tore|unknown": {"inflected_form": "tear", "excluded_has_cefr": "B2"}}
    d, log, counts = tool.plan(rows, flags)
    assert d["redirect"] == {"3": 4}
    assert 2 not in d["strip_cefr"] and "2" not in d["redirect"]


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
    # Card #435: the two tags remapped onto sense 102 merge into one
    assert [t["sense_id"] for t in tags] == [102, 110]
    assert tags[0]["sense_id_before"] == 100 and tags[1]["lexeme_id"] == 11
    assert pack["catalog_images"][0]["labels"][0]["lexeme_id"] == 11
    assert q.fix_catalog_senses(pack) == 0  # idempotent


def test_fix_catalog_senses_never_follows_redirect_to_stub():
    """Card #331: faded (full) -> fade the noun (stub) left 7 photo tags on a stub."""
    pack = {"lexemes": [{"id": 28210, "status": "full", "senses": [{"id": 21833, "native": "褪色的", "priority": "main"}]},
                        {"id": 1397, "status": "stub"}],
            "redirects": {"28210": 1397},
            "catalog_images": [{"tags": [{"lexeme_id": 28210, "sense_id": 21833}],
                                "labels": [{"lexeme_id": 28210}]}]}
    q.fix_catalog_senses(pack)
    im = pack["catalog_images"][0]
    assert im["tags"][0]["lexeme_id"] == 28210 and im["labels"][0]["lexeme_id"] == 28210


def test_etymology_sense_is_low():
    assert q.sense_is_low({"labels": ["etymology-2"], "native": "語音", "native_ai": False}, False)

def test_photo_tag_moves_from_first_main_sense_to_approved_sense():
    # Card #705 (問題回報 #841): open 可通行 (first main) → approved 打開的; the label follows.
    pack = {"lexemes": [{"id": 10, "senses": [{"id": 100, "native": "可通行", "priority": "main"},
                                              {"id": 101, "native": "打開的", "priority": "main"}]}],
            "redirects": {},
            "catalog_images": [{"tags": [{"lexeme_id": 10, "sense_id": 100}],
                                "labels": [{"lexeme_id": 10}]}]}
    q.fix_catalog_senses(pack, {10: 101})
    im = pack["catalog_images"][0]
    assert im["tags"][0]["sense_id"] == 101 and im["tags"][0]["sense_id_before"] == 100
    assert im["labels"][0]["sense_id"] == 101
    assert q.fix_catalog_senses(pack, {10: 101}) == 0  # idempotent
