from app.adapters.local import LocalCalc, _usage_pos_fr
from app.adapters.base import Context


def test_repeated_headword_is_not_noun_evidence():
    sentence = "Est-ce que ce sont vos livres ? Non, ce ne sont pas mes livres."
    assert _usage_pos_fr(sentence, frozenset({"ce"}), frozenset()) is None
    ctx = Context("fr", "en", "ce", resolved={
        "definition": [{"pos": p, "sense_key": p} for p in ["noun", "det", "pron"]],
        "example_sentences": [{"text": sentence, "key": "ex"}],
    })
    result = LocalCalc().normalize("example_sense", None, ctx)
    assert result[0].value["sense_key"] == "pron"


def test_independent_determiner_still_identifies_noun():
    assert _usage_pos_fr("Le livre est ici.", frozenset({"livre"}), frozenset()) == "noun"
