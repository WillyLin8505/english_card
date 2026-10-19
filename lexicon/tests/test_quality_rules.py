"""Quality rules (docs/LEXICON_QUALITY_RULES.md, 問題回報 #182–#186). Unit tests only."""

from app import quality as q

CEFR = {"tear": [4.3, {"noun": "A2", "verb": "B1"}, None], "flee": [3.8, {"verb": "B2"}, None],
        "window": [4.8, {"noun": "A1"}, None], "grass": [4.4, {"noun": "A1"}, None],
        "laptop": [4.2, {"noun": "B2"}, None], "light": [5.3, {"adj.": "A1", "noun": "A1"}, None]}


def k(pos, *senses):
    return {"pos": pos, "senses": list(senses)}


def form(base, *tags):
    return {"form_of": [{"word": base}], "tags": ["form-of", *tags]}


def test_person_name_flagged_but_word_with_common_sense_kept():
    chen = [k("noun", {"tags": ["offensive", "slur"]}), k("name", {})]
    assert "person_name" in q.inclusion_flags("chen", "unknown", chen, CEFR)
    jane = [k("name", {}), k("noun", {"tags": []})]
    assert "person_name" not in q.inclusion_flags("jane", "unknown", jane, CEFR)


def test_gloss_fallback_and_pos_scoped_list():
    """#213/#217: a tag-less gloss is still a form. #162: a level listed for
    another pos does not keep a pure inflection, and a mixed pos is not redirected."""
    scored = [k("verb", {"tags": [], "glosses": ["simple past and past participle of score"]})]
    assert q.inflection_base("scored", "verb", scored, {"score": [5, {"verb": "B1"}, None]}) == "score"
    based = [k("adj", {"tags": [], "glosses": [
        "simple past and past participle of base", "Being derived from something"]})]
    assert q.inflection_base("based", "adj", based, {}) is None
    attached = [
        k("adj", {"tags": [], "glosses": ["Fond of someone."]}),
        k("verb", form("attach", "past", "participle")),
    ]
    listed = {"attached": [4.0, {"adj.": "B2"}, None], "attach": [4.5, {"verb": "A2"}, None]}
    assert q.inflection_base("attached", "verb", attached, listed) == "attach"
    assert q.inflection_base("attached", "adj", attached, listed) is None
    shove = [k("verb", {"tags": [], "glosses": ["To push roughly."]}, form("shave", "past"))]
    assert q.inflection_base("shove", "verb", shove, {"shave": [4, {"verb": "A2"}, None]}) is None
    beans = [k("noun", form("coffee bean", "plural"))]
    assert q.inclusion_flags("coffee beans", "noun", beans, {})["inflected_form"] == "coffee bean"
    phrase = [k("verb", form("fool around", "gerund", "participle"))]
    assert q.inclusion_flags("fooling around", "verb", phrase, {})["inflected_form"] == "fool around"


def test_inflected_forms_point_to_their_lemma():
    tore = [k("adj", {"tags": ["obsolete"]}), k("verb", form("tear", "past")),
            k("noun", {"alt_of": [{"word": "torus"}], "tags": ["alt-of"]})]
    assert q.inclusion_flags("tore", "unknown", tore, CEFR)["inflected_form"] == "tear"
    fleeing = [k("verb", form("flee", "gerund", "participle")), k("noun", {"tags": []})]
    assert q.inclusion_flags("fleeing", "unknown", fleeing, CEFR)["inflected_form"] == "flee"
    tenants = [k("noun", form("tenant", "plural"))]
    assert q.inclusion_flags("tenants", "unknown", tenants, CEFR)["inflected_form"] == "tenant"
    empress = [k("noun", {"form_of": [{"word": "emperor"}], "tags": ["feminine"]})]
    assert "inflected_form" not in q.inclusion_flags("empress", "noun", empress, CEFR)


def test_fragments_brands_and_abbreviations():
    assert "phrase_fragment" in q.inclusion_flags("contain her", "unknown", [], CEFR)
    assert "proper_or_brand" in q.inclusion_flags("V-8 juice", "noun", [], CEFR)
    assert "proper_or_brand" in q.inclusion_flags("South China Sea", "noun", [], CEFR)
    bq = q.inclusion_flags("BQ", "name", [k("noun", {"tags": ["abbreviation", "initialism"]})], CEFR)
    assert {"abbreviation", "proper_or_brand"} <= set(bq)
    win = [k("noun", form("window", "plural")), k("name", {"tags": []})]
    assert {"proper_or_brand", "inflected_form"} <= set(q.inclusion_flags("Windows", "noun", win, CEFR))
    assert q.inclusion_flags("window", "noun", [k("noun", {"tags": []})], CEFR) == {}


def test_cefr_rules():
    assert q.cefr_flags("laptop", "noun", "C1", 4.2, CEFR) == {"cefr_above_list": "B2"}
    assert q.cefr_flags("laptop", "noun", "B2", 4.2, CEFR) == {}
    assert "common_word_too_hard" in q.cefr_flags("grassy", "adj", "C1", 3.2, CEFR)
    assert q.cefr_flags("make light of", "verb", "A1", None, CEFR) == {"idiom_too_easy": "B2"}
    assert q.cefr_flags("make light of", "verb", "B2", None, CEFR) == {}
    assert q.cefr_flags("rose garden", "noun", "A2", None, CEFR) == {}


def test_senses_ranked_low_priority_after_main():
    senses = [{"id": 1, "native": "陡", "native_ai": False, "labels": []},
              {"id": 2, "native": "昂貴的", "native_ai": True, "labels": ["informal"]},
              {"id": 3, "native": "化學燒瓶上部", "native_ai": True, "labels": []},
              {"id": 4, "native": "陡坡的", "native_ai": False, "labels": []}]
    ranked = q.rank_senses(senses)
    assert [s["id"] for s in ranked] == [1, 4, 2, 3]
    assert ranked[2]["priority"] == "low" and "low_priority" in ranked[2]["labels"]
    # Reviewed override: a dictionary sense can be demoted by id.
    assert q.rank_senses([{"id": 9, "native": "x", "labels": []}], {"9"})[0]["priority"] == "low"


def test_example_validator():
    assert q.example_flags("The door is hinged on the left.", "hinged", "adj") == []
    assert "pos_mismatch" in q.example_flags(
        "The love was conditional; it hinged on my finances.", "hinged", "adj")
    assert "not_sentence" in q.example_flags("a scarlet woman", "scarlet", "adj")
    assert "missing_lemma" in q.example_flags("The cat sat on the mat.", "dog", "noun")
    assert q.example_flags("She tore the letter in half.", "tear", "verb", ["tore"]) == []
    assert "odd_name" in q.example_flags("Ziri planted heathers in clusters.", "cluster", "noun")
    assert q.example_flags("The cities are growing.", "city", "noun") == []
    assert q.example_is_charged(
        "Outlawing migration is like outlawing going to the bathroom.", "outlaw") == "politics"
    assert q.example_is_charged('Will the word "woman" be outlawed?', "outlaw") == "politics"
    assert q.example_is_charged(
        "Modern man has moved far away from God and from nature.", "move") == "religion"
    assert "charged" in q.example_flags(
        "Don't kill the part of you that is cringe.", "cringe", "verb")
    assert q.example_is_charged("They found the outlaw's tracks near the river.", "outlaw") is None
    assert q.example_is_charged("The church is on the corner.", "church") is None
    assert q.example_is_charged("Oh my God, I forgot my keys.", "forget") is None
    assert q.example_is_charged("Ziri checked the stability of the balcony railing.", "balcony") is None
    ranked = q.rank_examples(
        [{"id": 1, "text": "She fired her last bullet at the outlaw."},
         {"id": 2, "text": "He tracked the outlaw through the canyon."}],
        "outlaw", "noun", ["outlaw"], set())
    assert ranked[0]["text"].startswith("He tracked")
    assert q.example_reject_reason("kinetic kill vehicle", "vehicle", "noun") == "不是完整句"
    assert q.example_preference("Ziri drove the vehicle home.") > q.example_preference(
        "She parked the vehicle outside.")
    senses = [{"sense_key": "fruit", "gloss": "a sweet food you can eat", "ordinal": 0, "labels": []},
              {"sense_key": "tree", "gloss": "a tall woody plant", "ordinal": 1, "labels": []}]
    assert q.bind_example_sense("She ate the sweet food.", senses)["sense_key"] == "fruit"
    assert q.bind_example_sense("The door is red.", senses) is None
    only = [{"sense_key": "main", "gloss": "something else", "ordinal": 0, "labels": []}]
    assert q.bind_example_sense("The door is red.", only)["sense_key"] == "main"


def test_apply_pack_orders_and_attaches():
    pack = {"lexemes": [
        {"id": 1, "lemma": "hinged", "normalized": "hinged", "pos": "adj", "status": "full",
         "forms": [], "senses": [{"id": 10, "native": "以鉸鏈固定的", "labels": []},
                                 {"id": 11, "native": "嗑藥", "labels": ["slang"]}],
         "examples": [{"id": 5, "text": "It hinged on my finances.", "sense_id": 10}]},
        {"id": 2, "lemma": "chen", "normalized": "chen", "pos": "unknown", "status": "stub"}]}
    q.apply_pack(pack, {"chen|unknown": {"person_name": "人名"}},
                 {"examples": {"hinged|adj": [{"id": None, "text": "The box has a hinged lid.",
                                                "sense_id": 10, "source": "qwen"}]},
                  "rejected_examples": [5]})
    hinged, chen = pack["lexemes"]
    assert hinged["examples"][0]["text"] == "The box has a hinged lid."
    assert "rejected" in hinged["examples"][-1]["quality_flags"]
    assert hinged["senses"][1]["priority"] == "low"
    assert chen["quality_flags"] == {"person_name": "人名"}

def test_bind_example_sense_ex_reports_evidence():
    senses = [{"sense_key": "main", "gloss": "touch with lips", "ordinal": 0},
              {"sense_key": "candy", "gloss": "chocolate candy", "ordinal": 1}]
    assert q.bind_example_sense_ex("She ate chocolate.", senses)[1] == "gloss"
    assert q.bind_example_sense_ex("The door is red.", senses) == (None, "none")
    sense, evidence = q.bind_example_sense_ex("The door is red.", senses, fallback_main=True)
    assert (sense["sense_key"], evidence) == ("main", "fallback")
    only = [{"sense_key": "main", "gloss": "x", "ordinal": 0}]
    assert q.bind_example_sense_ex("The door is red.", only)[1] == "single"
