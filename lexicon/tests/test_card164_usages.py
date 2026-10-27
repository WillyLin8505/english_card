"""Card #164: main usage by dictionary votes, photo tags by photo context."""

from app import quality as q
from app.app_pack import rank_usages


def _lx(i, word, pos, senses, examples=0, **extra):
    # Examples hang on the entry's senses, as in the pack (a dated sense's
    # examples weigh as little as the sense itself).
    exs = [{"sense_id": senses[k % len(senses)]["id"]} for k in range(examples)] if senses else []
    return {"id": i, "normalized": word, "lemma": word, "pos": pos, "status": "full",
            "cefr": "B2", "zipf": 3.5, "senses": senses, "examples": exs, **extra}


def _senses(n, labels=()):
    return [{"id": 100 + k, "native": "x", "labels": list(labels)} for k in range(n)]


def test_dictionaries_outvote_wiktionary_coverage():
    """archaic / vulgar: Wiktionary documents a noun at length, but neither
    WordNet nor ECDICT has one at all — the adjective is the main usage."""
    noun, adj = _lx(1, "archaic", "noun", _senses(6), 12), _lx(2, "archaic", "adj", _senses(2), 2)
    rank_usages([noun, adj], {}, pos_votes=lambda w: (2, {"adj": 2}))
    assert adj["usage_rank"] == 0 and noun["rare_usage"]


def test_one_dictionary_gap_does_not_flip_a_word():
    """backlight: only ECDICT knows the word and lists just the verb; one
    source is not enough to overrule the evidence (noun 背光)."""
    noun, verb = _lx(1, "backlight", "noun", _senses(5), 8), _lx(2, "backlight", "verb", _senses(2), 1)
    rank_usages([noun, verb], {}, pos_votes=lambda w: (1, {"verb": 1}))
    assert noun["usage_rank"] == 0


def test_tie_falls_back_to_weighted_evidence_and_the_list_still_wins():
    frail_n = _lx(1, "frail", "noun", _senses(6, ["dated"]), 12)
    frail_a = _lx(2, "frail", "adj", _senses(5), 5)
    breeze_v, breeze_n = _lx(3, "breeze", "verb", _senses(5), 9), _lx(4, "breeze", "noun", _senses(3), 4)
    rank_usages([frail_n, frail_a, breeze_v, breeze_n], {"breeze": {"noun": "A2"}},
                pos_votes=lambda w: (2, {"noun": 2, "adj": 2, "verb": 2}))
    assert frail_a["usage_rank"] == 0 and frail_n["rare_usage"]
    assert breeze_n["usage_rank"] == 0 and breeze_v["rare_usage"]


def test_a_broken_vote_source_is_neutral():
    def boom(w):
        raise RuntimeError("no wordnet")
    noun, verb = _lx(1, "tea", "noun", _senses(4), 6), _lx(2, "tea", "verb", _senses(1), 0)
    rank_usages([noun, verb], {}, pos_votes=boom)
    assert noun["usage_rank"] == 0 and verb["rare_usage"]


def test_etymology_senses_stay_main_when_the_rest_is_obsolete():
    """monogram: the only non-etymology sense is obsolete; 花押字 under
    etymology-3 is the meaning the card shows."""
    senses = [{"id": 1, "native": "輪廓素描", "labels": ["obsolete"]},
              {"id": 2, "native": "短詩", "labels": ["obsolete", "rare", "etymology-2"]},
              {"id": 3, "native": "花押字", "labels": ["etymology-3"]}]
    ranked = q.rank_senses(senses)
    assert ranked[0]["id"] == 3 and ranked[0]["priority"] == "main"
    assert {s["id"] for s in ranked if s["priority"] == "low"} == {1, 2}


def test_etymology_senses_are_still_demoted_next_to_a_plain_main_sense():
    senses = [{"id": 1, "native": "電話", "labels": []},
              {"id": 2, "native": "語音", "labels": ["etymology-2"]}]
    ranked = q.rank_senses(senses)
    assert [s["priority"] for s in ranked] == ["main", "low"]


def test_chinese_senses_stay_main_when_no_main_sense_has_chinese():
    """stanch: the only translated sense is tagged poetic; the card must
    still show 使止血 rather than an untranslated sense."""
    senses = [{"id": 1, "native": "使止血", "labels": ["poetic", "etymology-2"]},
              {"id": 2, "native": None, "labels": ["etymology-2"]},
              {"id": 3, "native": "", "labels": ["transitive", "etymology-2"]}]
    ranked = q.rank_senses(senses)
    assert ranked[0]["id"] == 1 and ranked[0]["priority"] == "main"
    assert "low_priority" not in ranked[0]["labels"]
    # A reviewed demotion (overrides.json) is never undone by this.
    senses = [{"id": 1, "native": "使止血", "labels": ["poetic"]}, {"id": 2, "native": "", "labels": []}]
    assert q.rank_senses(senses, {"1"})[-1]["id"] == 1


def _pack_with_photo():
    glass = {"id": 10, "normalized": "glass", "lemma": "glass", "pos": "noun", "status": "full",
             "usage_rank": 0, "senses": [
                 {"id": 100, "native": "玻璃", "priority": "main",
                  "definition": "A hard transparent material made from sand."},
                 {"id": 101, "native": "玻璃杯", "priority": "main",
                  "definition": "A drinking vessel made of glass, a cup for water or wine."},
                 {"id": 102, "native": "飲用容器", "priority": "low", "definition": "A drinking vessel."}]}
    brick_n = {"id": 20, "normalized": "brick", "lemma": "brick", "pos": "noun", "status": "full",
               "usage_rank": 0, "senses": [{"id": 200, "native": "磚", "priority": "main",
                                            "definition": "A block of clay used for building walls."}]}
    brick_a = {"id": 21, "normalized": "brick", "lemma": "brick", "pos": "adj", "status": "full",
               "usage_rank": 1, "senses": [{"id": 210, "native": "極冷", "priority": "low",
                                            "definition": "Very cold.", "labels": ["colloquial"]}]}
    image = {"id": 7, "tags": [{"lexeme_id": 10, "sense_id": 102}, {"lexeme_id": 21, "sense_id": 210}],
             "labels": [{"word": "glass", "pos": "noun", "lexeme_id": 10},
                        {"word": "brick", "pos": "adj", "lexeme_id": 21}]}
    return {"lexemes": [glass, brick_n, brick_a], "redirects": {}, "catalog_images": [image]}


def test_fix_catalog_senses_picks_by_photo_context_not_first_sense():
    pack = _pack_with_photo()
    pack["catalog_images"][0]["tags"].append({"lexeme_id": 30, "sense_id": 300})
    pack["lexemes"].append({"id": 30, "normalized": "wine", "lemma": "wine", "pos": "noun", "status": "full",
                            "senses": [{"id": 300, "native": "酒", "priority": "main", "definition": "Drink."}]})
    assert q.fix_catalog_senses(pack) == 2
    tags = pack["catalog_images"][0]["tags"]
    assert tags[0]["sense_id"] == 101 and tags[0]["sense_id_before"] == 102  # 玻璃杯 next to wine


def test_fix_catalog_senses_moves_a_tag_to_the_sister_part_of_speech():
    pack = _pack_with_photo()
    q.fix_catalog_senses(pack)
    im = pack["catalog_images"][0]
    brick = im["tags"][1]
    assert brick["lexeme_id"] == 20 and brick["lexeme_id_before"] == 21
    assert brick["sense_id"] == 200 and brick["sense_id_before"] == 210 and brick["sense_fallback"]
    assert im["labels"][1] == {"word": "brick", "pos": "noun", "lexeme_id": 20, "sense_id": 200}
    assert q.fix_catalog_senses(pack) == 0  # idempotent


def test_fix_catalog_senses_does_not_double_tag_a_sister_already_on_the_photo():
    pack = _pack_with_photo()
    im = pack["catalog_images"][0]
    im["tags"].append({"lexeme_id": 20, "sense_id": 200})
    q.fix_catalog_senses(pack)
    brick_adj = im["tags"][1]
    assert brick_adj["lexeme_id"] == 21 and brick_adj["sense_id"] == 210  # left for review
    assert sum(1 for t in im["tags"] if t["lexeme_id"] == 20) == 1


def test_dictionaries_outrank_the_participle_rule():
    """underlying: an adjective to WordNet and ECDICT; Wiktionary alone has a
    noun. The -ing rule (noun before adjective) applies only when the
    dictionaries do not separate them (railing)."""
    adj, noun, verb = (_lx(1, "underlying", "adj", _senses(3), 15), _lx(2, "underlying", "noun", _senses(1)),
                       _lx(3, "underlying", "verb", _senses(2)))
    rank_usages([adj, noun, verb], {}, pos_votes=lambda w: (2, {"adj": 2, "verb": 1}))
    assert adj["usage_rank"] == 0 and noun["rare_usage"] and verb["usage_rank"] == 2
    rail_a, rail_n = _lx(4, "railing", "adj", _senses(3), 2), _lx(5, "railing", "noun", _senses(1))
    rank_usages([rail_a, rail_n], {}, pos_votes=lambda w: (0, {}))
    assert rail_n["usage_rank"] == 0


def test_register_senses_come_back_before_other_etymologies():
    """meth: the dictionary's informal 冰毒 is the meaning; the clean sense
    under etymology-4 (梅酒) is another word."""
    senses = [{"id": 1, "native": "冰毒", "labels": ["informal"]},
              {"id": 2, "native": "美沙酮", "native_ai": True, "labels": ["informal", "etymology-2"]},
              {"id": 3, "native": "流浪漢", "native_ai": True, "labels": ["derogatory", "etymology-3"]},
              {"id": 4, "native": "梅酒", "native_ai": True, "labels": ["etymology-4"]}]
    ranked = q.rank_senses(senses)
    assert ranked[0]["id"] == 1 and ranked[0]["priority"] == "main"
    assert [s["id"] for s in ranked if s["priority"] == "low"] == [2, 3, 4]


def test_last_resort_keeps_a_chinese_sense_main():
    senses = [{"id": 1, "native": "", "labels": []},
              {"id": 2, "native": "古義", "labels": ["obsolete"]}]
    ranked = q.rank_senses(senses)
    assert ranked[0]["id"] == 1 and ranked[1]["priority"] == "main"


def test_offensive_senses_never_become_the_meaning():
    """chimp: the only translated sense is the offensive one — show nothing
    rather than that; moron's derogatory 白痴 is the word's meaning."""
    senses = [{"id": 1, "native": "", "labels": []}, {"id": 2, "native": "黑人", "labels": ["offensive", "vulgar"]}]
    assert [s["priority"] for s in q.rank_senses(senses)] == ["main", "low"]
    # … and when nothing is main, the offensive sense is at least not the first one shown.
    senses = [{"id": 2, "native": "黑人", "labels": ["offensive"]}, {"id": 1, "native": "", "labels": ["obsolete"]}]
    assert [s["id"] for s in q.rank_senses(senses)] == [1, 2]
    senses = [{"id": 1, "native": "白痴", "labels": ["derogatory"]},
              {"id": 2, "native": "假想粒子", "native_ai": True, "labels": ["etymology-2"]}]
    assert q.rank_senses(senses)[0]["id"] == 1
