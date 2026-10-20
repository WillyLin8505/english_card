"""問題回報 #16: a spelling's rarer parts of speech get their own CEFR."""

from app.app_pack import rank_usages


def lex(i, pos, senses, examples, cefr="A1", zipf=4.7):
    return {"id": i, "normalized": "tea", "lemma": "tea", "pos": pos, "status": "full",
            "cefr": cefr, "zipf": zipf, "senses": [{}] * senses, "examples": [{}] * examples}


def test_main_usage_keeps_its_level_and_rare_ones_are_marked():
    noun, verb, adj = lex(1, "noun", 10, 24), lex(2, "verb", 1, 0), lex(3, "adj", 1, 0)
    stub = {"id": 4, "normalized": "tea", "lemma": "tea", "pos": "noun", "status": "stub"}
    rank_usages([adj, verb, noun, stub])
    assert (noun["usage_rank"], noun["rare_usage"], noun["cefr"]) == (0, False, "A1")
    assert verb["rare_usage"] and adj["rare_usage"]
    assert verb["cefr"] == "C2" and verb["headword_cefr"] == "A1"
    assert verb["cefr_source"] == "frequency_estimate"
    assert "usage_rank" not in stub


def test_rare_usage_is_never_easier_than_the_main_one():
    noun, verb = lex(1, "noun", 3, 3, cefr="B2", zipf=6.0), lex(2, "verb", 3, 2, cefr="B2", zipf=6.0)
    rank_usages([noun, verb], {})
    assert verb["rare_usage"] and verb["cefr"] == "B2"


def test_a_single_usage_is_not_rare():
    only = lex(1, "noun", 2, 2)
    rank_usages([only])
    assert only["rare_usage"] is False and only["cefr"] == "A1"


def test_cefr_j_decides_the_main_parts_of_speech():
    """breeze is a noun (微風), not the verb 隨意行動 with more senses; bowl's
    verb is a listed usage of its own, not a rare one."""
    def l(i, word, pos, senses, examples, cefr="A1"):
        return {"id": i, "normalized": word, "lemma": word, "pos": pos, "status": "full",
                "cefr": cefr, "zipf": 4.5, "senses": [{}] * senses, "examples": [{}] * examples}
    breeze_v, breeze_n = l(1, "breeze", "verb", 5, 9), l(2, "breeze", "noun", 3, 4)
    bowl_n, bowl_v = l(3, "bowl", "noun", 4, 8), l(4, "bowl", "verb", 2, 1)
    railing_a, railing_n = l(5, "railing", "adj", 3, 2), l(6, "railing", "noun", 1, 0)
    rank_usages([breeze_v, breeze_n, bowl_n, bowl_v, railing_a, railing_n],
                {"breeze": {"noun": "A2"}, "bowl": {"noun": "A1", "verb": "B1"}})
    assert breeze_n["usage_rank"] == 0 and breeze_n["cefr"] == "A2"
    assert breeze_v["rare_usage"]
    assert not bowl_v["rare_usage"] and bowl_v["cefr"] == "B1" and bowl_v["cefr_source"] == "cefr-j"
    assert railing_n["usage_rank"] == 0 and railing_a["rare_usage"], "an -ing word not in the list: noun first"


def test_an_ed_word_not_in_the_list_is_the_adjective_before_the_verb():
    def l(i, pos, senses, examples):
        return {"id": i, "normalized": "potted", "lemma": "potted", "pos": pos, "status": "full",
                "cefr": "B1", "zipf": 3.0, "senses": [{}] * senses, "examples": [{}] * examples}
    verb, adj = l(1, "verb", 1, 9), l(2, "adj", 3, 1)
    rank_usages([verb, adj], {})
    assert adj["usage_rank"] == 0 and verb["rare_usage"]


def test_set_cefr_decision_never_makes_a_rare_usage_easier():
    """Card #397: #191's word-level set_cefr (bright A1) must not lift bright's
    rare verb from its share-based C1 back to A1."""
    from app import quality
    lxs = [{"id": 1, "cefr": "A1", "rare_usage": False}, {"id": 2, "cefr": "C1", "rare_usage": True},
           {"id": 3, "cefr": "B2", "rare_usage": True}]
    pack = {"lexemes": lxs}
    counts = quality.apply_decisions(pack, {"set_cefr": {"1": "A1", "2": "A1", "3": "C1"}})
    assert [x["cefr"] for x in lxs] == ["A1", "C1", "C1"]
    assert counts["set_cefr_rare_kept"] == 1


def test_compound_synonyms_move_to_related():
    from app.app_pack import move_compound_synonyms
    rel = lambda w, r="synonyms", h=False: {"relation": r, "word": w, "hide_by_default": h, "detail": {}}
    lx = {"status": "full", "lemma": "apple", "relations": [
        rel("orchard apple tree"), rel("pome"), rel("apple pie", "antonyms"), rel("apple tree", h=True)]}
    assert move_compound_synonyms({"lexemes": [lx]}) == 2
    assert [r["relation"] for r in lx["relations"]] == ["related", "synonyms", "related", "synonyms"]
