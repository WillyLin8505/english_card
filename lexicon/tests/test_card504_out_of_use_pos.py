"""卡 #504（問題回報 #512）: a part of speech whose every meaning is obsolete / archaic,
beside a current one, gets no entry (hier/verb, rich/verb, among/adv)."""

from __future__ import annotations

from app.adapters.kaikki import dropped_pos, inflection_only_pos, out_of_use_pos


def _entry(pos, *senses):
    return {"word": "x", "pos": pos, "senses": list(senses)}


def _sense(gloss, *tags, **kw):
    return {"glosses": [gloss], "tags": list(tags), **kw}


def test_old_part_of_speech_beside_a_current_one_is_dropped():
    hier = [_entry("adv", _sense("yesterday")),
            _entry("verb", _sense("to stamp with a rod (hie)", "obsolete"))]
    assert out_of_use_pos(hier) == {"verb"}
    rich = [_entry("adj", _sense("Wealthy")),
            _entry("verb", _sense("To enrich.", "obsolete", "transitive"),
                   _sense("To become rich.", "intransitive", "archaic")),
            _entry("name", _sense("A surname."))]
    assert out_of_use_pos(rich) == {"verb"}
    assert dropped_pos(rich) == {"verb"}


def test_one_current_meaning_keeps_the_part_of_speech():
    strange = [_entry("adj", _sense("Not normal"), _sense("foreign", "obsolete")),
               _entry("noun", _sense("A strange quark.", "countable"))]
    assert out_of_use_pos(strange) == set()
    # dated / rare are not out of use
    assert out_of_use_pos([_entry("adj", _sense("big")),
                           _entry("noun", _sense("a thing", "dated"))]) == set()


def test_word_with_only_old_meanings_keeps_them():
    assert out_of_use_pos([_entry("verb", _sense("to be", "obsolete")),
                           _entry("noun", _sense("being", "archaic"))]) == set()


def test_current_form_is_not_out_of_use():
    # dried the verb is dry's past (問題回報 #51's rule, app_pack card_form), not an old word
    dried = [_entry("adj", _sense("Having been dried")),
             _entry("verb", _sense("simple past and past participle of dry", form_of=[{"word": "dry"}]))]
    assert out_of_use_pos(dried) == set()
    # an obsolete form beside a current meaning goes either way
    ought = [_entry("verb", _sense("Indicating duty"),
                    _sense("simple past of owe", "obsolete", form_of=[{"word": "owe"}]))]
    assert out_of_use_pos(ought) == set()
    assert inflection_only_pos(ought) == set()
