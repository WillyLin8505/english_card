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


def _track(s):
    from app import models as m
    track = m.Lexeme(language="en", lemma="track", normalized="track", pos="noun", status="full")
    s.add(track)
    s.flush()
    for i, zh in enumerate(("追蹤", "軌道")):
        sense = m.Sense(lexeme_id=track.id, sense_key=f"s{i}", ordinal=i, labels=[])
        s.add(sense)
        s.flush()
        s.add(m.SenseTranslation(sense_id=sense.id, native_language="zh-TW", text=zh,
                                 source="kaikki"))
    s.flush()


def _lookup(s, field, rel):
    from app.adapters.local import LexiconLookup
    ctx = Context("en", "zh-TW", "trace", "trace", session=s, resolved={
        "native_definition": [{"sense_key": "s1", "text": "追蹤"}], rel: [{"word": "track"}]})
    return [c.value["text"] for c in LexiconLookup().normalize(field, None, ctx)]


def test_lexicon_lookup_keeps_full_entry_own_meaning(session):
    # A full look-alike entry gets its own first meaning even when it equals the
    # headword's (derived forms: independence/independent 獨立); the exporter hides
    # such rows (card #438) instead of showing a rare other sense (card #447 r2).
    _track(session)
    assert _lookup(session, "similar_spelling_native", "similar_spelling") == ["追蹤"]
    assert _lookup(session, "synonyms_native", "synonyms") == ["追蹤"]
