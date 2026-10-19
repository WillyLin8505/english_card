"""AI 翻譯 reuses translations the lexicon already stores instead of asking
the model again: the same relation word under another headword, the same
example sentence."""

from __future__ import annotations

from app import models as m
from app.adapters import Context
from app.adapters.ai import AITranslate


def _store_existing(s):
    heads = [m.Lexeme(language="en", lemma=w, normalized=w, pos="adj", status="full")
             for w in ("big", "great", "wide")]
    large = m.Lexeme(language="en", lemma="large", normalized="large", pos="adj", status="full")
    s.add_all([*heads, large])
    s.flush()
    big = heads[0]
    # "large" was translated for three other headwords; the most common text wins.
    for head, text in zip(heads, ("大的", "大的", "巨大")):
        rel = m.LexemeRelation(lexeme_id=head.id, relation="synonyms", target_lexeme_id=large.id,
                               target_word="large", source="oewn")
        s.add(rel)
        s.flush()
        s.add(m.RelationTranslation(relation_id=rel.id, native_language="zh-TW", text=text,
                                    source="ai_translate", is_ai=True))
    example = m.Example(lexeme_id=big.id, language="en", text="A large dog barked.",
                        text_hash="h1", source="tatoeba")
    s.add(example)
    s.flush()
    s.add(m.ExampleTranslation(example_id=example.id, native_language="zh-TW",
                               text="一隻大狗叫了。", source="tatoeba"))
    s.flush()


def test_prefetch_reuses_stored_translations(session, monkeypatch):
    _store_existing(session)
    adapter = AITranslate()
    ctx = Context("en", "zh-TW", "huge", "huge", session=session, resolved={
        "definition": [{"sense_key": "s1", "gloss": "Very large.", "pos": "adj"}],
        "example_sentences": [{"key": "e1", "text": "A large dog barked."},
                              {"key": "e2", "text": "The huge wave hit the boat."}],
        "synonyms": [{"word": "Large"}, {"word": "vast"}],
    })
    for field, slots in (("native_definition", {"s1"}), ("example_translation", {"e1", "e2"}),
                         ("synonyms_native", {"large", "vast"})):
        ctx.memo[("missing_slots", field)] = slots
    sent = []

    def fake_call(context, kind, items, lang_out=None):
        sent.extend(items)
        # Plain Chinese: "譯-vast" would be dropped by the Latin-letter guard (問題回報 #334).
        return ({item["id"]: {"vast": "廣大"}.get(item["text"], "譯文") for item in items},
                "qwen/test")

    monkeypatch.setattr(adapter, "_call", fake_call)
    assert adapter.prefetch(ctx, ["native_definition", "example_translation",
                                  "synonyms_native"]) == 1

    # Only what the lexicon has never translated reaches the model.
    assert sorted(item["text"] for item in sent) == [
        "The huge wave hit the boat.", "Very large.", "vast"]
    words = {c.value["word"]: c for c in adapter.lookup("synonyms_native", ctx)}
    assert words["large"].value["text"] == "大的"
    assert words["large"].value["ai"] is True  # still marked AI
    assert words["vast"].value["text"] == "廣大"
    examples = {c.value["example_key"]: c.value["text"]
                for c in adapter.lookup("example_translation", ctx)}
    assert examples["e1"] == "一隻大狗叫了。"
    assert "reused" in words["large"].source_record_id


def test_everything_reused_needs_no_model_call(session, monkeypatch):
    _store_existing(session)
    adapter = AITranslate()
    ctx = Context("en", "zh-TW", "huge", "huge", session=session,
                  resolved={"synonyms": [{"word": "large"}]})
    ctx.memo[("missing_slots", "synonyms_native")] = {"large"}
    monkeypatch.setattr(adapter, "_call", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("no model call expected")))
    assert adapter.prefetch(ctx, ["synonyms_native"]) == 0
    assert adapter.lookup("synonyms_native", ctx)[0].value["text"] == "大的"


def test_homophone_translation_not_reused_for_a_meaning_relation(session, monkeypatch):
    """問題回報 #253: "phone"'s near-homophone "fawn" cached 小鹿 (the deer
    sense). "cringe"'s synonym "fawn" (the fawn-over/flatter sense) must not
    reuse that text just because the word matches — the relation categories
    differ, so the model is asked instead."""
    fawn = m.Lexeme(language="en", lemma="fawn", normalized="fawn", pos="noun", status="stub")
    phone = m.Lexeme(language="en", lemma="phone", normalized="phone", pos="noun", status="full")
    s = session
    s.add_all([fawn, phone])
    s.flush()
    rel = m.LexemeRelation(lexeme_id=phone.id, relation="near_homophones",
                           target_lexeme_id=fawn.id, target_word="fawn", source="kaikki")
    s.add(rel)
    s.flush()
    s.add(m.RelationTranslation(relation_id=rel.id, native_language="zh-TW", text="小鹿",
                                source="kaikki", is_ai=False))
    s.flush()

    adapter = AITranslate()
    ctx = Context("en", "zh-TW", "cringe", "cringe", session=s, resolved={
        "definition": [{"sense_key": "s1", "gloss": "to behave obsequiously.", "pos": "verb"}],
        "synonyms": [{"word": "fawn"}],
    })
    ctx.memo[("missing_slots", "synonyms_native")] = {"fawn"}

    def fake_call(context, kind, items, lang_out=None):
        return ({item["id"]: "奉承" for item in items}, "qwen/test")

    monkeypatch.setattr(adapter, "_call", fake_call)
    assert adapter.prefetch(ctx, ["synonyms_native"]) == 1
    result = adapter.lookup("synonyms_native", ctx)[0].value
    assert result["text"] == "奉承"
