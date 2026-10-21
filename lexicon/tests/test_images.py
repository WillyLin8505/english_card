"""Matching a sense to its Wikidata concept, on recorded answers (no network)."""

from app import images


def fake_cefr_list(monkeypatch, words):
    """The CEFR-J / Octanove list, faked: {word: {pos: level}}."""
    from app.adapters import local
    monkeypatch.setattr(local, "cefr_list", lambda: {w: (4.0, lv, "") for w, lv in words.items()})


ENTITIES = {
    "Q22687": ("bank", "financial institution that accepts deposits", "銀行"),
    "Q2897058": ("bank", "in geography, raised landform on the side of a water body", "河岸"),
    "Q5": ("Bank", "family name", None),
    "Q7": ("Run", "stream in North Brabant, Netherlands", None),
    "Q81727": ("cup", "vessel for liquids", "杯"),
}


def fake_wikidata(params):
    if params["action"] == "wbsearchentities":
        word = params["search"]
        return {"search": [{"id": q} for q, e in ENTITIES.items() if e[0].lower() == word]}
    return {"entities": {q: {
        "labels": {"en": {"value": ENTITIES[q][0]},
                   **({"zh-tw": {"value": ENTITIES[q][2]}} if ENTITIES[q][2] else {})},
        "descriptions": {"en": {"value": ENTITIES[q][1]}},
        "claims": {"P18": [{}]}} for q in params["ids"].split("|")}}


def test_each_sense_gets_its_own_concept(monkeypatch):
    monkeypatch.setattr(images, "wikidata", fake_wikidata)
    money = images.match_concept("bank", "An institution where one can deposit money.", "銀行")
    river = images.match_concept("bank", "The land alongside a river or water.", "河岸")
    assert money[0] == "Q22687" and river[0] == "Q2897058"
    # The only concept named "cup" is taken though its description shares no
    # word with the gloss; its Chinese label 杯 is part of 杯子.
    assert images.match_concept("cup", "A small open container for drinking.", "杯子")[0] == "Q81727"
    # Proper names and places are never a sense's concept.
    assert images.match_concept("run", "To move swiftly on foot.", "跑") is None


def test_semantic_score_prefers_the_concepts_own_picture():
    assert images.semantic_score({"p18": True}, "cup", "cup") == 0.9
    assert images.semantic_score({"title": "File:Tea cup.jpg"}, "cup", "cup") == 0.7
    assert images.semantic_score({"title": "File:IMG_2041.jpg"}, "cup", "cup") == 0.4


def test_a_picture_belongs_to_a_word_only_when_the_ai_sees_the_word():
    tags = [{"word": "tile"}, {"word": "wall"}, {"word": "arch"}]
    assert not images.shows_word(tags, "ceramic")  # the Ishtar Gate: not under ceramic
    assert images.shows_word([{"word": "ceramic"}, {"word": "label"}], "ceramic")
    assert images.shows_word([{"word": "apples"}], "apple")
    assert images.shows_word([{"word": "cutting board"}], "board")


def test_a_picture_is_shared_by_every_word_its_labels_name(session):
    from app import models as m
    lx = {w: m.Lexeme(language="en", lemma=w, normalized=w, pos="noun", status="full")
          for w in ("bench", "gravel")}
    session.add_all(lx.values())
    session.flush()
    senses = {w: m.Sense(lexeme_id=x.id, sense_key=w, ordinal=0) for w, x in lx.items()}
    session.add_all(senses.values())
    words = ["bench", "gravel", "shadow", *[f"filler-{i}" for i in range(15)]]
    complete_tags = [{"word": word, "pos": "noun", "cefr": images.CEFR_LEVELS[i // 3],
                      "score": 0.9} for i, word in enumerate(words)]
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:Bench.jpg",
                         license_code="CC0", status="ready", tag_status="done",
                         safety_status="safe",
                         tags=complete_tags)
    session.add(asset)
    session.flush()
    session.add(m.SenseImage(sense_id=senses["bench"].id, image_asset_id=asset.id,
                             role="representative", review_status="approved", alt_native={}))
    session.flush()
    assert images.share(session, asset) == 1  # gravel; shadow is no entry
    got = session.query(m.SenseImage).filter_by(sense_id=senses["gravel"].id).one()
    assert got.review_status == "approved", "a reviewed picture is approved for the other word too"
    assert images.share(session, asset) == 0, "never twice"


def test_adult_content_is_quarantined_and_all_bindings_are_rejected(
        session, tmp_path, monkeypatch):
    import io
    import urllib.error

    import pytest
    from app import config, models as m

    monkeypatch.setattr(config, "MEDIA", tmp_path)
    monkeypatch.setattr(images, "TAG_MODE", "cefr")
    (tmp_path / "unchecked.jpg").write_bytes(b"jpeg")
    lexeme = m.Lexeme(language="en", lemma="photo", normalized="photo",
                      pos="noun", status="full")
    session.add(lexeme)
    session.flush()
    sense = m.Sense(lexeme_id=lexeme.id, sense_key="photo", ordinal=0)
    asset = m.ImageAsset(source="user", source_image_id="unsafe-1",
                         license_code="private", status="ready",
                         tag_status="pending", safety_status="unchecked",
                         path="unchecked.jpg")
    session.add_all((sense, asset))
    session.flush()
    binding = m.SenseImage(sense_id=sense.id, image_asset_id=asset.id,
                           role="representative", review_status="approved",
                           alt_native={})
    session.add(binding)
    session.flush()

    def unsafe(*_args, **_kwargs):
        raise urllib.error.HTTPError("http://tagger/tag", 451, "unsafe", {},
                                     io.BytesIO(b'{"code":"unsafe_image"}'))

    monkeypatch.setattr(images.urllib.request, "urlopen", unsafe)
    with pytest.raises(ValueError, match="成人內容"):
        images.tag_asset(session, asset.id)

    assert asset.safety_status == "blocked"
    assert asset.tag_status == "failed"
    assert asset.tags == []
    assert binding.review_status == "rejected"
    review = session.query(m.ImageReview).filter_by(sense_image_id=binding.id).one()
    assert review.decision == "rejected"


def test_only_labels_scored_80_percent_or_more_pass(session, tmp_path, monkeypatch):
    """Every label is checked again; under 80% it is kept aside, never used."""
    import io
    import json
    from urllib.parse import parse_qs, urlsplit
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    monkeypatch.setattr(images, "TAG_MODE", "legacy")
    monkeypatch.setattr(images, "DEFER_TAG_SCORE", False)
    (tmp_path / "a.jpg").write_bytes(b"jpeg")
    looks = {None: ["bench", "gravel", "elephant"], "harder": ["shadow", "tree"],
             "descriptions": ["sunny"]}
    scores = {"bench": 0.99, "gravel": 0.8, "elephant": 0.02, "shadow": 0.7, "tree": 0.95,
              "sunny": 0.85}

    def fake_urlopen(request, timeout=0):
        url = urlsplit(request.full_url)
        q = parse_qs(url.query)
        if url.path == "/score":
            body = {"scores": [{"word": x["word"], "score": scores[x["word"]]}
                               for x in json.loads(q["labels"][0])]}
        else:
            body = {"model": "vision", "candidates": [
                {"word": w, "pos": "noun", "point": [0.5, 0.5]}
                for w in looks[(q.get("focus") or [None])[0]]]}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(images.urllib.request, "urlopen", fake_urlopen)
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:B.jpg",
                         license_code="CC0", status="ready", path="a.jpg")
    session.add(asset)
    session.flush()
    images.tag_asset(session, asset.id)
    assert [t["word"] for t in asset.tags] == ["bench", "tree", "sunny", "gravel"]
    assert [t["word"] for t in asset.dropped_tags] == ["shadow", "elephant"]
    assert asset.tag_status == "done"


def test_old_labels_are_leveled_from_the_list_scored_and_settled(session, tmp_path, monkeypatch):
    """Existing labels: levels from the CEFR list, the 0.80 placeholder is
    measured, then the picture is settled (gaps stay gaps)."""
    import io
    import json
    from urllib.parse import parse_qs, urlsplit
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"jpeg")
    fake_cefr_list(monkeypatch, {"fruit": {"noun": "A1"}, "petal": {"noun": "B2"}})
    asked = []

    def fake_urlopen(request, timeout=0):
        labels = json.loads(parse_qs(urlsplit(request.full_url).query)["labels"][0])
        asked.extend(x["word"] for x in labels)
        return io.BytesIO(json.dumps({"scores": [
            {"word": x["word"], "score": 0.1 if x["word"] == "petal" else 0.9}
            for x in labels]}).encode())

    monkeypatch.setattr(images.urllib.request, "urlopen", fake_urlopen)
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:P.jpg", license_code="CC0",
                         status="ready", path="a.jpg", tag_status="pending", safety_status="safe",
                         tags=[{"word": "fruit", "pos": "noun", "cefr": "C1", "point": [0.5, 0.5],
                                "score": 0.8, "scoreDeferred": True},
                               {"word": "petal", "pos": "noun", "cefr": "C1", "point": [0.5, 0.5],
                                "score": 0.6}])
    session.add(asset)
    session.flush()
    assert images.tag_pending(session, limit=5) == 1
    assert asked == ["fruit"], "only the placeholder is measured again"
    assert asset.tag_status == "done"
    assert [(t["word"], t["cefr"], t["score"]) for t in asset.tags] == [("fruit", "A1", 0.9)]
    assert [(t["word"], t["cefr"]) for t in asset.dropped_tags] == [("petal", "B2")]


def test_tag_asset_defaults_to_cefr_mode(session, tmp_path, monkeypatch):
    """CEFR mode keeps asking until every band has three verified labels."""
    _pin_old_standard(monkeypatch)
    import io
    import json
    from urllib.parse import parse_qs, urlsplit
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    monkeypatch.setattr(images, "TAG_MODE", "cefr")
    monkeypatch.setattr(images, "DEFER_TAG_SCORE", False)
    monkeypatch.setattr(images, "CEFR_TAG_ROUNDS", 2)
    monkeypatch.setattr(images, "dictionary_phrase", lambda s, w: True)  # made-up test words
    fake_cefr_list(monkeypatch, {f"{lv.lower()}-{i}": {"noun": lv}
                                 for lv in images.CEFR_LEVELS for i in range(3)})
    (tmp_path / "a.jpg").write_bytes(b"jpeg")
    seen_modes = []

    def fake_urlopen(request, timeout=0):
        url = urlsplit(request.full_url)
        q = parse_qs(url.query)
        if url.path == "/score":
            labels = json.loads(q["labels"][0])
            body = {"scores": [{"word": x["word"], "score": 0.95} for x in labels]}
        else:
            seen_modes.append((q.get("mode") or [""])[0])
            excluded = set((q.get("exclude") or [""])[0].split(','))
            candidates = []
            for level in images.CEFR_LEVELS:
                for i in range(3):
                    word = f"{level.lower()}-{i}"
                    if word not in excluded:
                        candidates.append({"word": word, "pos": "noun", "cefr": level,
                                           "point": [0.4, 0.5]})
            body = {"model": "vision", "candidates": candidates,
                    "stages": {"queueMs": 5, "modelMs": 900, "modelCalls": 1}}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(images.urllib.request, "urlopen", fake_urlopen)
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:C.jpg",
                         license_code="CC0", status="ready", path="a.jpg")
    session.add(asset)
    session.flush()
    images.tag_asset(session, asset.id)
    assert seen_modes == ["cefr"]
    assert images.cefr_counts(asset.tags) == {level: 3 for level in images.CEFR_LEVELS}
    assert asset.tag_status == "done"
    # 問題回報 #229: one timing line per picture, stage by stage, with the tagger's split.
    line = json.loads(images.TAG_TIMING_LOG.read_text(encoding="utf-8").splitlines()[-1])
    assert (line["asset"], line["outcome"]) == (asset.id, "ok")
    by_stage = {st["stage"]: st for st in line["stages"]}
    assert {"cefr-1", "score-1"} <= set(by_stage)
    assert by_stage["cefr-1"]["tagger"] == [{"queueMs": 5, "modelMs": 900, "modelCalls": 1}]


def _pin_old_standard(monkeypatch):
    """The tests below were written for the three-per-level standard (card #448
    moved the default to five); they pin the old numbers so their logic still holds."""
    monkeypatch.setattr(images, "CEFR_PER_LEVEL", 3)
    monkeypatch.setattr(images, "CEFR_LEVEL_MAX", 4)


def test_card448_default_standard_is_five_per_level():
    assert images.CEFR_PER_LEVEL == 5
    assert images.CEFR_LEVEL_MAX == 5


def test_cefr_picture_stays_pending_when_any_band_has_fewer_than_per_level():
    per_level = images.CEFR_PER_LEVEL
    tags = [{"word": f"{level}-{i}", "cefr": level, "score": 0.9}
            for level in images.CEFR_LEVELS for i in range(per_level)]
    assert images.cefr_complete(tags)
    assert images.cefr_counts(tags) == {level: per_level for level in images.CEFR_LEVELS}
    assert not images.cefr_complete(tags[:-1])


def test_label_level_comes_from_the_cefr_list_never_the_vision_model(session, monkeypatch):
    """Owner decision (問題回報, option A): fruit is A1 even when the model
    filled its C1 band with it."""
    fake_cefr_list(monkeypatch, {"fruit": {"noun": "A1"}, "round": {"adj.": "B1", "verb": "B2"}})
    tag = images.classify_tag_cefr(session, {"word": "fruit", "pos": "noun", "cefr": "C1"})
    assert (tag["cefr"], tag["cefrSource"]) == ("A1", "cefrj")
    tag = images.classify_tag_cefr(session, {"word": "round", "pos": "adjective"})
    assert tag["cefr"] == "B1", "the same part of speech, not the hardest one"


def test_inflections_and_fully_known_phrases_get_reliable_cefr(session, monkeypatch):
    from app import models as m
    fake_cefr_list(monkeypatch, {"black": {"adj.": "A1"}, "fur": {"noun": "B2"},
                                 "leaf": {"noun": "A1"}, "hold": {"verb": "A2"}})
    leaf = m.Lexeme(language="en", lemma="leaf", normalized="leaf", pos="noun", status="full")
    session.add(leaf)
    session.flush()
    session.add(m.Form(lexeme_id=leaf.id, field="plural", form="leaves",
                       normalized="leaves", source="test"))
    session.flush()
    inflected = images.classify_tag_cefr(session, {"word": "leaves", "pos": "noun"})
    holding = images.classify_tag_cefr(session, {"word": "holding", "pos": "verb"})
    phrase = images.classify_tag_cefr(session, {"word": "black fur", "pos": "phrase"})
    unknown = images.classify_tag_cefr(session, {"word": "mystery widget", "pos": "noun"})
    assert (inflected["cefr"], inflected["cefrSource"], inflected["cefrLemma"]) == ("A1", "cefrj", "leaf")
    assert (holding["cefr"], holding["cefrLemma"]) == ("A2", "hold")
    assert (phrase["cefr"], phrase["cefrSource"], phrase["cefrCoreWord"]) == ("B2", "phrase", "fur")
    assert unknown["cefrSource"] == "estimate" and unknown["cefr"] in images.CEFR_LEVELS


def test_cefr_prefers_the_labels_part_of_speech(session):
    from app import models as m
    session.add_all([
        m.Lexeme(language="en", lemma="round", normalized="round", pos="adj",
                 status="full", cefr="B1"),
        m.Lexeme(language="en", lemma="round", normalized="round", pos="verb",
                 status="full", cefr="B2"),
    ])
    session.flush()
    tag = images.classify_tag_cefr(session, {"word": "round", "pos": "adjective"})
    assert tag["cefr"] == "B1"


def test_a_mistagged_part_of_speech_still_uses_the_lists_easy_level(session, monkeypatch):
    """#198: the tagger's part of speech is often wrong, and the old code
    fell through to a letter-split guess when the exact pos had no listed
    level — furniture/adjective → estimate B1, person/adjective → per+son
    B1, number/adverb → numb C1, feather/adjective → feat+her B2. The word
    itself is listed as a noun at an easy level; use that instead of
    guessing from a split that happens to look like real words."""
    fake_cefr_list(monkeypatch, {
        "furniture": {"noun": "A2"}, "person": {"noun": "A1"},
        "number": {"noun": "A1"}, "feather": {"noun": "A2"},
        "numb": {"adj.": "C1"}, "feat": {"noun": "B2"}, "her": {"pronoun": "A1"},
    })
    for word, wrong_pos in (("furniture", "adjective"), ("person", "adjective"),
                            ("number", "adverb"), ("feather", "adjective")):
        tag = images.classify_tag_cefr(session, {"word": word, "pos": wrong_pos})
        assert tag["cefr"] in ("A1", "A2"), (word, wrong_pos, tag)
        assert tag["cefrSource"] == "cefrj"


def test_a_harder_other_pos_entry_never_outranks_a_lower_guess(session, monkeypatch):
    """A rarer, harder sense under a different part of speech (gloss, noun,
    "superficial shine", C2) must not override an easier guess just because
    the spelling matches the tagger's (wrong) part of speech - only an
    *easier* listed level may ever replace the derivation/estimate guess."""
    from app.adapters import base as adapters_base
    fake_cefr_list(monkeypatch, {"gloss": {"noun": "C2"}})
    monkeypatch.setattr(adapters_base, "zipf", lambda *a, **k: 5.0)
    monkeypatch.setattr(adapters_base, "frequency_profile", lambda *a, **k: {"cefr": "A2"})
    tag = images.classify_tag_cefr(session, {"word": "gloss", "pos": "adjective"})
    assert (tag["cefr"], tag["cefrSource"]) == ("A2", "estimate")


def test_a_level_the_picture_cannot_fill_is_a_gap_not_a_retry(session, tmp_path, monkeypatch):
    """Owner decision A: only listed levels; an unfillable level stays a gap
    and the picture is done after one full labelling attempt."""
    _pin_old_standard(monkeypatch)
    import io
    import json
    from urllib.parse import parse_qs, urlsplit
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    monkeypatch.setattr(images, "TAG_MODE", "cefr")
    monkeypatch.setattr(images, "DEFER_TAG_SCORE", False)
    monkeypatch.setattr(images, "CEFR_TAG_ROUNDS", 2)
    fake_cefr_list(monkeypatch, {"fruit": {"noun": "A1"}, "flower": {"noun": "A1"},
                                 "tomato": {"noun": "A1"}, "soil": {"noun": "B2"}})
    monkeypatch.setattr(images, "expand_visible_vocabulary", lambda *a, **k: ([], []))
    (tmp_path / "a.jpg").write_bytes(b"jpeg")

    def fake_urlopen(request, timeout=0):
        url = urlsplit(request.full_url)
        q = parse_qs(url.query)
        if url.path == "/score":
            body = {"scores": [{"word": x["word"], "score": 0.95}
                               for x in json.loads(q["labels"][0])]}
        else:  # the model claims C1/C2 for everyday words
            body = {"model": "vision", "candidates": [
                {"word": w, "pos": "noun", "cefr": lv, "point": [0.5, 0.5]}
                for w, lv in (("fruit", "C1"), ("flower", "C2"), ("tomato", "A1"), ("soil", "B1"))]}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(images.urllib.request, "urlopen", fake_urlopen)
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:T.jpg",
                         license_code="CC0", status="ready", path="a.jpg")
    session.add(asset)
    session.flush()
    images.tag_asset(session, asset.id)
    assert {t["word"]: t["cefr"] for t in asset.tags} == {
        "fruit": "A1", "flower": "A1", "tomato": "A1", "soil": "B2"}
    assert asset.tag_status == "done"
    assert images.cefr_gaps(asset.tags) == ["A2", "B1", "B2", "C1", "C2"]


def test_the_pictures_own_word_is_never_capped_out(session, monkeypatch):
    """balcony A2 scored 99.9% but the A2 band was full (column, furniture,
    plant): the picture's own word stays, the others fill up to three."""
    _pin_old_standard(monkeypatch)
    from app import models as m
    lx = m.Lexeme(language="en", lemma="balcony", normalized="balcony", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="balcony", ordinal=0)
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:Bal.jpg",
                         license_code="CC0", status="ready", tag_status="done", tags=[])
    session.add_all([sense, asset])
    session.flush()
    binding = m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="context",
                           review_status="approved", alt_native={})
    session.add(binding)
    session.flush()
    tags = [{"word": w, "pos": "noun", "cefr": "A2", "score": sc}
            for w, sc in (("column", 1.0), ("furniture", 1.0), ("plant", 1.0), ("table", 0.99),
                          ("chair", 0.98), ("balcony", 0.85))]
    images._settle(session, asset, tags, [], None, done=True)
    # At most four a level (#114 C): the own word plus the three best others.
    assert sorted(t["word"] for t in asset.tags) == ["balcony", "column", "furniture", "plant"]
    assert [t["word"] for t in asset.dropped_tags] == ["table", "chair"]
    assert binding.review_status == "approved"


def test_a_derived_word_takes_its_base_words_level(session, monkeypatch):
    """Owner decision 2026-10-06: arched (not listed) follows arch (noun B2),
    not a word-frequency estimate (C1); unripe → ripe; a phrase uses it too."""
    fake_cefr_list(monkeypatch, {"arch": {"noun": "B2"}, "ripe": {"adj.": "B1"},
                                 "shadow": {"noun": "A2", "verb": "B2"}, "interior": {"noun": "B2"}})
    arched = images.classify_tag_cefr(session, {"word": "arched", "pos": "adjective"})
    unripe = images.classify_tag_cefr(session, {"word": "unripe", "pos": "adjective"})
    shadowed = images.classify_tag_cefr(session, {"word": "shadowed", "pos": "adjective"})
    phrase = images.classify_tag_cefr(session, {"word": "shadowed interior", "pos": "noun"})
    unknown = images.classify_tag_cefr(session, {"word": "tendril", "pos": "noun"})
    assert (arched["cefr"], arched["cefrSource"], arched["cefrLemma"]) == ("B2", "base", "arch")
    assert (unripe["cefr"], unripe["cefrLemma"]) == ("B1", "ripe")
    assert shadowed["cefr"] == "A2", "the easiest level the list gives the base"
    assert (phrase["cefr"], phrase["cefrSource"], phrase["cefrCoreWord"]) == ("B2", "phrase", "interior")
    assert unknown["cefrSource"] == "estimate"


def test_made_up_phrases_are_set_aside(session, monkeypatch):
    """#62: vehicle ahead / sunlit area are descriptions, not vocabulary."""
    from app import models as m
    from app.adapters import ADAPTERS
    monkeypatch.setattr(images, "_PHRASE_CACHE", {})
    monkeypatch.setattr(ADAPTERS["kaikki"], "fetch",
                        lambda ctx: [{"pos": "noun"}] if ctx.lemma == "ceiling fan" else [])
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:Ph.jpg",
                         license_code="CC0", status="ready", tag_status="done", tags=[])
    session.add(asset)
    session.flush()
    tags = [{"word": w, "pos": "noun", "cefr": "B1", "score": 0.95}
            for w in ("ceiling fan", "vehicle ahead", "chair")]
    images._settle(session, asset, tags, [], None, done=True)
    assert sorted(t["word"] for t in asset.tags) == ["ceiling fan", "chair"]
    assert [(t["word"], t["dropReason"]) for t in asset.dropped_tags] == [("vehicle ahead", "不是詞典片語")]


def test_a_made_up_phrase_becomes_its_scored_words_and_plurals_match(session, tmp_path, monkeypatch):
    """wooden surface → wooden + surface, each measured; a child picture
    labelled children still shows child (stored plural)."""
    import io
    import json
    from urllib.parse import parse_qs, urlsplit
    from app import config, models as m
    from app.adapters import ADAPTERS
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"jpeg")
    monkeypatch.setattr(images, "_PHRASE_CACHE", {})
    monkeypatch.setattr(ADAPTERS["kaikki"], "fetch", lambda ctx: [])
    fake_cefr_list(monkeypatch, {"wooden": {"adj.": "A2"}, "surface": {"noun": "B1"},
                                 "child": {"noun": "A1"}})
    asked = []

    def fake_urlopen(request, timeout=0):
        labels = json.loads(parse_qs(urlsplit(request.full_url).query)["labels"][0])
        asked.extend(x["word"] for x in labels)
        return io.BytesIO(json.dumps({"scores": [{"word": x["word"], "score": 0.9}
                                                 for x in labels]}).encode())

    monkeypatch.setattr(images.urllib.request, "urlopen", fake_urlopen)
    lx = m.Lexeme(language="en", lemma="child", normalized="child", pos="noun", status="full")
    session.add(lx)
    session.flush()
    session.add(m.Form(lexeme_id=lx.id, field="noun_plural", form="children",
                       normalized="children", source="test"))
    sense = m.Sense(lexeme_id=lx.id, sense_key="child", ordinal=0)
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:W.jpg", license_code="CC0",
                         status="ready", path="a.jpg", tag_status="pending",
                         tags=[{"word": "wooden surface", "pos": "noun", "point": [0.5, 0.5], "score": None},
                               {"word": "children", "pos": "noun", "point": [0.2, 0.2], "score": 0.95}])
    session.add_all([sense, asset])
    session.flush()
    binding = m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="context",
                           review_status="approved", alt_native={})
    session.add(binding)
    session.flush()
    images.rescore(session, asset)
    assert sorted(asked) == ["surface", "wooden"]
    assert sorted(t["word"] for t in asset.tags) == ["children", "surface", "wooden"]
    assert asset.dropped_tags[0]["word"] == "wooden surface"
    assert binding.review_status == "approved", "children shows child"


def test_two_labelling_workers_never_take_the_same_picture(session, monkeypatch):
    """Several tags-lane workers run at once: a picture another worker holds
    is skipped and the next one is labelled instead."""
    from sqlalchemy import text
    from app import models as m
    first, second = (m.ImageAsset(source="wikimedia_commons", source_image_id=f"File:{n}.jpg",
                                  license_code="CC0", status="ready", path=f"{n}.jpg",
                                  tag_status="pending") for n in ("a", "b"))
    session.add_all([first, second])
    session.flush()
    labelled = []
    monkeypatch.setattr(images, "tag_asset", lambda s, asset_id: labelled.append(asset_id))
    with session.get_bind().connect() as other:  # another worker labelling the first picture
        other.execute(text("SELECT pg_advisory_lock(:k, :id)"), {"k": images.TAG_LOCK, "id": first.id})
        assert images.tag_pending(session) == 1
        other.execute(text("SELECT pg_advisory_unlock(:k, :id)"), {"k": images.TAG_LOCK, "id": first.id})
    assert labelled == [second.id]


def test_a_broken_model_server_leaves_pictures_waiting_not_failed(session, tmp_path, monkeypatch):
    """502 from the tagging service (its model server is down, or broken after
    the computer slept) isn't the picture's fault: it stays pending."""
    import io
    import urllib.error
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"jpeg")

    def bad_gateway(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 502, "Bad Gateway", {}, io.BytesIO(b""))

    monkeypatch.setattr(images.urllib.request, "urlopen", bad_gateway)
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:Q.jpg",
                         license_code="CC0", status="ready", path="a.jpg", tag_status="pending")
    session.add(asset)
    session.flush()
    assert images.tag_pending(session) == 0
    assert asset.tag_status == "pending"


# ── 問題回報 #3: Open Images, Smithsonian, Openverse join the fallback chain ──

def test_open_images_keeps_only_cc0_pd_and_cc_by_licences():
    allowed = ("https://creativecommons.org/publicdomain/zero/1.0/",
               "https://creativecommons.org/licenses/by/2.0/",
               "https://creativecommons.org/licenses/by/4.0/",
               "https://creativecommons.org/publicdomain/mark/1.0/")
    forbidden = ("https://creativecommons.org/licenses/by-sa/2.0/",
                 "https://creativecommons.org/licenses/by-nc/2.0/",
                 "https://creativecommons.org/licenses/by-nd/2.0/", "", None)
    assert [images._cc_code_from_url(u) for u in allowed] == ["CC0", "CC BY 2.0", "CC BY 4.0", "PUBLIC DOMAIN"]
    assert all(images._cc_code_from_url(u) is None for u in forbidden)


def test_openverse_keeps_only_cc0_pdm_and_by_slugs():
    assert images._cc_code_from_slug("cc0", None) == "CC0"
    assert images._cc_code_from_slug("pdm", None) == "PUBLIC DOMAIN"
    assert images._cc_code_from_slug("by", "4.0") == "CC BY 4.0"
    assert images._cc_code_from_slug("by", None) == "CC BY"
    for slug in ("by-sa", "by-nc", "by-nd", "by-nc-sa", "by-nc-nd", ""):
        assert images._cc_code_from_slug(slug, None) is None


def test_public_image_url_guard_rejects_private_and_internal_addresses(monkeypatch):
    import socket
    import pytest

    def fake_addrinfo(host, port, proto=0):
        ip = {"public.example": "93.184.216.34", "internal.example": "10.0.0.5",
             "metadata.example": "169.254.169.254", "loopback.example": "127.0.0.1"}[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(images.socket, "getaddrinfo", fake_addrinfo)
    assert images.check_public_image_url("https://public.example/a.jpg") == "https://public.example/a.jpg"
    for url in ("https://internal.example/a.jpg", "https://metadata.example/a.jpg",
                "https://loopback.example/a.jpg", "http://public.example/a.jpg",
                "https://user:pw@public.example/a.jpg", "https://public.example:81/a.jpg"):
        with pytest.raises(ValueError):
            images.check_public_image_url(url)


def test_search_smithsonian_keeps_only_cc0_media(session, monkeypatch):
    import json
    from app import models as m
    lx = m.Lexeme(language="en", lemma="cat", normalized="cat", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="cat", ordinal=0)
    session.add(sense)
    session.flush()
    payload = {"response": {"rows": [{"title": "cat toy", "content": {"descriptiveNonRepeating": {
        "title": {"content": "cat toy"}, "guid": "https://example/1", "data_source": "NMAH",
        "online_media": {"media": [
            {"id": "m1", "type": "Images", "usage": {"access": "CC0"},
             "content": "https://ids.si.edu/ids/deliveryService?id=m1"},
            {"id": "m2", "type": "Images", "usage": {"access": "Usage Conditions Apply"},
             "content": "https://ids.si.edu/ids/deliveryService?id=m2"},
        ]}}}}]}}
    monkeypatch.setattr(images, "fetch", lambda url, validate=None: json.dumps(payload).encode())
    out = images.search_smithsonian(session, sense.id, "cat")
    assert len(out) == 1, "only the CC0 media item"
    cand = session.get(m.ImageCandidate, out[0]["id"])
    assert cand.concept_id == "m1"
    assert cand.metadata_["license_code"] == "CC0"


def test_search_openverse_keeps_only_allowed_licenses(session, monkeypatch):
    import json
    from app import models as m
    lx = m.Lexeme(language="en", lemma="cat", normalized="cat", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="cat", ordinal=0)
    session.add(sense)
    session.flush()
    payload = {"results": [
        {"id": "ov1", "title": "cat", "license": "by", "license_version": "2.0",
         "url": "https://example.com/cat.jpg", "foreign_landing_url": "https://example.com/p/cat",
         "creator": "Someone", "tags": [{"name": "cat"}]},
        {"id": "ov2", "title": "cat (NC)", "license": "by-nc", "license_version": "2.0",
         "url": "https://example.com/cat2.jpg"},
    ]}
    monkeypatch.setattr(images, "fetch", lambda url, validate=None: json.dumps(payload).encode())
    out = images.search_openverse(session, sense.id, "cat")
    assert len(out) == 1, "by-nc is not on the allowed list"
    cand = session.get(m.ImageCandidate, out[0]["id"])
    assert cand.concept_id == "ov1"
    assert cand.metadata_["license_code"] == "CC BY 2.0"


def test_auto_fetch_falls_back_through_the_source_chain(session, monkeypatch):
    """問題回報 #3: wikimedia_commons alone used to be the only source ever
    tried; a sense it can't fill now goes on to open_images, smithsonian,
    then openverse, in the spec's order, until it has enough pictures."""
    from app import models as m
    monkeypatch.setattr(images, "wikidata", lambda params: {"search": []})  # Commons: no concept
    lx = m.Lexeme(language="en", lemma="gizmo", normalized="gizmo", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="gizmo", ordinal=0)
    session.add(sense)
    session.flush()
    session.add(m.Definition(sense_id=sense.id, language="en", text="a small device", source="test"))
    session.flush()

    tried = []

    def make_search(key, found):
        def inner(s, sense_id, lemma, gloss, native, ctx):
            tried.append(key)
            return [{"id": 42, "score": 0.9, "imported": False}] if found else []
        return inner

    def fake_ingest(s, candidate_id):
        asset = m.ImageAsset(source="smithsonian", source_image_id="m1", license_code="CC0", status="ready")
        s.add(asset)
        s.flush()
        binding = m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="representative",
                               review_status="pending", alt_native={})
        s.add(binding)
        s.flush()
        return {"id": binding.id, "status": "pending"}

    monkeypatch.setitem(images.IMAGE_SOURCES, "open_images", (make_search("open_images", False), fake_ingest))
    monkeypatch.setitem(images.IMAGE_SOURCES, "openverse", (make_search("openverse", True), fake_ingest))
    monkeypatch.setitem(images.IMAGE_SOURCES, "smithsonian", (make_search("smithsonian", False), fake_ingest))

    got = images.auto_fetch(session, "en", "zh-TW", "gizmo", per_sense=1)
    assert tried == ["open_images", "openverse"], "stops once the sense has enough pictures"
    assert got["images"] == 1


def test_run_fetch_flags_a_silent_zero_result_as_errors_not_plain_completed(session, monkeypatch):
    """常態卡 #3 (round 2): every source can come back with a plain empty
    result (no 429, no format rejection — just no candidate at all). That
    used to leave the task "completed" with no error, indistinguishable
    from a word that already has every picture it needs: invisible to any
    later scan, and never retried by enqueue_fetch (which only resets
    failed/completed_with_errors). It must surface as completed_with_errors
    with a descriptive error so both can find it again."""
    from app import models as m
    lx = m.Lexeme(language="en", lemma="zilch", normalized="zilch", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="zilch", ordinal=0)
    session.add(sense)
    session.flush()
    session.add(m.Definition(sense_id=sense.id, language="en", text="nothing at all", source="test"))
    task = m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="zilch",
                            fields=["sense_image"], status="queued")
    session.add(task)
    session.flush()

    monkeypatch.setattr(images, "auto_fetch",
                        lambda *a, **k: {"senses": 1, "images": 0, "errors": [], "incomplete_senses": 1})
    got = images.run_fetch(session, task.id)
    assert got["images"] == 0
    assert task.status == "completed_with_errors", \
        "a zero-result attempt must not look identical to a fully satisfied word"
    assert task.error, "the empty result needs a reason future scans and enqueue_fetch's retry check can see"


def test_run_fetch_still_completes_cleanly_when_every_sense_got_a_picture(session, monkeypatch):
    """The fix above must not flag a genuinely finished word."""
    from app import models as m
    lx = m.Lexeme(language="en", lemma="apple", normalized="apple", pos="noun", status="full")
    session.add(lx)
    session.flush()
    task = m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="apple",
                            fields=["sense_image"], status="queued")
    session.add(task)
    session.flush()

    monkeypatch.setattr(images, "auto_fetch",
                        lambda *a, **k: {"senses": 1, "images": 3, "errors": [], "incomplete_senses": 0})
    images.run_fetch(session, task.id)
    assert task.status == "completed"
    assert task.error is None


def test_run_fetch_backs_off_and_requeues_on_persistent_rate_limit(session, monkeypatch):
    """卡 #99 (root cause from #98): a source still answering 429/503 past
    fetch()'s own retries must never be counted completed/completed_with_errors
    — that hides the gap from every future scan instead of retrying it. It
    must go back to "queued" with a future retry_at (backoff), not be
    flagged failed either."""
    from app import models as m
    lx = m.Lexeme(language="en", lemma="dodo", normalized="dodo", pos="noun", status="full")
    session.add(lx)
    session.flush()
    task = m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="dodo",
                            fields=["sense_image"], status="queued", attempts=1)
    session.add(task)
    session.flush()

    monkeypatch.setattr(images, "auto_fetch", lambda *a, **k: {
        "senses": 1, "images": 0, "errors": ["smithsonian 詞義 #1：HTTP Error 429: Too Many Requests"],
        "incomplete_senses": 1, "rate_limited": True})
    before = images.datetime.now(images.timezone.utc)
    got = images.run_fetch(session, task.id)
    assert got["images"] == 0
    assert task.status == "queued", "a persistent rate limit must requeue, not complete"
    assert task.retry_at is not None and task.retry_at > before, \
        "must back off before the next claim, not retry immediately"
    assert task.finished_at is None, "still pending — not a finished run"


def test_run_fetch_does_not_requeue_when_rate_limit_was_covered_by_another_source(session, monkeypatch):
    """A 429 hiccup on one source that another source still covered leaves
    every sense with a picture: that is a real completion, not a loop."""
    from app import models as m
    lx = m.Lexeme(language="en", lemma="moa", normalized="moa", pos="noun", status="full")
    session.add(lx)
    session.flush()
    task = m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="moa",
                            fields=["sense_image"], status="queued")
    session.add(task)
    session.flush()

    monkeypatch.setattr(images, "auto_fetch", lambda *a, **k: {
        "senses": 1, "images": 1, "errors": ["smithsonian 詞義 #1：HTTP Error 429: Too Many Requests"],
        "incomplete_senses": 0, "rate_limited": True})
    images.run_fetch(session, task.id)
    assert task.status == "completed", "every sense already has its picture — a real completion"
    assert task.retry_at is None


def test_claim_fetch_skips_a_task_still_in_backoff(session, monkeypatch):
    """claim_fetch must not immediately re-pick a task a worker just backed
    off (卡 #99), or the backoff is pointless and the source gets hit again
    right away."""
    from datetime import timedelta
    from app import models as m
    future = m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="waiting",
                              fields=["sense_image"], status="queued",
                              retry_at=images.datetime.now(images.timezone.utc) + timedelta(minutes=30))
    ready = m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="ready",
                             fields=["sense_image"], status="queued")
    session.add_all([future, ready])
    session.flush()

    claimed = images.claim_fetch(session, "worker-1")
    assert claimed is not None and claimed.lemma == "ready", \
        "the task still in backoff must not be claimed before its retry_at"


def test_claim_fetch_fresh_words_before_retried_and_languages_alternate(session):
    """問題回報 #338: words that keep returning 429 must not sit ahead of
    never-tried ones, and one language's backlog must not starve another."""
    from app import models as m
    def task(lemma, lang="en", attempts=0, started=None):
        return m.ImageFetchTask(target_language=lang, native_language="zh-TW", lemma=lemma,
                                fields=["sense_image"], status="queued", attempts=attempts,
                                started_at=started)
    now = images.datetime.now(images.timezone.utc)
    session.add_all([task("old429", attempts=30), task("fresh_en"),
                     task("fresh_fr", lang="fr")])
    session.add(m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="done_en",
                                 fields=["sense_image"], status="completed", started_at=now))
    session.flush()
    first = images.claim_fetch(session, "w1")
    assert first.lemma == "fresh_fr", "last run was en, so fr goes next"
    second = images.claim_fetch(session, "w1")
    assert second.lemma == "fresh_en"
    third = images.claim_fetch(session, "w1")
    assert third.lemma == "old429", "retried words come after never-tried ones"


def test_auto_fetch_flags_persistent_429_as_rate_limited_not_a_plain_error(session, monkeypatch):
    """A source raising the same HTTPError fetch() gives up on after its own
    retries (429/503) must be distinguished from an ordinary ValueError/
    no-candidate result, so run_fetch knows to back off instead of
    completing (卡 #99)."""
    import urllib.error
    from app import models as m
    monkeypatch.setattr(images, "wikidata", lambda params: {"search": []})
    lx = m.Lexeme(language="en", lemma="dodo", normalized="dodo", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="dodo", ordinal=0)
    session.add(sense)
    session.flush()
    session.add(m.Definition(sense_id=sense.id, language="en", text="an extinct bird", source="test"))
    session.flush()

    def rate_limited_search(s, sense_id, lemma, gloss, native, ctx):
        raise urllib.error.HTTPError("https://api.si.edu/x", 429, "Too Many Requests", {}, None)

    def empty_search(s, sense_id, lemma, gloss, native, ctx):
        return []

    monkeypatch.setitem(images.IMAGE_SOURCES, "open_images", (empty_search, None))
    monkeypatch.setitem(images.IMAGE_SOURCES, "smithsonian", (rate_limited_search, None))
    monkeypatch.setitem(images.IMAGE_SOURCES, "openverse", (empty_search, None))

    got = images.auto_fetch(session, "en", "zh-TW", "dodo", per_sense=1)
    assert got["rate_limited"] is True
    assert got["incomplete_senses"] == 1


def test_enabled_image_sources_honors_policy_order_and_disabled_steps(session):
    from sqlalchemy import select
    from app import models as m
    policy = session.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == "en", m.SourcePolicy.native_language == "zh-TW",
        m.SourcePolicy.field == "sense_image")).scalar_one()
    steps = {st.source: st for st in session.execute(select(m.SourcePolicyStep).where(
        m.SourcePolicyStep.policy_id == policy.id)).scalars()}
    steps["wikimedia_commons"].enabled = False
    steps["openverse"].position, steps["smithsonian"].position = \
        steps["smithsonian"].position, steps["openverse"].position
    session.flush()
    assert images._enabled_image_sources(session, "en", "zh-TW") == [
        "open_images", "smithsonian", "openverse"]


def test_seed_moves_smithsonian_last_only_in_untouched_image_chains(session):
    # 問題回報 #375: the old default order gets Smithsonian last; an order the
    # admin chose is left alone.
    from sqlalchemy import select
    from app import models as m, policies

    def chain(field):
        p = session.execute(select(m.SourcePolicy).where(
            m.SourcePolicy.target_language == "en", m.SourcePolicy.native_language == "zh-TW",
            m.SourcePolicy.field == field)).scalar_one()
        return p, {st.source: st for st in policies.steps_of(session, p)}

    old = ["wikimedia_commons", "open_images", "smithsonian", "openverse"]
    p, steps = chain("sense_image")
    for i, src in enumerate(old):
        steps[src].position = (i + 1) * 1000
    q, custom = chain("thumbnail")
    for i, src in enumerate(["smithsonian", "wikimedia_commons", "open_images", "openverse"]):
        custom[src].position = (i + 1) * 1000
    session.flush()
    version = p.version
    assert policies.reorder_untouched_chains(session) >= 1
    assert [st.source for st in policies.steps_of(session, p)] == [
        "wikimedia_commons", "open_images", "openverse", "smithsonian"]
    assert p.version == version
    assert [st.source for st in policies.steps_of(session, q)][0] == "smithsonian"
    assert policies.reorder_untouched_chains(session) == 0


def test_enabled_image_sources_defaults_to_the_full_chain_when_no_policy_exists(session):
    assert images._enabled_image_sources(session, "xx", "yy") == list(images.IMAGE_SOURCE_CHAIN)


def _queued_task(lemma, **kwargs):
    from app import models as m
    data = dict(target_language="en", native_language="zh-TW", lemma=lemma,
                fields=["sense_image"], status="queued")
    data.update(kwargs)
    return m.ImageFetchTask(**data)


def test_concept_search_label_falls_back_past_a_missing_english_label():
    assert images._concept_search_label({"labels": {"en": {"value": "walnut"}}}, lemma="nut") == "walnut"
    assert images._concept_search_label(
        {"labels": {"ja": {"value": "胡桃"}}, "aliases": {"en": [{"value": "English walnut"}]}},
        lemma="walnut") == "English walnut"
    assert images._concept_search_label({"labels": {"ja": {"value": "胡桃"}}}, lemma="walnut") == "walnut"
    assert images._concept_search_label({"labels": {"ja": {"value": "胡桃"}}}) == "胡桃"
    assert images._concept_search_label({"aliases": {"de": [{"value": "Walnuss"}]}}) == "Walnuss"
    assert images._concept_search_label({}) is None


def test_search_uses_the_word_when_the_concept_has_no_english_label(session, monkeypatch):
    import json
    from app import models as m
    lx = m.Lexeme(language="en", lemma="walnut", normalized="walnut", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="walnut", ordinal=0)
    session.add(sense)
    session.flush()
    seen = {}

    def fake_fetch(url, limit=images.MAX_BYTES, validate=None):
        body = {"entities": {"Q1": {
            "labels": {"ja": {"value": "胡桃"}},
            "aliases": {},
            "claims": {"P18": [{"mainsnak": {"datavalue": {"value": "Walnut.jpg"}}}]},
        }}}
        return json.dumps(body).encode()

    def fake_commons(params):
        if params.get("list") == "search":
            seen["q"] = params["srsearch"]
            return {"query": {"search": []}}
        return {"query": {"pages": {}}}

    monkeypatch.setattr(images, "fetch", fake_fetch)
    monkeypatch.setattr(images, "commons", fake_commons)
    out = images.search(session, sense.id, "Q1", lemma="walnut")
    assert seen["q"].startswith("walnut")
    assert out["concept"] == "walnut"


def test_search_is_a_permanent_failure_without_any_label_or_picture(session, monkeypatch):
    import pytest
    from app import models as m
    lx = m.Lexeme(language="en", lemma="nolabel", normalized="nolabel", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="nolabel", ordinal=0)
    session.add(sense)
    session.flush()
    monkeypatch.setattr(images, "fetch", lambda url, limit=images.MAX_BYTES, validate=None: (
        b'{"entities":{"Q2":{"labels":{},"aliases":{},"claims":{}}}}'))
    with pytest.raises(ValueError, match="沒有任何語言標籤"):
        images.search(session, sense.id, "Q2")


def test_normalize_card_bytes_converts_gif_and_rejects_a_short_side():
    import io
    import pytest
    from PIL import Image
    gif = io.BytesIO()
    Image.new("RGB", (160, 180), "red").save(gif, "GIF")
    converted = images._normalize_card_bytes(gif.getvalue())
    with Image.open(io.BytesIO(converted)) as im:
        assert im.format == "JPEG"
        assert min(im.size) >= 120
    tiny = io.BytesIO()
    Image.new("RGB", (40, 80), "blue").save(tiny, "JPEG")
    with pytest.raises(ValueError, match="短邊不足"):
        images._normalize_card_bytes(tiny.getvalue())


def test_normalize_card_bytes_shrinks_an_oversized_png_instead_of_rejecting_it():
    import io
    from PIL import Image
    png = io.BytesIO()
    Image.new("RGB", (200, 200), "green").save(png, "PNG")
    converted = images._normalize_card_bytes(png.getvalue(), max_pixels=10_000, min_side=40)
    with Image.open(io.BytesIO(converted)) as im:
        assert im.format == "PNG"
        assert im.width * im.height <= 10_000
        assert min(im.size) >= 40


def test_run_fetch_requeues_a_timeout_instead_of_completing_with_errors(session, monkeypatch):
    task = _queued_task("fruity", attempts=1)
    session.add(task)
    session.flush()
    monkeypatch.setattr(images, "auto_fetch", lambda *a, **k: {
        "senses": 1, "images": 0,
        "errors": ["openverse 詞義 #1：The read operation timed out"],
        "incomplete_senses": 1, "timed_out": True, "transient": True})
    before = images.datetime.now(images.timezone.utc)
    images.run_fetch(session, task.id)
    assert task.status == "queued"
    assert task.retry_at is not None and task.retry_at > before
    assert task.finished_at is None


def test_run_fetch_timeout_stops_as_failed_after_the_attempt_cap(session, monkeypatch):
    task = _queued_task("huddle", attempts=images.TRANSIENT_ATTEMPT_CAP)
    session.add(task)
    session.flush()
    monkeypatch.setattr(images, "auto_fetch", lambda *a, **k: {
        "senses": 1, "images": 0, "errors": ["openverse：timed out"],
        "incomplete_senses": 1, "timed_out": True})
    images.run_fetch(session, task.id)
    assert task.status == "failed"
    assert task.error.startswith("暫時性錯誤重試已達上限")
    assert task.retry_at is None


def test_run_fetch_marks_an_unconvertible_picture_as_a_permanent_failure(session, monkeypatch):
    task = _queued_task("sodium")
    session.add(task)
    session.flush()
    monkeypatch.setattr(images, "auto_fetch", lambda *a, **k: {
        "senses": 1, "images": 0,
        "errors": ["smithsonian #4：圖片格式或尺寸不適合字卡：短邊不足"],
        "incomplete_senses": 1, "permanent": True})
    images.run_fetch(session, task.id)
    assert task.status == "failed"
    assert task.error.startswith("永久失敗")
    assert "短邊不足" in task.error


def test_auto_fetch_flags_a_timeout_and_a_format_dead_end(session, monkeypatch):
    from app import models as m
    monkeypatch.setattr(images, "wikidata", lambda params: {"search": []})
    lx = m.Lexeme(language="en", lemma="iota", normalized="iota", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="iota", ordinal=0)
    session.add(sense)
    session.flush()
    session.add(m.Definition(sense_id=sense.id, language="en", text="a letter", source="test"))

    def empty(s, sense_id, lemma, gloss, native, ctx):
        return []

    def timed_out(s, sense_id, lemma, gloss, native, ctx):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setitem(images.IMAGE_SOURCES, "open_images", (empty, None))
    monkeypatch.setitem(images.IMAGE_SOURCES, "smithsonian", (timed_out, None))
    monkeypatch.setitem(images.IMAGE_SOURCES, "openverse", (empty, None))
    got = images.auto_fetch(session, "en", "zh-TW", "iota", per_sense=1)
    assert got["timed_out"] is True and got["transient"] is True
    assert got["permanent"] is False

    def too_small(s, sense_id, lemma, gloss, native, ctx):
        raise ValueError("圖片格式或尺寸不適合字卡：短邊不足")

    monkeypatch.setitem(images.IMAGE_SOURCES, "smithsonian", (too_small, None))
    got = images.auto_fetch(session, "en", "zh-TW", "iota", per_sense=1)
    assert got["permanent"] is True
    assert got["timed_out"] is False


def test_claim_fetch_takes_requeue_before_an_older_queued_word(session):
    """Rejected-picture refetches must not wait behind the missing-picture backlog."""
    from datetime import timedelta
    now = images.datetime.now(images.timezone.utc)
    session.add_all([
        _queued_task("older", created_at=now - timedelta(days=5)),
        _queued_task("blister", status="requeue", search_query="blister small",
                     created_at=now),
    ])
    session.flush()
    claimed = images.claim_fetch(session, "worker-claim")
    assert claimed is not None and claimed.lemma == "blister"
    assert claimed.status == "running"


def test_claim_fetch_takes_a_stale_running_task_before_an_older_queued_one(session):
    from datetime import timedelta
    now = images.datetime.now(images.timezone.utc)
    session.add_all([
        _queued_task("older", created_at=now - timedelta(days=5)),
        _queued_task("door", status="running", created_at=now - timedelta(days=1),
                     started_at=now - timedelta(minutes=30), worker_id="not-a-live-worker"),
    ])
    session.flush()
    claimed = images.claim_fetch(session, "worker-claim")
    assert claimed is not None and claimed.lemma == "door"


def test_claim_fetch_takes_a_dead_worker_before_the_stale_window(session, monkeypatch):
    from datetime import timedelta
    now = images.datetime.now(images.timezone.utc)
    monkeypatch.setattr(images, "_worker_process_gone", lambda worker_id: worker_id == "gone-worker")
    session.add_all([
        _queued_task("older", created_at=now - timedelta(days=5)),
        _queued_task("doorway", status="running", created_at=now,
                     started_at=now, worker_id="gone-worker"),
    ])
    session.flush()
    claimed = images.claim_fetch(session, "worker-claim")
    assert claimed is not None and claimed.lemma == "doorway"


def test_claim_fetch_leaves_a_live_running_task_and_prefers_a_word_with_no_picture(session, monkeypatch):
    from datetime import timedelta
    from app import models as m
    now = images.datetime.now(images.timezone.utc)
    monkeypatch.setattr(images, "_worker_process_gone", lambda worker_id: False)
    lx = m.Lexeme(language="en", lemma="pictured", normalized="pictured", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="pictured", ordinal=0)
    session.add(sense)
    session.flush()
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:pictured.jpg", license_code="CC0")
    session.add(asset)
    session.flush()
    session.add(m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="representative",
                             review_status="pending"))
    session.add_all([
        _queued_task("pictured", created_at=now - timedelta(days=3)),
        _queued_task("bareword", created_at=now - timedelta(hours=1)),
        _queued_task("live", status="running", created_at=now - timedelta(days=4),
                     started_at=now, worker_id="still-working"),
    ])
    session.flush()
    claimed = images.claim_fetch(session, "worker-claim")
    assert claimed is not None and claimed.lemma == "bareword"
