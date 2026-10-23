"""Card #536 (問題回報 #575): a French verb form after a determiner is a noun, another word."""
from app.adapters.local import _usage_pos_fr

MASQUER = {"masquer", "masque", "masques", "masquons", "masquez", "masquent", "masqué", "masquant"}
PLACER = {"placer", "place", "places", "plaçons", "placez", "placent", "placé", "plaçant"}
STOPPER = {"stopper", "stoppe", "stoppes", "stoppons", "stoppez", "stoppent", "stoppé"}


def test_noun_after_determiner_is_another_word():
    for t in ("Est-ce que je peux avoir un masque ?", "Je mets mon masque.",
              "Ziri a un bon masque anti-poussière.", "Les masqués sont là."):
        assert _usage_pos_fr(t, MASQUER, frozenset(MASQUER - {"masquer"})) == "other", t
    for t in ("À la place de Tom.", "La place est vide.", "Il n'y a pas de place."):
        assert _usage_pos_fr(t, PLACER, frozenset(PLACER - {"placer"})) == "other", t


def test_object_pronoun_and_verb_uses_stay():
    only = frozenset(MASQUER - {"masquer"})
    for t in ("Chacun est masqué.", "Il masque sa peur.", "Il le masque bien."):
        assert _usage_pos_fr(t, MASQUER, only) == "verb", t
    assert _usage_pos_fr("Je la place ici.", PLACER, frozenset(PLACER - {"placer"})) == "verb"
    # the infinitive is this word even beside the noun
    assert _usage_pos_fr("Il cherche la place pour placer sa voiture.", PLACER,
                         frozenset(PLACER - {"placer"})) != "other"


LIVRER = {"livrer", "livre", "livres", "livrons", "livrez", "livrent", "livré", "livrant"}


def test_adverb_and_partitive_before_the_adjective():
    only = frozenset(LIVRER - {"livrer"})
    for t in ("C'est un très petit livre.", "De nombreux livres furent volés.",
              "Tu as de nombreux livres.", "Il a d'autres livres."):
        assert _usage_pos_fr(t, LIVRER, only) == "other", t
    for t in ("Il livre de nouveau.", "Le paquet a été livré hier.", "On le livre très vite."):
        assert _usage_pos_fr(t, LIVRER, only) == "verb", t


def test_pronoun_before_a_form_that_is_no_noun():
    only = frozenset(STOPPER - {"stopper"})
    assert _usage_pos_fr("Comment le stoppons-nous ?", STOPPER, only) == "verb"
    assert _usage_pos_fr("Je ne veux pas que quelqu'un stoppe ça.", STOPPER, only) == "verb"


def test_second_sentence_and_quelque():
    only = frozenset(LIVRER - {"livrer"})
    for t in ("Mon oncle m'a donné un livre hier. Voici le livre.",
              "Quelque livre que tu lises, lis-le avec attention."):
        assert _usage_pos_fr(t, LIVRER, only) == "other", t
    assert _usage_pos_fr("Hier, Marie la place ici.", PLACER, frozenset(PLACER - {"placer"})) != "other"
