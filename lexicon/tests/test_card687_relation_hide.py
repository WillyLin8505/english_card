"""Card 687 / 問題回報 #561: related / hyponyms / hypernyms follow the same meaning rule as synonyms."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.app_pack import hide_minor_sense_synonyms  # noqa: E402


def lex(senses, relations):
    return {"id": 1, "lemma": "can", "status": "full",
            "senses": [{"id": 100 + n} for n in range(senses)], "relations": relations}


def rel(relation, word, sense_id, match=None):
    detail = {"sense_match": match} if match else {}
    return {"relation": relation, "word": word, "sense_id": sense_id, "hide_by_default": False, "detail": detail}


def test_minor_sense_related_word_is_hidden_and_main_sense_kept():
    pack = {"lexemes": [lex(5, [rel("related", "butt", 104), rel("related", "room", 100),
                                rel("hyponyms", "beer can", 101, "qwen")])]}
    assert hide_minor_sense_synonyms(pack) == 1
    related_butt, related_room, hypo = pack["lexemes"][0]["relations"]
    assert related_butt["hide_by_default"] and related_butt["detail"]["hidden_reason"] == "minor_sense"
    assert not related_room["hide_by_default"]
    assert not hypo["hide_by_default"]


def test_no_sense_match_hides_hypernym_and_unknown_sense_stays_shown():
    pack = {"lexemes": [lex(2, [rel("hypernyms", "container", None, "none"),
                                rel("related", "facility", None)])]}
    assert hide_minor_sense_synonyms(pack) == 1
    hyper, unknown = pack["lexemes"][0]["relations"]
    assert hyper["hide_by_default"] and hyper["detail"]["hidden_reason"] == "no_sense"
    assert not unknown["hide_by_default"]
