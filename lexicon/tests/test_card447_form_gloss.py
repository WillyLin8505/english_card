"""問題回報 #441: a look-alike word (near_homophones / similar_spelling) must get
its own meaning, never the headword's (gulp → gul 「一口量」)."""

from __future__ import annotations

from app.adapters import Context
from app.adapters.ai import AITranslate


def _ctx():
    return Context("en", "zh-TW", "gulp", "gulp", session=None, resolved={
        "definition": [{"sense_key": "s1", "gloss": "A mouthful; a swallow.", "pos": "noun"}],
        "native_definition": [{"sense_key": "s1", "text": "一口量"}],
        "near_homophones": [{"word": "gul"}, {"word": "gull"}],
        "synonyms": [{"word": "swallow"}],
    })


def test_form_request_does_not_send_headword_gloss():
    kind, items = AITranslate()._text_request("near_homophones_native", _ctx())
    assert kind == "word"
    for item in items:
        assert "mouthful" not in item["context"]
        assert "not the meaning of 'gulp'" in item["context"]
        assert item["category"] == "form"
    # Meaning relations still get the sense as context.
    _, items = AITranslate()._text_request("synonyms_native", _ctx())
    assert "mouthful" in items[0]["context"]


def test_copied_headword_meaning_is_dropped(monkeypatch):
    adapter = AITranslate()
    monkeypatch.setattr(adapter, "_call", lambda ctx, kind, items, lang_out=None: (
        {"gul": "一口量。", "gull": "海鷗"}, "qwen/test"))
    got = {c.value["word"]: c.value["text"]
           for c in adapter.lookup("near_homophones_native", _ctx())}
    assert got == {"gull": "海鷗"}


def test_meaning_relation_may_share_headword_meaning(monkeypatch):
    adapter = AITranslate()
    monkeypatch.setattr(adapter, "_call", lambda ctx, kind, items, lang_out=None: (
        {"swallow": "一口量"}, "qwen/test"))
    got = {c.value["word"]: c.value["text"] for c in adapter.lookup("synonyms_native", _ctx())}
    assert got == {"swallow": "一口量"}
