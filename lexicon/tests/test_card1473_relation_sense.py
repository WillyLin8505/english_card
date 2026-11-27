"""問題回報 #253 (card #1473): a relation word is asked with the headword sense of its own
part of speech, not always the headword's first sense (cringe → verb synonym funk 臭味)."""

from __future__ import annotations

from app.adapters import Context
from app.adapters.ai import AITranslate


def _ctx():
    return Context("en", "zh-TW", "cringe", "cringe", session=None, resolved={
        "definition": [
            {"sense_key": "n1", "gloss": "A cringing sensation; a shudder.", "pos": "noun"},
            {"sense_key": "v1", "gloss": "To act in an obsequious or servile manner.", "pos": "verb"},
        ],
        "synonyms": [{"word": "funk", "pos": "verb"}, {"word": "cower"}],
        "near_homophones": [{"word": "crine"}],
    })


def test_relation_word_gets_headword_sense_of_its_own_pos():
    _, items = AITranslate()._text_request("synonyms_native", _ctx())
    funk = next(i for i in items if i["text"] == "funk")
    assert "obsequious" in funk["context"]
    assert "shudder" not in funk["context"]


def test_relation_word_without_pos_keeps_first_sense():
    _, items = AITranslate()._text_request("synonyms_native", _ctx())
    cower = next(i for i in items if i["text"] == "cower")
    assert "shudder" in cower["context"]


def test_form_relation_context_unchanged():
    _, items = AITranslate()._text_request("near_homophones_native", _ctx())
    assert items[0]["category"] == "form"
    assert "not the meaning of 'cringe'" in items[0]["context"]
    assert "obsequious" not in items[0]["context"]
