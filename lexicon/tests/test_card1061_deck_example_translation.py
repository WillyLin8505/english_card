"""Card #1061: deck examples carry translation / aiTranslated for the app."""
from app.decks import _with_translations


def test_zh_becomes_translation_and_ai_flag():
    out = _with_translations(None, [
        {"text": "a", "zh": "甲", "zh_ai": True},
        {"text": "b", "translation": "乙", "zh": "丙"},
        {"text": "c", "translation": "T", "translation_ai": True},
    ])
    assert out[0]["translation"] == "甲" and out[0]["aiTranslated"] is True and out[0]["zh"] == "甲"
    assert out[1]["translation"] == "乙" and "aiTranslated" not in out[1]
    assert out[2]["aiTranslated"] is True
