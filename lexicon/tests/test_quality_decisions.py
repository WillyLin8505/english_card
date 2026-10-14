"""Owner decision 問題回報 #191: redirects, CEFR strip and correction. Unit tests."""

import importlib.util
from pathlib import Path

from app import quality as q

_spec = importlib.util.spec_from_file_location(
    "apply_quality_decisions", Path(__file__).resolve().parents[1] / "tools" / "apply_quality_decisions.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

ROWS = [(1, "tear", "noun", "full", "A2"), (2, "tear", "verb", "full", "B1"),
        (3, "tore", "unknown", "stub", "B2"), (4, "fleeing", "unknown", "stub", "B2"),
        (5, "flee", "verb", "full", "B2"), (6, "chen", "unknown", "stub", "B1"),
        (7, "laptop", "noun", "full", "C1"), (8, "grassy", "adj", "full", "C1"),
        (9, "make light of", "verb", "stub", "A1"), (10, "zorbed", "unknown", "stub", "C2")]
FLAGS = {"tore|unknown": {"inflected_form": "tear", "excluded_has_cefr": "B2"},
         "fleeing|unknown": {"inflected_form": "flee"},
         "chen|unknown": {"person_name": "人名", "excluded_has_cefr": "B1"},
         "laptop|noun": {"cefr_above_list": "B2"},
         "grassy|adj": {"common_word_too_hard": "由 grass 衍生，建議 ≤B1"},
         "make light of|verb": {"idiom_too_easy": "B2"},
         "zorbed|unknown": {"inflected_form": "zorb"},
         "missing|noun": {"person_name": "人名"}}


def test_plan_actions():
    d, log, counts = tool.plan(ROWS, FLAGS)
    assert d["redirect"] == {"3": 2, "4": 5}  # tore -> tear (verb, -ed/past pool), fleeing -> flee
    assert sorted(d["strip_cefr"]) == [6, 10]  # chen; zorbed has no lemma entry
    assert d["set_cefr"] == {"7": "B2", "8": "B1", "9": "B2"}
    assert counts["not_in_db"] == 1 and counts["set_cefr_ambiguous"] == 1
    assert any(e["action"] == "set_cefr" and e["ambiguous"] for e in log)


def _pack():
    return {"redirects": {}, "lexemes": [
        {"id": 2, "lemma": "tear", "normalized": "tear", "pos": "verb", "status": "full", "cefr": "B1",
         "senses": [{"id": 20, "images": [{"path": "a.webp"}]}], "examples": []},
        {"id": 3, "lemma": "tore", "normalized": "tore", "pos": "adj", "status": "full", "cefr": "B2",
         "senses": [{"id": 30, "images": [{"path": "b.webp"}, {"path": "a.webp"}]}],
         "examples": [{"text": "She tore the page.", "quality_flags": []},
                      {"text": "torn", "quality_flags": ["not_sentence"]}]},
        {"id": 6, "lemma": "chen", "normalized": "chen", "pos": "unknown", "status": "stub", "cefr": "B1"},
        {"id": 7, "lemma": "laptop", "normalized": "laptop", "pos": "noun", "status": "full", "cefr": "C1"}]}


def test_apply_decisions_pointer_merge_and_levels():
    pack = _pack()
    d = {"redirect": {"3": 2}, "strip_cefr": [6], "set_cefr": {"7": "B2"}}
    counts = q.apply_decisions(pack, d)
    tear, tore, chen, laptop = pack["lexemes"]
    assert tore["redirect_to"] == 2 and tore["cefr"] is None and tore["card"] == "tear"
    assert pack["redirects"]["3"] == 2
    assert [i["path"] for i in tear["senses"][0]["images"]] == ["a.webp", "b.webp"]
    assert [e["text"] for e in tear["examples"]] == ["She tore the page."]
    assert chen["cefr"] is None and chen["cefr_before_rule"] == "B1"
    assert laptop["cefr"] == "B2" and laptop["cefr_source"] == "quality_rule"
    assert counts == {"redirect": 1, "strip_cefr": 1, "set_cefr": 1,
                      "merged_images": 1, "merged_examples": 1}
    # Idempotent: a second run (serve_app after the catalog merge) adds nothing.
    q.apply_decisions(pack, d)
    assert len(tear["senses"][0]["images"]) == 2 and len(tear["examples"]) == 1
    assert chen["cefr_before_rule"] == "B1"