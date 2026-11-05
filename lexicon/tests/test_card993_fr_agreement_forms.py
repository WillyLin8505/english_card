"""Card 993 (問題回報 #1514): a sentence using la as le's article, or fine as
fin's adjective, gets no sense on the homograph that kept the headword."""
from app.adapters import kaikki
from app.adapters.base import Context
from app.adapters.local import LocalCalc, _fr_guess_pos, fr_agreement_use

LA = [{"pos": "article", "lang_code": "fr", "word": "la", "senses": [
          {"glosses": ["feminine of le: the"], "tags": ["feminine", "form-of", "singular"],
           "form_of": [{"word": "le"}]}]},
      {"pos": "pron", "lang_code": "fr", "word": "la", "senses": [{"glosses": ["her, it"]}]},
      {"pos": "noun", "lang_code": "fr", "word": "la", "senses": [{"glosses": ["the note A"]}]}]


def test_article_form_is_an_agreement_pos():
    assert kaikki.agreement_form_pos(LA) == {"det"}
    alt = [{"pos": "adj", "word": "maire", "senses": [{"glosses": ["alternative form of maigre"],
            "tags": ["alt-of", "alternative", "dialectal"], "alt_of": [{"word": "maigre"}]}]},
           {"pos": "noun", "word": "maire", "senses": [{"glosses": ["mayor"]}]}]
    assert kaikki.agreement_form_pos(alt) == set()


def test_clitic_before_la_is_the_pronoun():
    forms = frozenset({"la"})
    assert _fr_guess_pos("Je ne la vois pas.", forms, {"det", "pron"}) == "pron"
    assert _fr_guess_pos("J'aime la musique douce.", forms, {"det", "pron"}) == "det"


def test_article_sentence_is_left_unbound(monkeypatch):
    monkeypatch.setattr(kaikki, "fr_agreement_form_pos", lambda w: frozenset({"det"}))
    article = "Florence est la ville la plus belle d'Italie."
    pronoun = "Où est Judith ? Je ne la vois pas."
    assert fr_agreement_use(article, frozenset({"la"}), frozenset(), {"noun", "pron"}, {"det"})
    ctx = Context("fr", "en", "la", resolved={
        "definition": [{"pos": "pron", "sense_key": "pron"}, {"pos": "noun", "sense_key": "noun"}],
        "example_sentences": [{"text": article, "key": "a"}, {"text": pronoun, "key": "p"}],
    })
    got = {c.value["example_key"]: c.value["sense_key"]
           for c in LocalCalc().normalize("example_sense", None, ctx)}
    assert got == {"p": "pron"}


def test_adjective_form_after_etre():
    forms = frozenset({"fine"})
    assert fr_agreement_use("Cette veste est trop fine.", forms, frozenset(), {"noun"}, {"adj"})
    assert not fr_agreement_use("La fine est arrivée.", forms, frozenset(), {"noun"}, set())
