"""Card #429: French gender / number forms reach the App pack's nouns."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import app_pack  # noqa: E402
from app.adapters import kaikki  # noqa: E402


def _forms(by_lex):
    app_pack.share_forms(by_lex)
    return {i: [f["field"] for f in lex["forms"]] for i, lex in by_lex.items()}


def test_noun_keeps_plural_and_gender():
    got = _forms({1: {"normalized": "chat", "pos": "noun", "forms": [
        {"field": "fr_plural", "normalized": "chats"}, {"field": "fr_gender", "normalized": "m"}]}})
    assert sorted(got[1]) == ["fr_gender", "fr_plural"]


def test_noun_beside_adjective_shares_number_forms():
    got = _forms({1: {"normalized": "entier", "pos": "noun", "forms": []},
                  2: {"normalized": "entier", "pos": "adj",
                      "forms": [{"field": "fr_plural", "normalized": "entiers"}]}})
    assert got == {1: ["fr_plural"], 2: ["fr_plural"]}


def test_interjection_gets_no_noun_gender():
    got = _forms({1: {"normalized": "merci", "pos": "noun", "forms": [{"field": "fr_gender", "normalized": "m"}]},
                  2: {"normalized": "merci", "pos": "intj", "forms": []}})
    assert got[2] == []


def test_english_forms_unchanged():
    got = _forms({1: {"normalized": "book", "pos": "noun", "forms": [{"field": "noun_plural", "normalized": "books"}]},
                  2: {"normalized": "book", "pos": "verb", "forms": [{"field": "verb_past", "normalized": "booked"}]}})
    assert got == {1: ["noun_plural"], 2: ["verb_past"]}


def test_gender_of_homographs_is_the_main_entry():
    livre = [{"head_templates": [{"args": {"1": "m"}}]}, {"head_templates": [{"args": {"1": "f"}}]}]
    assert kaikki.fr_gender(livre) == "m"
    assert kaikki.fr_gender([{"head_templates": [{"args": {"1": "mfbysense"}}]}]) == "m/f"


def test_french_suffix_meaning_follows_the_word_pos(monkeypatch):
    idx = {"-ment": [{"lang_code": "fr", "word": "-ment", "pos": "suffix", "senses": [
        {"glosses": ["Attaches to an adjective to form the corresponding adverb."]}]},
        {"lang_code": "fr", "word": "-ment", "pos": "suffix", "senses": [
            {"glosses": ["forms nouns from verbs"]}]}],
        "lente": [{"lang_code": "fr", "word": "lente", "pos": "adj", "senses": [
            {"glosses": ["feminine of lent"], "form_of": [{"word": "lent"}]}]},
            {"lang_code": "fr", "word": "lente", "pos": "noun", "senses": [{"glosses": ["nit"]}]}],
        "lent": [{"lang_code": "fr", "word": "lent", "pos": "adj", "senses": [{"glosses": ["slow"]}]}]}
    monkeypatch.setattr(kaikki.kaikki_index, "lookup", lambda lang, w: idx.get(w))

    def bd():
        return {"parts": [{"part": "lente", "kind": "root", "meaning": None},
                          {"part": "-ment", "kind": "suffix", "meaning": "result, act"},
                          {"part": "re-", "kind": "prefix", "meaning": "again"}]}
    adv = kaikki._fr_part_meanings(bd(), "adv")["parts"]
    assert [p["meaning"] for p in adv] == ["slow", "Attaches to an adjective to form the corresponding adverb.", "again"]
    assert kaikki._fr_part_meanings(bd(), "noun")["parts"][1]["meaning"] == "forms nouns from verbs"


def test_other_tenses_and_auxiliary():
    tags = lambda *t: set(t)  # noqa: E731
    ff = lambda t: kaikki.form_field("verb", t, "fr")  # noqa: E731
    assert ff(tags("gerund", "participle", "present")) == "fr_present_participle"
    assert ff(tags("first-person", "imperfect", "indicative", "singular")) == "fr_imperfect_1s"
    assert ff(tags("first-person", "future", "indicative", "singular")) == "fr_future_1s"
    assert ff(tags("future", "indicative", "multiword-construction", "perfect")) is None
    assert ff(tags("gerund", "multiword-construction", "participle", "present")) is None
    entry = {"forms": [{"form": "être + past participle", "tags": ["infinitive", "multiword-construction"]},
                       {"form": "avoir + past participle", "tags": ["infinitive", "multiword-construction"]}]}
    assert kaikki.fr_auxiliaries([entry]) == ["être", "avoir"]


def test_pronominal_forms_and_auxiliary_are_not_own_forms():
    from app import catalog
    for form in ("m'acquiers", "s'acquérant", "se douche", "nous en sommes"):
        assert kaikki.FR_ELIDED.match(form)
    assert not kaikki.FR_ELIDED.match("acquiers")
    assert "fr_auxiliary" in catalog.FORM_FIELDS and "fr_auxiliary" not in catalog.INFLECTION_FIELDS
