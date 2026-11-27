"""Card #1451: the importer shares a meaning group between its member words and is rerunnable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import import_word_ladder as iw


def test_senses_of_converts_prototype_candidates():
    e = {"word": "idea", "pos": "noun", "senses": [{"gloss": "g", "candidates": [{"w": "plan", "level": "A1"}]}]}
    (gloss, zh, ws), = list(iw.senses_of(e))
    assert gloss == "g" and ws[0]["cefr"] == "A1" and ws[0]["pos"] == "noun"


def test_norm_pos():
    assert iw.norm_pos("adj.") == "adj" and iw.norm_pos("Verb") == "verb"
