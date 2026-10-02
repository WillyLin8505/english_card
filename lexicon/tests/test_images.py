"""Matching a sense to its Wikidata concept, on recorded answers (no network)."""

from app import images

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
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:Bench.jpg",
                         license_code="CC0", status="ready", tag_status="done",
                         tags=[{"word": "bench", "pos": "noun"}, {"word": "gravel", "pos": "noun"},
                               {"word": "shadow", "pos": "noun"}])
    session.add(asset)
    session.flush()
    session.add(m.SenseImage(sense_id=senses["bench"].id, image_asset_id=asset.id,
                             role="representative", review_status="approved", alt_native={}))
    session.flush()
    assert images.share(session, asset) == 1  # gravel; shadow is no entry
    got = session.query(m.SenseImage).filter_by(sense_id=senses["gravel"].id).one()
    assert got.review_status == "approved", "a reviewed picture is approved for the other word too"
    assert images.share(session, asset) == 0, "never twice"


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


def test_old_labels_are_scored_first_and_short_pictures_wait_for_more_looks(session, tmp_path, monkeypatch):
    import io
    import json
    from urllib.parse import parse_qs, urlsplit
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"jpeg")

    def fake_urlopen(request, timeout=0):
        labels = json.loads(parse_qs(urlsplit(request.full_url).query)["labels"][0])
        return io.BytesIO(json.dumps({"scores": [
            {"word": x["word"], "score": 0.1 if x["word"].startswith("x") else 0.9}
            for x in labels]}).encode())

    monkeypatch.setattr(images.urllib.request, "urlopen", fake_urlopen)
    many = m.ImageAsset(source="wikimedia_commons", source_image_id="File:M.jpg", license_code="CC0",
                        status="ready", path="a.jpg", tag_status="pending",
                        tags=[{"word": w, "pos": "noun", "point": [0.5, 0.5]}
                              for w in "a b c d e f g h xi".split()])
    few = m.ImageAsset(source="wikimedia_commons", source_image_id="File:F.jpg", license_code="CC0",
                       status="ready", path="a.jpg", tag_status="pending",
                       tags=[{"word": w, "pos": "noun", "point": [0.5, 0.5]} for w in ("a", "xb")])
    session.add_all([many, few])
    session.flush()
    assert images.tag_pending(session, limit=5) == 2
    assert many.tag_status == "done" and len(many.tags) == 8 and many.dropped_tags[0]["word"] == "xi"
    assert few.tag_status == "pending", "fewer than 8 pass: more looks later"
    assert [t["score"] for t in few.tags] == [0.9] and few.dropped_tags[0]["score"] == 0.1


def test_tag_asset_defaults_to_cefr_mode(session, tmp_path, monkeypatch):
    """Import/tag pipeline uses one mode=cefr call (~3 per A1–C2), not TAG_LOOKS."""
    import io
    import json
    from urllib.parse import parse_qs, urlsplit
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    monkeypatch.setattr(images, "TAG_MODE", "cefr")
    monkeypatch.setattr(images, "DEFER_TAG_SCORE", False)
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
            body = {"model": "vision", "candidates": [
                {"word": "lake", "pos": "noun", "cefr": "A2", "point": [0.4, 0.5]},
                {"word": "forest", "pos": "noun", "cefr": "B1", "point": [0.6, 0.5]},
            ]}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(images.urllib.request, "urlopen", fake_urlopen)
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:C.jpg",
                         license_code="CC0", status="ready", path="a.jpg")
    session.add(asset)
    session.flush()
    images.tag_asset(session, asset.id)
    assert seen_modes == ["cefr"]
    assert [t["word"] for t in asset.tags] == ["lake", "forest"]
    assert asset.tags[0].get("cefr") == "A2"
