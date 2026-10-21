"""卡 #499（問題回報 #504）: French Kaikki inflection senses that carry no `form_of` /
form-of tag and only say so in the gloss (aimez 「second-person plural present
indicative/imperative of aimer」) must read as forms, not as meanings of their own."""

from __future__ import annotations

from app.adapters.base import (form_bases, gloss_inflection_base, gloss_spelling_base,
                               is_form_sense)
from app.adapters.kaikki import _form_entry_bases, inflection_only_pos


def _entry(pos, *senses, forms=None):
    return {"word": "x", "pos": pos, "senses": list(senses), "forms": forms or []}


def _sense(gloss, **kw):
    return {"glosses": [gloss], **kw}


def test_gloss_inflection_base_reads_french_verb_forms():
    assert gloss_inflection_base(
        "second-person plural present indicative/imperative of aimer") == "aimer"
    assert gloss_inflection_base("third-person plural present/subjunctive of conter") == "conter"
    assert gloss_inflection_base(
        "first-person singular indicative/present of poitriner") == "poitriner"
    assert gloss_inflection_base("present participle of permettre") == "permettre"
    assert gloss_inflection_base("feminine plural of beau") == "beau"
    assert gloss_inflection_base("inflection of aimer:") == "aimer"
    # the base inside a parenthesis counts (plait: a spelling of plaît, plaire's form)
    assert gloss_inflection_base(
        "post-1990 spelling of plaît (third-person singular present indicative of plaire)"
    ) == "plaire"


def test_gloss_inflection_base_leaves_real_meanings_alone():
    assert gloss_inflection_base("Indicative of unkind or malevolent intentions") is None
    assert gloss_inflection_base("a form of cancer") is None
    assert gloss_inflection_base("the act of running") is None
    assert gloss_inflection_base("doubts, misgivings (apprehension)") is None
    assert gloss_inflection_base("concrete") is None
    assert gloss_inflection_base("") is None


def test_spelling_and_bound_glosses_are_forms_without_a_base():
    assert gloss_spelling_base("post-1990 spelling of connaître") == "connaître"
    assert gloss_spelling_base("Dated spelling of calorie.") == "calorie"
    assert gloss_spelling_base("a form of cancer") is None
    s = _sense("post-1990 spelling of connaître")
    assert is_form_sense(s) and form_bases(s) == []  # keeps its own conjugation
    assert is_form_sense(_sense("only used in laisse béton"))
    assert not is_form_sense(_sense("concrete", tags=["masculine"]))


def test_metadata_still_wins():
    s = _sense("past participle of accuser", form_of=[{"word": "accuser"}], tags=["form-of"])
    assert is_form_sense(s) and form_bases(s) == ["accuser"]
    assert form_bases(_sense("second-person plural present indicative/imperative of aimer")) \
        == ["aimer"]


def test_verb_pos_that_is_only_a_form_is_dropped_beside_a_real_pos():
    content = [_entry("adj", _sense("content, satisfied, pleased")),
               _entry("verb", _sense("third-person plural present/subjunctive of conter"))]
    assert inflection_only_pos(content) == {"verb"}
    beton = [_entry("noun", _sense("concrete", tags=["masculine"])),
             _entry("verb", _sense("only used in laisse béton"))]
    assert inflection_only_pos(beton) == {"verb"}
    # a whole-word form (aimez) keeps its only part of speech: it redirects instead
    assert inflection_only_pos([_entry(
        "verb", _sense("second-person plural present indicative/imperative of aimer"))]) == set()


def test_form_entry_shares_the_base_verbs_table():
    aimez = _entry("verb", _sense("second-person plural present indicative/imperative of aimer"))
    assert _form_entry_bases(aimez, "aimez") == ["aimer"]
    # a participle with a meaning of its own but no conjugation of its own
    permettant = _entry(
        "verb",
        _sense("present participle of permettre", form_of=[{"word": "permettre"}],
               tags=["form-of", "participle", "present"]),
        _sense("allowing, enabling", tags=["participle"]))
    assert _form_entry_bases(permettant, "permettant") == ["permettre"]
    # a past participle with agreement forms only (accusée, accusés) has no conjugation
    accuse = _entry(
        "verb",
        _sense("past participle of accuser", form_of=[{"word": "accuser"}],
               tags=["form-of", "participle", "past"]),
        _sense("marked, conspicuous", tags=["participle"]),
        forms=[{"form": "accusée", "tags": ["feminine"]},
               {"form": "accusés", "tags": ["masculine", "plural"]}])
    assert _form_entry_bases(accuse, "accusé") == ["accuser"]
    # a real verb with its own table shares nothing
    aimer = _entry("verb", _sense("to love"), forms=[
        {"form": "aime", "tags": ["first-person", "indicative", "present", "singular"]}])
    assert _form_entry_bases(aimer, "aimer") == []
    # ought: its 「past of owe」 is obsolete — owe's table is not ought's
    ought = _entry("verb", _sense("simple past of owe", form_of=[{"word": "owe"}],
                                  tags=["form-of", "obsolete"]),
                   _sense("Indicating duty or obligation."))
    assert _form_entry_bases(ought, "ought") == []
    # a dialect / old form (book as the Northern English past of bake)
    book = _entry("verb", _sense("simple past of bake", form_of=[{"word": "bake"}],
                                 tags=["form-of", "dialectal"]))
    assert _form_entry_bases(book, "book") == []
