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


FINE = [{"pos": "adj", "lang_code": "fr", "word": "fine", "senses": [
            {"glosses": ["feminine singular of fin"], "tags": ["feminine", "form-of", "singular"],
             "form_of": [{"word": "fin"}]}]},
        {"pos": "noun", "lang_code": "fr", "word": "fine", "senses": [{"glosses": ["brandy"]}]}]


def test_gender_form_is_an_agreement_pos():
    assert kaikki.agreement_form_pos(FINE) == {"adj"}
    # la / une keep their article (問題回報 #1516 A): not dropped, not an agreement use
    assert kaikki.agreement_form_pos(LA) == set()
    assert kaikki.dropped_pos(LA) == set()
    alt =[{"pos": "adj", "word": "maire", "senses": [{"glosses": ["alternative form of maigre"],
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


def test_kept_article_gets_its_own_entry():
    # 問題回報 #1516 A: la the article is an entry with a learner gloss, first like le's
    k = kaikki.Kaikki()
    ctx = Context("fr", "en", "la")
    assert [c.value["pos"] for c in k.normalize("pos", LA, ctx)] == ["det", "pron", "noun"]
    det = [c for c in k.normalize("definition", LA, ctx) if c.value["pos"] == "det"]
    assert [c.value["gloss"] for c in det] == ["the (feminine singular definite article)"]
    assert det[0].confidence == 1.0


def test_article_sentence_binds_to_the_kept_article():
    article = "Florence est la ville la plus belle d'Italie."
    pronoun = "Où est Judith ? Je ne la vois pas."
    ctx = Context("fr", "en", "la", resolved={
        "definition": [{"pos": "det", "sense_key": "det"}, {"pos": "pron", "sense_key": "pron"},
                       {"pos": "noun", "sense_key": "noun"}],
        "example_sentences": [{"text": article, "key": "a"}, {"text": pronoun, "key": "p"}],
    })
    got = {c.value["example_key"]: c.value["sense_key"]
           for c in LocalCalc().normalize("example_sense", None, ctx)}
    assert got == {"a": "det", "p": "pron"}
