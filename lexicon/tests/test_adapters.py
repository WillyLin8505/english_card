"""Each adapter's normalization and the shared validation rules, on
small recorded records (no network)."""

from app import catalog
from app.adapters import ADAPTERS, Candidate, Context
from app.adapters.base import frequency_profile, validate
from app.adapters.cmudict import CMUdict
from app.adapters.kaikki import _clean_etymology, _native_word, form_field, ipa_to_arpabet
from app.adapters.local import (LocalCalc, derivation, derived_adjective_ipa, inflected_ipa,
                                sentence_level, _edit1, plausible_form, word_forms)
from app.adapters.tatoeba import _pick_translation
from app.adapters.ai import AITranslate

APPLE = [{
    "word": "apple", "lang": "English", "lang_code": "en", "pos": "noun",
    "senses": [
        {"glosses": ["The fruit of the tree Malus domestica."], "tags": [],
         "examples": [{"text": "She ate an apple for lunch.", "type": "example"},
                      {"text": "Old quote with an apple.", "type": "quotation", "ref": "1900"}],
         "synonyms": [{"word": "pome"}]},
        {"glosses": ["A tree of the genus Malus."], "tags": ["rare"]},
    ],
    "sounds": [{"ipa": "/ˈæp.əl/", "tags": ["General-American"]},
               {"audio": "En-us-apple.ogg", "tags": ["US"],
                "mp3_url": "https://upload.wikimedia.org/x/En-us-apple.ogg.mp3"},
               {"homophone": "appel"}],
    "forms": [{"form": "apples", "tags": ["plural"]}],
    "hyphenations": [{"parts": ["ap", "ple"]}],
    "derived": [{"word": "applesauce"}, {"word": "apple pie"}],
    "translations": [{"lang": "Chinese Mandarin", "code": "zh", "word": "蘋果 /苹果",
                      "sense": "fruit of Malus domestica"},
                     {"lang": "French", "code": "fr", "lang_code": "fr", "word": "pomme",
                      "sense": "fruit"}],
    "etymology_text": "Etymology tree\nOld English æppel\nEnglish apple\nFrom Middle English appel.",
    "etymology_templates": [{"name": "inh", "args": {"1": "en", "2": "enm", "3": "appel"}}],
}, {
    "word": "apple", "lang": "English", "lang_code": "en", "pos": "verb",
    "senses": [{"glosses": ["To look like an apple."]}],
    "forms": [{"form": "appled", "tags": ["past"]}, {"form": "appled", "tags": ["participle", "past"]},
              {"form": "appling", "tags": ["participle", "present"]},
              {"form": "apples", "tags": ["present", "singular", "third-person"]}],
}]


def test_ai_native_prefetch_combines_fields(monkeypatch):
    adapter = AITranslate()
    ctx = Context("en", "zh-TW", "bench", "bench", resolved={
        "definition": [{"sense_key": "s1", "gloss": "A long seat.", "pos": "noun"}],
        "example_sentences": [{"key": "e1", "text": "She sat on the bench."}],
        "synonyms": [{"word": "seat"}],
        "related": [{"word": "seat"}],
    })
    ctx.memo[("missing_slots", "native_definition")] = {"s1"}
    ctx.memo[("missing_slots", "example_translation")] = {"e1"}
    ctx.memo[("missing_slots", "synonyms_native")] = {"seat"}
    ctx.memo[("missing_slots", "related_native")] = {"seat"}
    calls = []

    def fake_call(context, kind, items, lang_out=None):
        calls.append((kind, items))
        gloss = {"gloss": "長椅", "sentence": "她坐在長椅上", "word": "座位"}
        return ({item["id"]: gloss[item["task"]] for item in items}, "qwen/test")

    monkeypatch.setattr(adapter, "_call", fake_call)
    batches = adapter.prefetch(ctx, ["native_definition", "example_translation",
                                     "synonyms_native", "related_native"])

    assert batches == 1
    assert len(calls) == 1 and calls[0][0] == "bundle"
    assert len(calls[0][1]) == 3  # repeated "seat" is translated once for both fields
    assert {item["task"] for item in calls[0][1]} == {"gloss", "sentence", "word"}
    assert adapter.lookup("native_definition", ctx)[0].value["text"] == "長椅"
    assert adapter.lookup("example_translation", ctx)[0].value["text"] == "她坐在長椅上"
    assert adapter.lookup("synonyms_native", ctx)[0].value["text"] == "座位"
    assert adapter.lookup("related_native", ctx)[0].value["text"] == "座位"


def ctx(**kw):
    return Context("en", kw.pop("native", "zh-TW"), "apple", "apple", **kw)


def norm(field, c=None, raw=APPLE):
    k = ADAPTERS["kaikki"]
    out = k.normalize(field, raw, c or ctx())
    for x in out:
        x.source = "kaikki"
        r = k.validate(x, c or ctx())
        x.valid, x.invalid_reason = r is None, r
    return out


def test_kaikki_senses_forms_and_sounds():
    defs = norm("definition")
    assert [d.value["pos"] for d in defs] == ["noun", "noun", "verb"]
    assert defs[1].confidence < 1  # a rare sense
    assert [c.value["form"] for c in norm("noun_plural")] == ["apples"]
    assert [c.value["form"] for c in norm("verb_past")] == ["appled"]
    assert [c.value["form"] for c in norm("verb_present_participle")] == ["appling"]
    assert [c.value["form"] for c in norm("verb_third_person")] == ["apples"]
    ipa = norm("ipa")
    assert ipa[0].value == {"ipa": "/ˈæp.əl/", "accent": ["US"], "pos": "noun"}
    audio = norm("audio")
    assert audio[0].value["url"].endswith(".mp3") and audio[0].valid
    assert [c.value["word"] for c in norm("homophones")] == ["appel"]


def test_example_column_list_is_invalid_without_rejecting_prose():
    from app.text import is_column_word_list
    text = 'custard apple\u2003\u2003\u2003 rose apple\u2003\u2003\u2003 thorn apple'
    assert is_column_word_list(text, 'apple')
    c = Candidate('example_sentences', 'en', {'text': text}, 'list')
    assert '詞彙' in validate(c, ctx())
    for prose in ['She eats an apple.', 'I eat apple\tI cook apple',
                  'apple is green   apple is red', 'A bench.',
                  'I ate an apple.   Then I went home.']:
        assert not is_column_word_list(prose, 'apple')
    assert norm("syllables")[0].value["syllables"] == ["ap", "ple"]
    assert [c.value["word"] for c in norm("derived_terms")] == ["applesauce"]  # no phrases


def test_kaikki_examples_skip_quotations():
    ex = norm("example_sentences")
    assert [e.value["text"] for e in ex] == ["She ate an apple for lunch."]


def test_kaikki_translations_bind_to_the_matching_sense():
    defs = norm("definition")
    c = ctx(resolved={"definition": [d.value for d in defs]})
    zh = norm("native_definition", c)
    fruit = defs[0].value["sense_key"]
    assert [(x.value["sense_key"], x.value["text"]) for x in zh] == [(fruit, "蘋果")]
    fr = norm("native_definition", ctx(native="fr", resolved={"definition": [d.value for d in defs]}))
    assert fr[0].value["text"] == "pomme"


def test_kaikki_etymology():
    assert _clean_etymology(APPLE[0]["etymology_text"]) == "From Middle English appel."
    orig = norm("original_form")
    assert orig[0].value == {"form": "appel", "language": "Middle English", "code": "enm"}


def test_native_word_rules():
    assert _native_word({"lang": "Chinese Mandarin", "word": "蘋果 /苹果"}, "zh-TW") == "蘋果"
    assert _native_word({"lang": "Chinese Cantonese", "word": "蘋果"}, "zh-TW") is None
    assert _native_word({"lang": "French", "code": "fr", "word": "pomme"}, "fr") == "pomme"


def test_form_field_mapping_skips_obsolete_forms():
    assert form_field("verb", {"past"}, "en") == "verb_past"
    assert form_field("verb", {"past", "participle"}, "en") == "verb_past_participle"
    assert form_field("adj", {"comparative"}, "en") == "adj_comparative"
    assert form_field("adj", {"comparative", "obsolete"}, "en") is None
    assert form_field("verb", {"indicative", "present", "first-person", "plural"}, "fr") == "fr_present_1p"
    assert form_field("adj", {"feminine", "plural"}, "fr") == "fr_feminine_plural"


def test_ipa_to_arpabet():
    assert ipa_to_arpabet("/ˈæpəl/") == "AE1 P AH0 L"
    assert ipa_to_arpabet("/kæt/") == "K AE1 T"


def test_cmudict_phonemes_stress_and_sound_alikes(tmp_path):
    f = tmp_path / "cmudict.dict"
    f.write_text("apple AE1 P AH0 L\nappel AE1 P AH0 L\nopal OW1 P AH0 L\n", encoding="utf-8")
    a = CMUdict()
    a.snapshot = {"path": str(f), "id": None}
    raw = a.fetch(ctx())
    assert a.normalize("phonemes", raw, ctx())[0].value["phonemes"] == "AE1 P AH0 L"
    assert a.normalize("stress", raw, ctx())[0].value == {"pattern": "1 0", "primary_syllable": 1}
    assert [c.value["word"] for c in a.normalize("homophones", raw, ctx())] == ["appel"]


def test_tatoeba_example_and_translation_normalize():
    t = ADAPTERS["tatoeba"]
    raw = {"mode": "api", "sentences": [
        {"id": 7, "text": "I like apples.", "owner": "u",
         "translations": [{"id": 8, "text": "我喜欢苹果。", "owner": "v"}]}]}
    ex = t.normalize("example_sentences", raw, ctx())
    assert ex[0].value["tatoeba_id"] == 7 and ex[0].source_record_id == "7"
    c = ctx(resolved={"example_sentences": [{"text": "I like apples.", "key": ex[0].key,
                                               "tatoeba_id": 7}]})
    tr = t.normalize("example_translation", raw, c)
    assert tr[0].slot == ex[0].key
    assert tr[0].value["converted"] is True  # Simplified → Taiwan Traditional
    assert "蘋果" in tr[0].value["text"]


def test_tatoeba_skips_fragments_and_ranks_odd_names_last():
    from app.adapters.base import Context
    t = ADAPTERS["tatoeba"]
    c = Context("en", "zh-TW", "vehicle", "vehicle", resolved={"pos": [{"pos": "noun"}]})
    sentences = [
        {"id": 1, "text": "kinetic kill vehicle", "translations": [{"id": 2, "text": "載具"}]},
        {"id": 3, "text": "Ziri drove the vehicle home.", "translations": [{"id": 4, "text": "齊里開車回家。"}]},
        {"id": 5, "text": "She parked the vehicle outside.", "translations": [{"id": 6, "text": "她把車停在外面。"}]},
    ]
    values = [item.value for item in t.normalize(
        "example_sentences", {"mode": "api", "sentences": sentences}, c)]
    ids = [v["tatoeba_id"] for v in values]
    assert 1 not in ids and ids.index(5) < ids.index(3)
    assert validate(Candidate("example_sentences", "en", {"text": "kinetic kill vehicle"}, "k"), c) \
        == "不是完整句"


def test_tatoeba_prefers_bilingual_pairs_and_short_sentences():
    t = ADAPTERS["tatoeba"]
    sentences = []
    for i in range(8):
        sentences.append({"id": i, "text": f"Apple is red {i}.", "translations": []})
    sentences.append({"id": 99, "text": "Apple is green.",
                      "translations": [{"id": 100, "text": "蘋果是綠色的。"}]})
    sentences.append({"id": 50, "text": "An apple " + "and more " * 10 + "apples.",
                      "translations": [{"id": 51, "text": "很長"}]})
    values = [c.value for c in t.normalize(
        "example_sentences", {"mode": "api", "sentences": sentences}, ctx())]
    # The pair first; untranslated sentences (each needing an AI
    # translation) only until the level has three.
    assert [v["tatoeba_id"] for v in values][:1] == [99] and len(values) == 3
    assert all(v["level"] == "A1" for v in values)
    assert values[0]["has_translation"] is True
    assert 50 not in [v["tatoeba_id"] for v in values], "longer than 20 words"
    # With enough pairs a level takes five of them and nothing untranslated.
    pairs = [{"id": 200 + i, "text": f"The apple is red {i}.", "translations": [{"id": 300 + i,
             "text": "蘋果熟了。"}]} for i in range(7)]
    values = [c.value for c in t.normalize(
        "example_sentences", {"mode": "api", "sentences": sentences + pairs}, ctx())]
    assert len(values) == 5 and all(v["has_translation"] for v in values)


def test_fields_a_word_cannot_have_or_simply_lacks():
    from app.pipeline import not_applicable
    c = ctx()
    c.resolved["pos"] = [{"pos": "noun"}]
    assert not_applicable("verb_past", c) == "不是動詞"
    assert not_applicable("noun_plural", c) is None
    c.resolved["etymology_text"] = []
    assert not_applicable("etymology_native", c) == "沒有需要翻譯的內容"
    assert v_long("An apple a day keeps the doctor away, and " + "we eat " * 8 + "apples.")


def v_long(text):
    return validate(Candidate("example_sentences", "en", {"text": text}, "k"), ctx()) \
        == "超過 20 個字"


def test_pick_translation_prefers_traditional():
    trs = [{"id": 1, "text": "我喜欢苹果。"}, {"id": 2, "text": "我喜歡蘋果。"}]
    tr, converted = _pick_translation(trs, "zh-TW")
    assert tr["id"] == 2 and not converted


def test_validation_rules():
    c = ctx()

    def v(field, value, lang="en"):
        return validate(Candidate(field, lang, value, "k"), c)

    assert v("ipa", {"ipa": "AE1 P AH0 L"}) is not None  # not marked as IPA
    assert v("ipa", {"ipa": "/AE1 P AH0 L/"}) == "這是 ARPAbet 音素，不是 IPA"
    assert v("ipa", {"ipa": "/ˈæpəl/"}) is None
    assert v("phonemes", {"phonemes": "/ˈæpəl/"}) is not None
    assert v("native_definition", {"text": "苹果"}, "zh-TW") == "簡體字（繁中資料包需繁體）"
    assert v("native_definition", {"text": "蘋果"}, "zh-TW") is None
    assert v("native_definition", {"text": "apple"}, "zh-TW") == "不是中文"
    assert v("native_definition", {"text": "背gammon遊戲"}, "zh-TW") == "夾雜拉丁字母／殘字：gammon"
    assert v("native_definition", {"text": "家貓（Felis catus）"}, "zh-TW") is None  # 學名
    assert v("native_definition", {"text": "DNA 檢測"}, "zh-TW") is None  # 白名單縮寫
    assert v("example_sentences", {"text": "Bananas are yellow fruit."}) \
        == "例句沒有用到這個字或可信詞形"
    assert v("synonyms", {"word": "Apple"}) == "和詞條本身相同"
    assert v("audio", {"url": "http://x/a.mp3"}) is not None


def test_chinese_is_written_the_taiwan_way():
    from app.adapters.base import localize
    from app.text import to_taiwan
    assert to_taiwan("意大利麵") == "義大利麵"
    assert to_taiwan("意大利面") == "義大利麵"  # Simplified as well
    assert to_taiwan("芝士蛋糕、視頻、土豆泥") == "起司蛋糕、影片、馬鈴薯泥"
    assert to_taiwan("菠蘿麵包") == "菠蘿麵包"  # Taiwanese too, kept
    assert to_taiwan("筆記本") == "筆記本" and to_taiwan("筆記本電腦") == "筆記型電腦"
    # 面包 only where it can't be 外面 + 包裝.
    assert to_taiwan("我要另一片面包。") == "我要另一片麵包。"
    assert to_taiwan("他在面包店烤面包") == "他在麵包店烤麵包"
    assert to_taiwan("pasta") == "pasta"
    assert to_taiwan("匙子、湯匙、調羹") == "匙子、湯匙"  # no word named twice
    # A sentence mixing both scripts isn't Simplified as a whole; its
    # Simplified-only characters still become Traditional.
    assert to_taiwan("湯姆把日曆挂在墙上。") == "湯姆把日曆掛在牆上。"
    for tw in ("皇后", "若干", "面子", "公里", "余光中", "嘴唇", "只有一隻"):
        assert to_taiwan(tw) == tw
    # Taiwanese text is left alone: words already used in Taiwan, and
    # letters that only look like a Mainland word inside another word.
    for tw in ("程序", "文件", "社區", "算法", "數據機", "國家的士兵", "外面包裝", "油菜花",
               "大小區別", "舞臺燈光", "比薩斜塔", "台南意麵"):
        assert to_taiwan(tw) == tw
    # Converting twice changes nothing (柳橙汁 must not become 柳柳橙汁).
    from app.text import _tw
    variants, words, _ = _tw()
    for w in [*words, *words.values(), *variants]:
        assert to_taiwan(to_taiwan(w)) == to_taiwan(w), w
    # Every source's zh-TW text passes through it before validation …
    c = Candidate("native_definition", "zh-TW", {"sense_key": "s1", "text": "意大利麵"}, "意大利麵")
    localize(c, ctx())
    assert (c.value["text"], c.key) == ("義大利麵", "義大利麵")
    # … while Simplified text is still left for validation to reject.
    s = Candidate("native_definition", "zh-TW", {"text": "苹果"}, "k")
    localize(s, ctx())
    assert validate(s, ctx()) == "簡體字（繁中資料包需繁體）"


def test_taiwan_spellings_are_not_simplified():
    """問題回報 #24: OpenCC respells some Traditional phrases (工作台 → 工作臺,
    家具 → 傢俱); that alone made them 「簡體字」 and the translation was dropped."""
    from app.text import looks_simplified, to_taiwan
    for tw in ("工作台", "岩壁", "酒液染污了桌布。", "折痕", "和弦", "帶家具的", "可雇用", "托比",
               "皇后", "公里", "面子", "台南意麵", "湯姆把日曆挂在墙上。"):
        assert not looks_simplified(tw), tw
    for cn in ("苹果", "之后", "意大利面", "方便面", "他是个傻瓜。", "警察当场逮捕了小偷。",
               "齊里有一台等离子切割机。"):
        assert looks_simplified(cn), cn
    assert to_taiwan("之后") == "之後" and to_taiwan("工作台") == "工作台"


def test_local_rules():
    assert derivation("happy", "happiness")["affix"] == "-ness"
    assert derivation("happy", "unhappy")["affix"] == "un-"
    assert _edit1("apple", "apply") == "e→y"
    assert _edit1("cat", "cart") == "+r"
    assert sentence_level("Apple is red.") == "A1"


def test_local_ipa_fallbacks_use_a_phonemic_default(monkeypatch):
    from app import kaikki_index

    rows = {
        "dappled": [{"senses": [{"form_of": [{"word": "dapple"}]}]}],
        "dapple": [{"word": "dapple", "sounds": [
            {"ipa": "[ˈdæpəɫ]", "tags": ["UK"]}]}],
        "crumb": [{"word": "crumb", "sounds": [
            {"ipa": "/kɹʌm/", "tags": ["UK", "US"]}]}],
    }
    monkeypatch.setattr(kaikki_index, "lookup", lambda _language, word: rows.get(word, []))

    assert inflected_ipa("dappled")[0]["ipa"] == "/ˈdæpəld/"
    assert derived_adjective_ipa("crumbly")[0]["ipa"] == "/kɹʌmbli/"


def test_examples_reject_bad_source_forms_and_do_not_guess_a_sense():
    pan = Context("en", "zh-TW", "pan", "pan", resolved={
        "pos": [{"pos": "noun"}],
        "noun_plural": [{"form": "pans"}, {"form": "pen"}],
        "definition": [
            {"sense_key": "cookware", "gloss": "A wide flat receptacle used for cooking."},
            {"sense_key": "criticism", "gloss": "Strong adverse criticism."},
        ],
        "example_sentences": [
            {"text": "Hopefully things will pan out nicely.", "key": "phrasal"},
            {"text": "For example, this is a pen.", "key": "wrong-spelling"},
            {"text": "You scorned me and the mighty Pan.", "key": "proper-name"},
            {"text": "The wide flat pan is used for cooking.", "key": "cookware"},
        ],
    })
    assert plausible_form("pan", "pans") and plausible_form("pan", "panned")
    assert not plausible_form("pan", "pen")
    assert "pen" not in word_forms(pan)
    assert validate(Candidate("example_sentences", "en",
                              {"text": "This pen writes well."}, "bad"), pan) \
        == "例句沒有用到這個字或可信詞形"
    mapped = LocalCalc().normalize("example_sense", None, pan)
    assert [(c.slot, c.value["sense_key"]) for c in mapped] == [("cookware", "cookware")]


def test_english_form_validation_rejects_neighbouring_spelling():
    ctx = Context("en", "zh-TW", "pan", "pan")
    bad = Candidate("noun_plural", "en", {"form": "pen"}, "pen")
    good = Candidate("noun_plural", "en", {"form": "pans"}, "pans")
    assert validate(bad, ctx) == "詞形和詞條的拼字變化不合理"
    assert validate(good, ctx) is None


def test_frequency_profile_marks_obscure_relation_words_hidden():
    common = frequency_profile(4.76)
    obscure = frequency_profile(1.28)
    assert common["rarity"] in ("common", "everyday") and not common["hide_by_default"]
    assert obscure["cefr"] == "C2" and obscure["hide_by_default"]


def test_every_catalog_source_has_an_adapter_and_valid_defaults():
    assert set(ADAPTERS) == set(catalog.SOURCES)
    for t, n in catalog.PAIRS:
        for f in catalog.fields_for(t):
            sources, strategy, _ = catalog.default_policy(t, n, f.key)
            assert strategy in catalog.STRATEGIES
            for s in sources:
                assert catalog.supports(s, t, n, f.key)[0], (t, n, f.key, s)


def test_tatoeba_api_uses_only_direct_translations(monkeypatch):
    from app.adapters import http as h
    t = ADAPTERS["tatoeba"]
    data = {"data": [{"id": 1, "text": "They are eating bread.", "translations": [
        {"id": 2, "lang": "cmn", "text": "我們在吃麵包。", "is_direct": False},
        {"id": 3, "lang": "cmn", "text": "他們在吃麵包。", "is_direct": True}]}]}
    monkeypatch.setattr(h, "get", lambda *a, **k: (data, 200))
    raw = t._api(Context("en", "zh-TW", "bread", "bread"))
    assert [x["id"] for x in raw["sentences"][0]["translations"]] == [3]


def test_datamuse_normalize(monkeypatch):
    d = ADAPTERS["datamuse"]
    rows = {"sl": [{"word": "apple", "score": 100}, {"word": "ample", "score": 90},
                   {"word": "apal", "score": 80}],
            "rel_hom": [], "md": [{"word": "apple", "tags": ["f:24.5"]}]}
    monkeypatch.setattr(d, "ask", lambda c, p: rows["md"] if "md" in p else rows[next(
        k for k in ("sl", "rel_hom") if k in p)])
    near = d.normalize("near_homophones", None, ctx())
    assert [c.value["word"] for c in near] == ["ample"]  # itself and junk spellings dropped
    freq = d.normalize("frequency", None, ctx())
    assert freq[0].value["zipf"] == 4.39


def test_datamuse_drops_proper_nouns_and_keeps_the_part_of_speech(monkeypatch):
    d = ADAPTERS["datamuse"]
    rows = [{"word": "fruit", "score": 90, "tags": ["n"]},
            {"word": "abel", "score": 80, "tags": ["n", "prop"]},
            {"word": "babylon", "score": 70, "tags": ["n", "prop"]},
            {"word": "ripe", "score": 60, "tags": ["adj"]}]
    monkeypatch.setattr(d, "ask", lambda c, p: rows)
    got = {c.value["word"]: c.value.get("pos") for c in d.normalize("related", None, ctx())}
    assert got == {"fruit": "noun", "ripe": "adj"}


def test_sentences_are_leveled_on_the_words_around_the_headword():
    from app.adapters.local import sentence_level, word_level
    # "calendar" is A2; the sentence around it is A1 English.
    assert sentence_level("I have a calendar.") == "A2"
    assert sentence_level("I have a calendar.", frozenset({"calendar"})) == "A1"
    assert word_level("chalice") in ("C1", "C2") and word_level("glass") == "A1"


def test_kaikki_forms_are_shared_with_the_base_word():
    """eat, ate and eaten all show the same table: a headword that is only a
    form of another word takes that word's forms (spec: shared inflections)."""
    eat = [{"word": "eat", "pos": "verb", "senses": [{"glosses": ["To consume food."]}],
            "forms": [{"form": "ate", "tags": ["past"]},
                      {"form": "eaten", "tags": ["participle", "past"]},
                      {"form": "eating", "tags": ["participle", "present"]},
                      {"form": "eats", "tags": ["present", "singular", "third-person"]}]}]
    ate = [{"word": "ate", "pos": "verb",
            "senses": [{"glosses": ["simple past of eat"], "tags": ["form-of", "past"],
                        "form_of": [{"word": "eat"}]}]}]
    c = Context("en", "zh-TW", "ate", "ate")
    c.memo[("kaikki-other", "en", "eat")] = eat
    forms = {f: [x.value["form"] for x in norm(f, c, ate)][:1] for f in
             ("verb_base", "verb_past", "verb_past_participle",
              "verb_present_participle", "verb_third_person")}
    assert forms == {"verb_base": ["eat"], "verb_past": ["ate"], "verb_past_participle": ["eaten"],
                     "verb_present_participle": ["eating"], "verb_third_person": ["eats"]}


def test_recordings_fill_a_british_and_an_american_slot():
    from app.adapters.commons import WikimediaCommons, mp3_url
    from app.adapters.kaikki import audio_slot, file_accent
    assert file_accent("en-uk-London-bottle.ogg") == ["UK"]
    assert file_accent("EN-AU ck1 bench.ogg") == ["AU"]
    assert file_accent("LL-Q1860 (eng)-Vealhurl-apple.wav") == []
    assert [audio_slot(a) for a in (["US", "UK"], ["US"], ["AU"], [])] == ["UK", "US", "AU", "other"]
    raw = {"query": {"pages": [
        {"title": "File:En-uk-cheese.ogg", "imageinfo": [
            {"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/En-uk-cheese.ogg"}]},
        {"title": "File:En-gb-cheese.ogg", "missing": True}]}}
    got = WikimediaCommons().normalize("audio", raw, Context("en", "zh-TW", "cheese", "cheese"))
    assert [(c.slot, c.value["file"]) for c in got] == [("UK", "En-uk-cheese.ogg")]
    assert got[0].value["url"] == mp3_url(got[0].value["fallback_url"]) == (
        "https://upload.wikimedia.org/wikipedia/commons/transcoded/a/ab/En-uk-cheese.ogg/"
        "En-uk-cheese.ogg.mp3")


def test_relation_word_without_pos_is_read_in_the_headwords_pos():
    """問題回報 #36: ample (adj.) is related to big — 大, not the noun's 大人."""
    big = [{"word": "big", "pos": "noun", "senses": [{"glosses": ["A big name."]}],
            "translations": [{"code": "zh", "lang": "Chinese Mandarin", "word": "大人物",
                              "sense": "important person"}]},
           {"word": "big", "pos": "adj", "senses": [{"glosses": ["Of great size."]}],
            "translations": [{"code": "zh", "lang": "Chinese Mandarin", "word": "大",
                              "sense": "of a great size"},
                             {"code": "zh", "lang": "Chinese Mandarin", "word": "巨大",
                              "sense": "of a great size"},
                             {"code": "zh", "lang": "Chinese Mandarin", "word": "大人",
                              "sense": "adult"}]}]
    c = Context("en", "zh-TW", "ample", "ample",
                resolved={"pos": [{"pos": "adj"}], "related": [{"word": "big"}]})
    c.memo[("kaikki-other", "en", "big")] = big
    ample = [{"word": "ample", "pos": "adj", "senses": [{"glosses": ["Large; great."]}]}]
    got = {x.value["word"]: x.value["text"] for x in norm("related_native", c, ample)}
    assert got == {"big": "大、巨大"}  # the first sense only, not "adult" 大人
    # No entry in the headword's part of speech: any meaning beats none.
    c2 = Context("en", "zh-TW", "ample", "ample",
                 resolved={"pos": [{"pos": "verb"}], "related": [{"word": "big"}]})
    c2.memo[("kaikki-other", "en", "big")] = big
    assert [x.value["text"] for x in norm("related_native", c2, ample)] == ["大人物"]
    # major (adj.) has no Chinese of its own: nothing, not the noun's 少校.
    major = [{"word": "major", "pos": "noun", "senses": [{"glosses": ["A rank."]}],
              "translations": [{"code": "zh", "lang": "Chinese Mandarin", "word": "少校",
                                "sense": "military rank"}]},
             {"word": "major", "pos": "adj", "senses": [{"glosses": ["Greater."]}]}]
    c3 = Context("en", "zh-TW", "ample", "ample",
                 resolved={"pos": [{"pos": "adj"}], "related": [{"word": "major"}]})
    c3.memo[("kaikki-other", "en", "major")] = major
    assert norm("related_native", c3, ample) == []


def test_senses_of_a_later_etymology_are_labelled():
    sofa = [{"word": "sofa", "pos": "noun", "etymology_number": 1,
             "senses": [{"glosses": ["An upholstered seat."]}]},
            {"word": "sofa", "pos": "noun", "etymology_number": 2,
             "senses": [{"glosses": ["A slave soldier of the Mali Empire."]}]},
            {"word": "sofa", "pos": "verb", "etymology_number": "3",
             "senses": [{"glosses": ["To sit."]}]}]
    defs = norm("definition", Context("en", "zh-TW", "sofa", "sofa"), sofa)
    assert [d.value["labels"] for d in defs] == [[], ["etymology-2"], ["etymology-3"]]  # Kaikki also writes "3"


def test_register_is_classified_per_sense_with_clear_priority():
    entries = [{"word": "cool", "pos": "adj", "senses": [
        {"glosses": ["Moderately cold."], "tags": []},
        {"glosses": ["Fashionable."], "tags": ["informal"]},
        {"glosses": ["Excellent."], "tags": ["formal", "slang"]},
        {"glosses": ["Composed."], "tags": ["literary"]},
    ]}]
    got = norm("register", Context("en", "zh-TW", "cool", "cool"), entries)
    assert [c.value["register"] for c in got] == ["neutral", "spoken", "slang", "written"]
    assert [c.value["label"] for c in got] == ["中性／通用", "口語", "俚語", "書面語"]
    assert all(c.slot == c.value["sense_key"] for c in got)


def test_clean_etymology_skips_tree_nodes_with_relation_tags():
    # Tree nodes can end in a relation tag ("der.", "bor.") and look like
    # sentences; the text starts after the headword's own node.
    green = ("Etymology tree\nProto-Indo-European *gʰreh₁-der.\nProto-Germanic *grōniz\n"
             "Old English grēne\nEnglish green\nFrom Middle English grene, from Old English grēne.")
    assert _clean_etymology(green) == "From Middle English grene, from Old English grēne."
    pan = ("Etymology tree\nsubstratebor.?\nAncient Greek πᾰτᾰ́νη (pătắnē)bor.\nLatin pannabor.?\n"
           "English pan\nFrom Middle English panne.")
    assert _clean_etymology(pan) == "From Middle English panne."
    # A derived word's tree has its base's node first.
    crumbly = ("Etymology tree\nEnglish crumble\nProto-Indo-European *-kos\nEnglish -y\n"
               "English crumbly\nFrom crumble + -y.")
    assert _clean_etymology(crumbly) == "From crumble + -y."
    assert _clean_etymology("PIE word\n *dwóh₁\nFrom wood + -en.") == "From wood + -en."


def test_kaikki_morphemes_only_from_the_first_etymology():
    from app.adapters.kaikki import _main_etymology
    entries = [{"pos": "noun", "etymology_number": 1}, {"pos": "verb", "etymology_number": 1},
               {"pos": "noun", "etymology_number": 2, "etymology_templates": [
                   {"name": "affix", "args": {"1": "en", "2": "flow", "3": "-er"}}]}]
    assert [e["pos"] for e in _main_etymology(entries)] == ["noun", "verb"]
    assert _main_etymology([{"pos": "noun"}]) == [{"pos": "noun"}]


def test_example_usage_part_of_speech():
    """問題回報 #86: mugged is the verb, the mug the noun, and 「the wound」
    is not wind at all."""
    from app.adapters.local import _usage_pos
    forms, verb_only = {"wind", "winds", "wound", "winding"}, frozenset({"wound", "winding"})
    assert _usage_pos("The wound will not stop bleeding.", forms, verb_only) == "other"
    assert _usage_pos("I think the wind's dropping off.", forms, verb_only) == "noun"
    assert _usage_pos("He wound the clock.", forms, verb_only) == "verb"
    assert _usage_pos("Winds from the sea are moist.", forms, verb_only) is None
    assert _usage_pos("This still winds me up.", {"wind", "winds"}, frozenset()) is None
    assert _usage_pos("His lectures are long-winding.", forms, verb_only) == "other"
    forms, verb_only = {"mug", "mugs", "mugged"}, frozenset({"mugged"})
    assert _usage_pos("Tom was mugged.", forms, verb_only) == "verb"
    assert _usage_pos("I was thirsty. Mugs of tea helped.", forms, verb_only) is None
    assert _usage_pos("Hopefully things will mug up.", forms, verb_only, "mug") == "other"
    leaf = {"leaf", "leaves"}
    assert _usage_pos("The train leaves from Platform 5.", leaf, frozenset(), "leaf") == "other"
    assert _usage_pos("We take the bus that leaves at four.", leaf, frozenset(), "leaf") == "other"
    assert _usage_pos("The leaves turn red in autumn.", leaf, frozenset(), "leaf") != "other"
    assert _usage_pos("These green leaves turn red or yellow in fall.", leaf, frozenset(), "leaf") == "noun"
    assert _usage_pos("An icy wind blew into the room through the open window.",
                      {"wind", "winds", "winding", "winded"},
                      frozenset({"wound", "winding", "winded"}), "wind") == "noun"
    trees = {"tree", "trees"}
    assert _usage_pos("There used to be big trees around the pond.", trees, frozenset(), "tree") is None
    assert _usage_pos("Cats' eyes are sensitive.", {"cat", "cats"}, frozenset(), "cat") is None
    knife = {"butter knife", "butter knives"}
    assert _usage_pos("We need a butter knife.", knife, frozenset(), "butter knife") is None
    assert _usage_pos("We need a knife.", knife, frozenset(), "butter knife") == "other"
    assert _usage_pos("The thief mugged her.", forms, verb_only) == "verb"
    assert _usage_pos("I gave Tom a coffee mug.", forms, verb_only) == "noun"
    assert _usage_pos("The mug is on the table.", forms, verb_only) == "noun"
    forms, verb_only = {"warm", "warmer", "warmed"}, frozenset({"warmed"})
    assert _usage_pos("Sunshine is a warm burst of joy.", forms, verb_only) is None
    from app.adapters.local import matches_lexeme_pos
    assert matches_lexeme_pos(
        "She breaded the chicken before frying.", "bread", "verb",
        {"bread", "breads", "breaded", "breading"}, frozenset({"breaded", "breading"}))
    assert not matches_lexeme_pos(
        "I bought a loaf of bread.", "bread", "verb",
        {"bread", "breads", "breaded", "breading"}, frozenset({"breaded", "breading"}))
    assert not matches_lexeme_pos(
        "They formed a shadow government.", "shadow", "adj", {"shadow", "shadows"}, frozenset())
    assert matches_lexeme_pos(
        "The paper is crinkled.", "crinkled", "adj", {"crinkled"}, frozenset())
    assert matches_lexeme_pos(
        "Use the crinkled paper.", "crinkled", "adj", {"crinkled"}, frozenset())
    assert not matches_lexeme_pos(
        "Where does this street lead to?", "street", "adj", {"street", "streets"}, frozenset())
    assert not matches_lexeme_pos(
        "My favourite type of food is chocolate fudge.", "chocolate", "adj",
        {"chocolate"}, frozenset())
    assert not matches_lexeme_pos(
        "Tom said he doesn't think that Mary still does that.", "still", "noun",
        {"still", "stills"}, frozenset())
    assert not matches_lexeme_pos(
        "That still has a question mark next to it.", "still", "noun",
        {"still", "stills"}, frozenset())
    assert not matches_lexeme_pos(
        "He bent this metal bar with only two fingers.", "metal", "adj",
        {"metal"}, frozenset())
    assert not matches_lexeme_pos(
        "We'll also have to create a separate smoking section.", "separate", "noun",
        {"separate"}, frozenset())
    assert matches_lexeme_pos(
        "The walls are brick.", "brick", "adj", {"brick"}, frozenset())
    assert matches_lexeme_pos(
        "In the still of the night I find peace.", "still", "noun",
        {"still", "stills"}, frozenset())
    assert not matches_lexeme_pos(
        "The table is spread with all kinds of fruit.", "spread", "adj",
        {"spread"}, frozenset())
    assert not matches_lexeme_pos(
        "He was playing football with an empty can.", "empty", "noun",
        {"empty"}, frozenset())
    assert not matches_lexeme_pos(
        "The secret was spread.", "spread", "adj", {"spread"}, frozenset())
    assert not matches_lexeme_pos(
        "Taking her dog for a walk helps her connect with others.", "connect", "noun",
        {"connect"}, frozenset())
    assert not matches_lexeme_pos(
        "Not a single cloud could be seen in the sky.", "saw", "verb",
        {"saw", "seen", "seeing"}, frozenset({"seen", "seeing"}))
    assert not matches_lexeme_pos(
        "The tree of the Kabyles is the olive tree.", "olive", "adj", {"olive"}, frozenset())
    assert matches_lexeme_pos(
        "She was shod in pumps.", "shoe", "verb",
        {"shoe", "shod"}, frozenset({"shod"}))
    assert not matches_lexeme_pos(
        "His name was carved into the tombstone.", "carved", "adj",
        {"carved"}, frozenset())
    # 問題回報 #241: a determiner two words back plus a verb is not the noun.
    still = {"still", "stills"}
    assert _usage_pos("My head still felt.", still, frozenset(), "still") is None
    assert _usage_pos(
        "Tom said he doesn't think that Mary still does that.",
        still, frozenset(), "still") is None
    assert _usage_pos(
        "In the still of the night I find peace.", still, frozenset(), "still") == "noun"
    assert _usage_pos(
        "In the quiet still of the night I find peace.", still, frozenset(), "still") == "noun"
    assert not matches_lexeme_pos(
        "My head still felt.", "still", "noun", still, frozenset())


def test_example_pos_frames_are_not_only_suffixes():
    """問題 #243: non -ly adverbs, long adjectives, and hyphenated nouns.

    Noun heads tightened in #241 stay nouns or non-nouns as before.
    """
    from app.adapters.local import matches_lexeme_pos
    # Adverbs: position, not an -ly ending.
    assert matches_lexeme_pos(
        "There are also nightclubs where you dance.", "also", "adv", {"also"}, frozenset())
    assert matches_lexeme_pos(
        "The water was stone cold.", "stone", "adv", {"stone"}, frozenset())
    assert matches_lexeme_pos(
        "Mary still does that.", "still", "adv", {"still", "stills"}, frozenset())
    assert matches_lexeme_pos(
        "The helicopter is hovering overhead.", "overhead", "adv", {"overhead"}, frozenset())
    assert matches_lexeme_pos(
        "I won't ask you anything else today.", "today", "adv", {"today"}, frozenset())
    assert not matches_lexeme_pos(
        "You ran a red light.", "light", "adv", {"light"}, frozenset())
    assert not matches_lexeme_pos(
        "He threw a stone.", "stone", "adv", {"stone"}, frozenset())
    assert not matches_lexeme_pos(
        "In the still of the night I find peace.", "still", "adv",
        {"still", "stills"}, frozenset())
    assert not matches_lexeme_pos(
        "Today is June 18th.", "today", "adv", {"today"}, frozenset())
    assert not matches_lexeme_pos(
        "Please drink the beer before it goes flat.", "flat", "adv", {"flat"}, frozenset())
    assert not matches_lexeme_pos(
        "Wholesale prices had been basically flat.", "flat", "adv", {"flat"}, frozenset())
    assert not matches_lexeme_pos(
        "I had a feeling that something dreadful was happening.", "dreadful", "adv",
        {"dreadful"}, frozenset())
    # Adjectives: dictionary and position, not length or one more suffix.
    assert matches_lexeme_pos(
        "My favorite flavor is chocolate.", "chocolate", "adj", {"chocolate"}, frozenset())
    assert matches_lexeme_pos(
        "This report is informational.", "informational", "adj",
        {"informational"}, frozenset())
    assert matches_lexeme_pos(
        "We held an informational meeting.", "informational", "adj",
        {"informational"}, frozenset())
    assert matches_lexeme_pos(
        "Later, we'll visit the aquatic park.", "aquatic", "adj", {"aquatic"}, frozenset())
    assert matches_lexeme_pos(
        "She was happy.", "happy", "adj", {"happy"}, frozenset())
    assert matches_lexeme_pos(
        "It was very fitting.", "fitting", "adj", {"fitting"}, frozenset())
    assert not matches_lexeme_pos(
        "My favourite type of food is chocolate fudge.", "chocolate", "adj",
        {"chocolate"}, frozenset())
    assert not matches_lexeme_pos(
        "Tom is observing.", "observing", "adj", {"observing"}, frozenset())
    assert not matches_lexeme_pos(
        "The dignitary drove a very fancy car.", "dignitary", "adj",
        {"dignitary"}, frozenset())
    assert not matches_lexeme_pos(
        "The olive tree is old.", "olive", "adj", {"olive"}, frozenset())
    # Hyphenated nouns match as one word.
    assert matches_lexeme_pos(
        "I should redo the close-up in the fifth panel.", "close-up", "noun",
        {"close-up", "close-ups"}, frozenset())
    assert matches_lexeme_pos(
        "She used chickpeas in a stir-fry.", "stir-fry", "noun",
        {"stir-fry"}, frozenset())
    assert not matches_lexeme_pos(
        "Seen close-up, things show their defects.", "close-up", "noun",
        {"close-up"}, frozenset())
    assert not matches_lexeme_pos(
        "The black-and-white marbled cover is timeless.", "black-and-white", "noun",
        {"black-and-white"}, frozenset())
    assert not matches_lexeme_pos(
        "The man in charge of the merry-go-round decided to check it.", "round", "adv",
        {"round"}, frozenset())
    assert not matches_lexeme_pos(
        "It would be counter-productive to do such a thing.", "counter", "adv",
        {"counter"}, frozenset())
    assert not matches_lexeme_pos(
        "That is a masculine and feminine system.", "masculine", "noun",
        {"masculine"}, frozenset())
    assert not matches_lexeme_pos(
        "I ordered steak with scalloped potatoes.", "scallop", "verb",
        {"scallop", "scalloped", "scalloping"}, frozenset({"scalloped", "scalloping"}))
    assert matches_lexeme_pos(
        "He graded assignments in the lounge.", "grade", "verb",
        {"grade", "graded", "grading"}, frozenset({"graded", "grading"}))
    assert not matches_lexeme_pos(
        "The canine teeth are between the incisors and the molars.", "canine", "noun",
        {"canine"}, frozenset())
    assert not matches_lexeme_pos(
        "Lava and ash plumes rose into the sky.", "ash", "adv", {"ash"}, frozenset())
    assert not matches_lexeme_pos(
        "Doctors vaccinated them against whooping cough.", "whoop", "verb",
        {"whoop", "whooping"}, frozenset({"whooping"}))
    assert not matches_lexeme_pos(
        "The U.S. housing market collapsed in 2008.", "house", "verb",
        {"house", "housing", "housed"}, frozenset({"housing", "housed"}))
    assert not matches_lexeme_pos(
        "The firm showed a manned compact vehicle.", "man", "verb",
        {"man", "manned", "manning"}, frozenset({"manned", "manning"}))
    assert not matches_lexeme_pos(
        "SkyDrive showed its eight-propeller, manned compact vehicle.", "man", "verb",
        {"man", "manned", "manning"}, frozenset({"manned", "manning"}))
    assert matches_lexeme_pos(
        "She quickly graded assignments.", "grade", "verb",
        {"grade", "graded", "grading"}, frozenset({"graded", "grading"}))
    assert matches_lexeme_pos(
        "It's a black-and-white picture.", "black-and-white", "adj",
        {"black-and-white"}, frozenset())


def test_example_sense_does_not_use_incidental_counts_as_semantic_evidence():
    """A book leaf has two pages; two weeks does not make leaves book pages."""
    from app.text import example_key
    ctx = Context('en', 'zh-TW', 'leaf')
    ctx.resolved.update({
        'pos': [{'pos': 'noun'}],
        'noun_plural': [{'form': 'leaves'}],
        'definition': [
            {'sense_key': 'plant', 'pos': 'noun', 'gloss':
             'The usually green and flat organ of most vegetative plants.'},
            {'sense_key': 'book', 'pos': 'noun', 'gloss':
             'A sheet of a book, magazine, etc. consisting of two pages, one on each face.'},
        ],
        'example_sentences': [
            {'text': 'The leaves will turn red in two or three weeks.'},
            {'text': 'She turned the leaf of the book.'},
            {'text': 'The leaves will turn red in two or three weeks.',
             'key': 'verified-source', 'sense_key': 'plant'},
        ],
    })
    output = LocalCalc().normalize('example_sense', None, ctx)
    by_example = {c.value['example_key']: c.value['sense_key'] for c in output}
    assert by_example[example_key(ctx.items('example_sentences')[0]['text'])] == 'plant'
    assert by_example[example_key(ctx.items('example_sentences')[1]['text'])] == 'book'
    assert by_example['verified-source'] == 'plant'


def test_example_sense_ignores_prepositions_as_semantic_evidence():
    """問題回報 #143: `through` must not select wind's instrument verb."""
    from app.text import example_key
    ctx = Context('en', 'zh-TW', 'wind')
    ctx.resolved.update({
        'pos': [{'pos': 'noun'}, {'pos': 'verb'}],
        'verb_present_participle': [{'form': 'winding'}],
        'definition': [
            {'sense_key': 'air', 'pos': 'noun', 'gloss': 'Movement of atmospheric air.'},
            {'sense_key': 'instrument', 'pos': 'verb',
             'gloss': 'To blow air through a wind instrument or horn.'},
        ],
        'example_sentences': [
            {'text': 'An icy wind blew into the room through the open window.'},
        ],
    })
    output = LocalCalc().normalize('example_sense', None, ctx)
    by_example = {c.value['example_key']: c.value['sense_key'] for c in output}
    assert by_example[example_key(ctx.items('example_sentences')[0]['text'])] == 'air'


def test_taiwan_usage_drops_erhua_variants():
    from app.adapters.kaikki import _without_erhua
    assert _without_erhua(["門", "門兒", "戶"]) == ["門", "戶"]
    assert _without_erhua(["叉子", "叉兒", "餐叉"]) == ["叉子", "餐叉"]
    assert _without_erhua(["女兒", "閨女"]) == ["女兒", "閨女"]
    assert _without_erhua(["玩", "玩兒"]) == ["玩"]



def test_native_word_from_a_translation_note():
    """問題回報 #103: computer's 電腦 is only in the note."""
    tr = {"lang": "Chinese Mandarin", "sense": "programmable electronic device",
          "note": "電腦 /电脑 (diànnǎo, literally “electric brain”)"}
    assert _native_word(tr, "zh-TW") == "電腦"
    assert _native_word({"lang": "Chinese Mandarin", "note": "see 電腦"}, "zh-TW") is None


def test_taiwan_quotes_and_platform():
    from app.text import to_taiwan
    assert to_taiwan("“滾石不生苔”是一句諺語。") == "「滾石不生苔」是一句諺語。"
    assert to_taiwan("火車從3號站臺出發。") == "火車從3號月臺出發。"
    assert to_taiwan('"滾石"很好') == "「滾石」很好"
    assert to_taiwan('He said "hi".') == 'He said "hi".'


def test_interjection_needs_the_word_said_on_its_own():
    """問題回報 #286: an interjection is the word said as its own utterance."""
    from app.adapters.local import matches_lexeme_pos
    assert matches_lexeme_pos(
        '"Cheese!" said the photographer.', "cheese", "intj", {"cheese"}, frozenset())
    assert matches_lexeme_pos("Fire! Everyone get out now.", "fire", "intj", {"fire"}, frozenset())
    assert matches_lexeme_pos(
        'The director shouted "Cut!" and the actors stopped.', "cut", "intj", {"cut"}, frozenset())
    assert not matches_lexeme_pos("The fire was warm.", "fire", "intj", {"fire"}, frozenset())
    assert not matches_lexeme_pos(
        "I like cheese on my bread.", "cheese", "intj", {"cheese"}, frozenset())


def test_compound_noun_is_matched_as_a_phrase():
    """卡 #166: the single-word noun frames never matched "raised bed"."""
    from app.adapters.local import matches_lexeme_pos
    assert matches_lexeme_pos("We grow tomatoes in a raised bed.", "raised bed", "noun",
                              {"raised bed"}, frozenset())
    assert matches_lexeme_pos("Our galaxy has several spiral arms.", "spiral arms", "noun",
                              {"spiral arms"}, frozenset())
    assert not matches_lexeme_pos("The bed was raised off the floor.", "raised bed", "noun",
                                  {"raised bed"}, frozenset())
