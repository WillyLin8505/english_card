import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.sense_order import english_sense_translations


def test_plate_dish_sense_lists_assiette_not_plaque():
    got = english_sense_translations(
        "plate", "noun", "fr", "A slightly curved but almost flat dish from which food is served or eaten.")
    assert "assiette" in got and "plaque" not in got


def test_unknown_gloss_is_none():
    assert english_sense_translations("plate", "noun", "fr", "no such sense") is None
