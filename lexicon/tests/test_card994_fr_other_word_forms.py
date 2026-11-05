"""Card 994 (問題回報 #1515): a sentence that uses a French headword as another
word's form (fins = fin, je vous présente = présenter, qu'elle vive = vivre,
une fine couche = fin) gets no sense on the homograph."""
from app.adapters.local import fr_agreement_use


def use(text, forms, own, form_pos, lemma):
    return fr_agreement_use(text, frozenset(forms), frozenset(), set(own), set(form_pos), lemma)


FINE = ({"fine", "fines", "fins"}, {"noun"}, {"adj"}, "fine")
VIVE = ({"vive", "vives", "vifs"}, {"noun"}, {"adj", "verb"}, "vive")
PRES = ({"présente", "présentes", "présents"}, {"noun"}, {"adj", "verb"}, "présente")


def test_plural_of_another_word():
    assert use("J'adore les fins heureuses.", *FINE)
    assert use("Beaucoup d'étudiants furent présents au cours.", *PRES)


def test_adjective_next_to_a_noun():
    assert use("Cette pizza a une croûte fine.", *FINE)
    assert use("Il traverse une fine couche de glace.", *FINE)
    assert not use("La fine est un alcool.", *FINE)


def test_finite_verb_of_the_other_word():
    assert use("Je vous présente mes excuses.", *PRES)
    assert use("Il semble qu'il vive en Angleterre.", *VIVE)
    assert use("Vive la république !", *VIVE)
    assert not use("La vive du port est un poisson.", *VIVE)


def test_inversion_and_object_pronoun_are_not_the_verb():
    assert not use("Où es-tu allée ?", {"allée", "allées"}, {"noun"}, {"verb"}, "allée")
    assert not use("Je lui ai donné un livre.", {"lui"}, {"pron"}, {"verb"}, "lui")
