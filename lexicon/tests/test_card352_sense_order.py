"""Card #352 / 問題回報 #350: senses ordered by current use, not Kaikki's
historical order; label terms from a long gloss's head."""
import pytest

from app import sense_order
from app.images import english_label_terms, english_search_term
from app.sense_order import is_out_of_use, order_senses, sense_rank


def _item(gloss, labels=(), topics=None, pos="noun", confidence=1.0):
    return {"pos": pos, "gloss": gloss, "labels": list(labels), "topics": topics,
            "confidence": confidence, "source": "kaikki", "sense_key": gloss[:12]}


@pytest.fixture
def no_index(monkeypatch):
    """No Kaikki index in tests: topics come from the item, English
    Wiktionary confirms a fixed table."""
    table = {("plate", "noun", "fr", "assiette"): True, ("dish", "noun", "fr", "assiette"): True,
             ("seat", "noun", "fr", "assiette"): False, ("trim", "noun", "fr", "assiette"): False,
             ("basis", "noun", "fr", "assiette"): False, ("situation", "noun", "fr", "assiette"): False,
             ("face", "noun", "fr", "face"): True, ("optics", "noun", "fr", "optique"): None,
             ("view", "noun", "fr", "optique"): False}
    monkeypatch.setattr(sense_order, "english_translates_to", lambda e, p, t, l: table.get((e, p, t, l)))
    monkeypatch.setattr(sense_order, "topics_of", lambda *a: ())
    monkeypatch.setattr(sense_order, "tags_of", lambda *a: ())
    sense_order.english_translates_to.cache_clear = lambda: None


def test_assiette_plate_and_dish_come_first(no_index):
    items = [_item("manner of being seated, situation", labels=["archaic"], confidence=0.5),
             _item("seat", topics=["horse-racing", "sports"]),
             _item("trim, attitude, pitch attitude", topics=["nautical"]),
             _item("basis", topics=["accounting", "finance"]),
             _item("dish (the food)"), _item("plate, dish (the crockery)"), _item("plateful")]
    ordered = [i["gloss"] for i in order_senses(items, "fr", "assiette")]
    assert ordered[:3] == ["dish (the food)", "plate, dish (the crockery)", "plateful"]
    assert ordered[3:6] == ["seat", "trim, attitude, pitch attitude", "basis"]  # stable
    assert ordered[-1] == "manner of being seated, situation"


def test_confirmed_domain_sense_stays_first(no_index):
    items = [_item("face", topics=["anatomy"]), _item("surface, side")]
    assert [i["gloss"] for i in order_senses(items, "fr", "face")] == ["face", "surface, side"]


def test_unknown_evidence_does_not_demote(no_index):
    items = [_item("optics", topics=["physics"]), _item("point of view, perspective")]
    assert sense_rank(items[0], "fr", "optique") == 0


def test_cognate_gloss_is_its_own_evidence(no_index):
    assert sense_rank(_item("party", topics=["politics"]), "fr", "parti") == 0
    assert sense_rank(_item("scenario", topics=["film"]), "fr", "scénario") == 0


def test_register_labels_do_not_demote(no_index):
    kid, testicle = _item("child, kid", labels=["informal"]), _item("testicle", labels=["Quebec"])
    assert [i["gloss"] for i in order_senses([kid, testicle], "fr", "gosse")] == ["child, kid", "testicle"]
    assert not is_out_of_use(kid)
    assert is_out_of_use(_item("x", labels=["dated"]))
    assert is_out_of_use(_item("x", labels=["vulgar"]))
    assert is_out_of_use(_item("x", confidence=0.5))  # dialectal etc. kept only as low confidence


def test_english_gets_only_the_out_of_use_rule(no_index):
    items = [_item("A boundary; a border.", labels=["obsolete"]), _item("A pattern", topics=["textiles"]),
             _item("A grade")]
    assert [i["gloss"] for i in order_senses(items, "en", "mark")] == ["A pattern", "A grade", "A boundary; a border."]


def test_long_gloss_head_is_a_label_term():
    assert english_label_terms("skin of a person or animal") == ["skin"]
    assert english_search_term("skin of a person or animal") == "skin"
    assert english_label_terms("room in a house or flat") == ["room"]
    # generic heads and other long glosses stay out
    assert english_label_terms("kind of political system; regimen") == ["regimen"]
    assert english_label_terms("a person who is welcomed") == []
    assert english_label_terms("plate, dish (the crockery)") == ["plate", "dish"]
