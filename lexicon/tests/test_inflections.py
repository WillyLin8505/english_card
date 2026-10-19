"""Inflected forms go to their word (問題回報 #51): runs, climbs and leaves
from photos are imported as run, climb, leaf and leave; a form that is also a
word of its own (lying 說謊的) keeps its entry without the form-only verb."""

from __future__ import annotations

from sqlalchemy import select

from app import jobs, kaikki_index, models as m, pipeline
from app.adapters.base import inflection_bases
from app.adapters.kaikki import inflection_only_pos
from conftest import apple_data


def form(base, *tags):
    return {"glosses": [f"form of {base}"], "form_of": [{"word": base}],
            "tags": ["form-of", *tags]}


DICTIONARY = {
    "runs": [{"word": "runs", "pos": "noun", "senses": [form("run", "plural")]},
             {"word": "runs", "pos": "noun",
              "senses": [{"glosses": ["Diarrhea."], "tags": ["slang", "plural-only"]}]},
             {"word": "runs", "pos": "verb", "senses": [form("run", "present")]}],
    "leaves": [{"word": "leaves", "pos": "noun", "senses": [form("leaf", "plural")]},
               {"word": "leaves", "pos": "verb", "senses": [form("leave", "present")]}],
    "children": [{"word": "children", "pos": "noun",
                  "senses": [form("child", "plural"), form("childer", "plural")]}],
    "lying": [{"word": "lying", "pos": "verb", "senses": [form("lie", "participle")]},
              {"word": "lying", "pos": "adj",
               "senses": [{"glosses": ["Tending to tell lies, untruthful."]}]}],
    "apples": [{"word": "apples", "pos": "noun", "senses": [form("apple", "plural")]}],
    # Kaikki copies the headword labels 「(auxiliary, dialectal or formal)」 onto
    # every sense; the only form-of is obsolete (問題回報 #337).
    "ought": [{"word": "ought", "pos": "verb", "senses": [form("owe", "obsolete", "past")]},
              {"word": "ought", "pos": "verb",
               "senses": [{"glosses": ["Indicating duty or obligation."],
                           "tags": ["auxiliary", "dialectal", "formal"]}]}],
    "holpen": [{"word": "holpen", "pos": "verb", "senses": [form("help", "archaic", "participle")]}],
    "thy": [{"word": "thy", "pos": "det", "senses": [form("thou", "archaic", "possessive")]},
            {"word": "thy", "pos": "det",
             "senses": [{"glosses": ["Thine."], "tags": ["obsolete"]}]}],
}


def _dictionary(monkeypatch):
    inflection_bases.cache_clear()
    monkeypatch.setattr(kaikki_index, "lookup",
                        lambda language, word, path=None: DICTIONARY.get(word.lower(), []))


def test_a_form_without_a_meaning_of_its_own_names_its_words(monkeypatch):
    _dictionary(monkeypatch)
    assert inflection_bases("runs", "en") == ("run",)  # the slang 「the runs」 doesn't count
    assert inflection_bases("leaves", "en") == ("leaf", "leave")
    assert inflection_bases("children", "en") == ("child",)  # not the dialectal childer
    assert inflection_bases("lying", "en") == ()  # also 說謊的
    assert inflection_bases("apple", "en") == ()
    inflection_bases.cache_clear()


def test_an_obsolete_inflection_does_not_claim_a_word_of_its_own(monkeypatch):
    _dictionary(monkeypatch)
    assert inflection_bases("ought", "en") == ()  # a modal, not the old past of owe
    assert inflection_bases("holpen", "en") == ("help",)  # nothing but the old form
    assert inflection_bases("thy", "en") == ("thou",)  # its own sense is obsolete too
    inflection_bases.cache_clear()


def test_a_form_only_part_of_speech_gets_no_entry():
    assert inflection_only_pos(DICTIONARY["lying"]) == {"verb"}
    assert inflection_only_pos(DICTIONARY["leaves"]) == set()  # all forms: see inflection_bases


def test_importing_a_form_imports_its_word(session, fakes, monkeypatch):
    apple_data(fakes)
    _dictionary(monkeypatch)
    pipeline.process_word(session, "en", "zh-TW", "apples", None, "fill_missing")
    session.flush()
    words = {lx.normalized: lx.status for lx in session.scalars(select(m.Lexeme))}
    assert words.get("apple") == "full" and "apples" not in words
    inflection_bases.cache_clear()


def test_the_missing_word_list_asks_for_the_word(session, monkeypatch):
    _dictionary(monkeypatch)
    for word in ("runs", "lying"):
        session.add(m.MissingLexemeRequest(target_language="en", lemma=word, count=1))
    session.flush()
    assert jobs.missing_words(session, "en") == ["run", "lying"]
    inflection_bases.cache_clear()


def test_ie_verbs_take_y_before_ing():
    from app.adapters.local import plausible_form
    assert plausible_form("lie", "lying") and plausible_form("die", "dying")


FAMILY = {
    "tethered": [{"word": "tethered", "pos": "adj", "senses": [{"glosses": ["Tied with a tether."]}]},
                 {"word": "tethered", "pos": "verb", "senses": [form("tether", "past")]}],
    "left": [{"word": "left", "pos": "adj", "etymology_number": 1,
              "senses": [{"glosses": ["On the west side when facing north."]}]},
             {"word": "left", "pos": "verb", "etymology_number": 2,
              "senses": [form("leave", "past")]}],
    "building": [{"word": "building", "pos": "noun",
                  "senses": [{"glosses": ["A closed structure with walls and a roof."]}]},
                 {"word": "building", "pos": "verb", "senses": [form("build", "participle")]}],
    "tired": [{"word": "tired", "pos": "adj", "senses": [{"glosses": ["In need of rest."]}]},
              {"word": "tired", "pos": "verb", "senses": [form("tire", "past")]}],
    **DICTIONARY,
}


def test_forms_that_share_their_words_card(monkeypatch):
    from app.adapters import base
    base.card_base.cache_clear()
    inflection_bases.cache_clear()
    monkeypatch.setattr(kaikki_index, "lookup",
                        lambda language, word, path=None: FAMILY.get(word.lower(), []))
    monkeypatch.setattr(base, "_listed_levels", lambda: {"tired": 0, "tire": 2})
    assert base.card_base("runs", "en") == "run"  # a pure form
    assert base.card_base("tethered", "en") == "tether"  # 被拴住的: still the participle
    assert base.card_base("lying", "en") == "lie"  # 說謊的、the act of lying
    assert base.card_base("left", "en") is None  # 左邊: another etymology
    assert base.card_base("building", "en") is None  # 建築物: a thing of its own
    assert base.card_base("tired", "en") is None  # met before tire
    assert base.card_base("leaves", "en") is None  # leaf or leave
    from app.app_pack import _form_only_pos, assign_cards
    _form_only_pos.cache_clear()
    lexemes = [{"normalized": w, "pos": p, "status": "full"} for w, p in (
        ("tether", "verb"), ("tethered", "adj"), ("tethered", "verb"), ("left", "adj"),
        ("lying", "adj"))]
    assign_cards(lexemes, "en")
    assert [lx.get("card") for lx in lexemes] == [None, "tether", "tether", None, None]  # no lie
    # tethered the verb is only tether's form: no meaning of its own on the card.
    assert [lx.get("card_form", False) for lx in lexemes] == [False, False, True, False, False]
    _form_only_pos.cache_clear()
    base.card_base.cache_clear()
    inflection_bases.cache_clear()
