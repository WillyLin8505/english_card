"""#331: a French word's pictures are judged by its sense's English meaning
(labels are English): chat → cat, maison → house."""

from app import images


def _fr_word(session, m, lemma, meaning, zh=None):
    lx = m.Lexeme(language="fr", lemma=lemma, normalized=lemma, pos="noun", status="full")
    session.add(lx)
    session.flush()
    se = m.Sense(lexeme_id=lx.id, sense_key=f"fr-{lemma}", ordinal=0)
    session.add(se)
    session.flush()
    if meaning:
        session.add(m.SenseTranslation(sense_id=se.id, native_language="en", text=meaning,
                                       source="kaikki"))
    session.flush()
    return se


def _asset(session, m, tmp_path, words, name):
    path = tmp_path / f"{name}.jpg"
    path.write_bytes(b"x")
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id=f"File:{name}.jpg",
                         license_code="CC0", status="ready", tag_status="done",
                         safety_status="safe", path=path.name,
                         tags=[{"word": w, "pos": "noun", "score": 0.9} for w in words])
    session.add(asset)
    session.flush()
    return asset


def test_label_word_is_the_english_meaning(session):
    from app import models as m
    se = _fr_word(session, m, "chat", "cat (feline)")
    assert images.label_word(session, se.id, "fr", "chat") == "cat"
    assert images.label_word(session, se.id, "en", "chat") == "chat"
    bare = _fr_word(session, m, "truc", None)
    assert images.label_word(session, bare.id, "fr", "truc") is None


def test_judge_and_auto_accept_use_the_english_meaning(session, tmp_path, monkeypatch):
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    cat = _fr_word(session, m, "chat", "cat (feline)")
    house = _fr_word(session, m, "maison", "house")
    shown = _asset(session, m, tmp_path, ["cat", "fur", "nose", "eye"], "cat")
    other = _asset(session, m, tmp_path, ["vase", "cupboard", "display"], "vase")
    good = m.SenseImage(sense_id=cat.id, image_asset_id=shown.id, role="representative",
                        review_status="pending", semantic_score=0.8, alt_native={})
    bad = m.SenseImage(sense_id=house.id, image_asset_id=other.id, role="representative",
                       review_status="pending", semantic_score=0.8, alt_native={})
    session.add_all([good, bad])
    session.flush()
    images.judge(session, good, shown, "chat", "fr")
    images.judge(session, bad, other, "maison", "fr")
    assert good.semantic_score == 0.95 and good.review_status == "pending"
    assert bad.review_status == "rejected", "labels do not name house"
    note = session.query(m.ImageReview).filter_by(sense_image_id=bad.id).one().note
    assert "house（maison）" in note
    assert "cat" in images.own_words(session, shown)
    # Two more approved words on the picture reach the 3-word floor.
    for w in ("fur", "nose"):
        en = m.Lexeme(language="en", lemma=w, normalized=w, pos="noun", status="full")
        session.add(en)
        session.flush()
        sense = m.Sense(lexeme_id=en.id, sense_key=w, ordinal=0)
        session.add(sense)
        session.flush()
        session.add(m.SenseImage(sense_id=sense.id, image_asset_id=shown.id, role="context",
                                 review_status="approved", semantic_score=0.9, alt_native={}))
    session.flush()
    assert images.auto_accept_asset(session, shown) == 1
    assert good.review_status == "approved"
    note = session.query(m.ImageReview).filter_by(sense_image_id=good.id).one().note
    assert "cat（chat）" in note


def test_a_sense_without_english_meaning_is_left_for_review(session, tmp_path):
    from app import models as m
    se = _fr_word(session, m, "truc", None)
    asset = _asset(session, m, tmp_path, ["thing", "table"], "thing")
    b = m.SenseImage(sense_id=se.id, image_asset_id=asset.id, role="context",
                     review_status="pending", semantic_score=0.8, alt_native={})
    session.add(b)
    session.flush()
    images.judge(session, b, asset, "truc", "fr")
    assert b.review_status == "pending"


def test_share_existing_skips_a_french_headword(session):
    assert images.share_existing(session, "fr", "chat") == 0


def _en_sense(session, m, word):
    en = m.Lexeme(language="en", lemma=word, normalized=word, pos="noun", status="full")
    session.add(en)
    session.flush()
    sense = m.Sense(lexeme_id=en.id, sense_key=f"en-{word}", ordinal=0)
    session.add(sense)
    session.flush()
    return sense


def _approve(session, m, sense, asset):
    session.add(m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="context",
                             review_status="approved", semantic_score=0.9, alt_native={}))
    session.flush()


def test_share_existing_reuses_pictures_by_english_meaning(session, tmp_path, monkeypatch):
    """#336: chat reuses pictures approved for cat, not ones only labelled
    chat (the English word) or labelled cat but never approved."""
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    cat = _fr_word(session, m, "chat", "cat (feline)")
    _fr_word(session, m, "fourrure", "fur")  # the French pack names fur and nose too (#368)
    _fr_word(session, m, "nez", "nose")
    pics = [_asset(session, m, tmp_path, ["cat", "fur", "nose", "eye"], f"cat{i}") for i in range(4)]
    en_cat, fur, nose = (_en_sense(session, m, w) for w in ("cat", "fur", "nose"))
    for p in pics:
        _approve(session, m, fur, p)
        _approve(session, m, nose, p)
    for p in pics[:3]:  # pics[3] is labelled cat but not approved for cat
        _approve(session, m, en_cat, p)
    unapproved = pics[3]
    english_chat = _asset(session, m, tmp_path, ["chat", "phone", "screen"], "chat_en")
    session.flush()
    assert images.share_existing(session, "fr", "chat", per_sense=4) == 3
    got = session.query(m.SenseImage).filter_by(sense_id=cat.id).order_by(m.SenseImage.ordinal).all()
    assert [b.image_asset_id for b in got] == [p.id for p in pics[:3]]
    assert got[0].role == "representative" and all(b.role == "context" for b in got[1:])
    assert all(b.review_status == "approved" for b in got), "auto_accept_asset approved them"
    assert unapproved.id not in {b.image_asset_id for b in got}
    assert english_chat.id not in {b.image_asset_id for b in got}
    # Already full: nothing more is added.
    assert images.share_existing(session, "fr", "chat", per_sense=3) == 0


def test_share_by_meaning_uses_only_english_noun_primary_senses(session, tmp_path, monkeypatch):
    """#336: garde → watch reuses a wristwatch approved for the noun, not a
    picture approved for the verb watch or for a later noun sense."""
    from app import config, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    monkeypatch.setattr(images, "SHARE_MIN_LABELS", 1)  # only the sense choice is tested here
    garde = _fr_word(session, m, "garde", "watch")
    noun, verb_pic, late_pic = (_asset(session, m, tmp_path, ["watch", "wrist"], f"w{i}") for i in range(3))
    _approve(session, m, _en_sense(session, m, "watch"), noun)
    verb = m.Lexeme(language="en", lemma="watch", normalized="watch", pos="verb", status="full")
    session.add(verb)
    session.flush()
    verb_sense = m.Sense(lexeme_id=verb.id, sense_key="en-watch-v", ordinal=0)
    late = m.Sense(lexeme_id=verb.id, sense_key="en-watch-n5", ordinal=5)
    session.add_all([verb_sense, late])
    session.flush()
    _approve(session, m, verb_sense, verb_pic)
    late.lexeme_id = session.query(m.Lexeme).filter_by(language="en", normalized="watch", pos="noun").one().id
    session.flush()
    _approve(session, m, late, late_pic)
    assert images.share_existing(session, "fr", "garde", per_sense=3) == 1
    got = {b.image_asset_id for b in session.query(m.SenseImage).filter_by(sense_id=garde.id)}
    assert got == {noun.id}


def test_share_by_meaning_skips_a_picture_with_fewer_than_3_french_labels(session, tmp_path, monkeypatch):
    """#368: the French pack shows a picture's French words only; a cat photo
    whose other approved English words have no French entry would show just
    chat, so it is not shared. Once fourrure and nez exist it is."""
    from app import config, models as m
    from app.meaning_labels import pack_label_words
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    cat = _fr_word(session, m, "chat", "cat (feline)")
    pic = _asset(session, m, tmp_path, ["cat", "fur", "nose"], "lonely_cat")
    for word in ("cat", "fur", "nose"):
        _approve(session, m, _en_sense(session, m, word), pic)
    assert images.share_existing(session, "fr", "chat", per_sense=3) == 0
    assert not session.query(m.SenseImage).filter_by(sense_id=cat.id).count()
    fur = _fr_word(session, m, "fourrure", "fur")
    assert images.share_existing(session, "fr", "chat", per_sense=3) == 0
    assert not session.query(m.SenseImage).filter_by(sense_id=cat.id).count()
    nose = _fr_word(session, m, "nez", "nose")
    # chat already names the picture by meaning (cat); now fur and nose too.
    assert pack_label_words(session, "fr", pic.id) == {cat.lexeme_id, fur.lexeme_id, nose.lexeme_id}
    assert images.share_existing(session, "fr", "chat", per_sense=3) == 1
    assert pack_label_words(session, "fr", pic.id) == {cat.lexeme_id, fur.lexeme_id, nose.lexeme_id}


def test_meaning_cache_refreshes_after_existing_translation_edit(session, tmp_path):
    from app import models as m
    from app.meaning_labels import pack_label_words
    cat = _fr_word(session, m, "chat", "cat")
    pic = _asset(session, m, tmp_path, ["cat", "fur", "nose"], "edited_meaning")
    _approve(session, m, _en_sense(session, m, "cat"), pic)
    assert pack_label_words(session, "fr", pic.id) == {cat.lexeme_id}
    translation = session.query(m.SenseTranslation).filter_by(sense_id=cat.id).one()
    translation.text = "dog"
    session.flush()
    assert pack_label_words(session, "fr", pic.id) == set()


def test_projected_labels_match_pack_with_competing_meanings(session, tmp_path, monkeypatch):
    import serve_app
    from app import models as m, sense_order
    from app.meaning_labels import pack_label_words
    default = _fr_word(session, m, "plaque", "plate")
    specific = _fr_word(session, m, "assiette", "plate")
    table = _fr_word(session, m, "table", "table")
    plate = _en_sense(session, m, "plate")
    session.add(m.Definition(sense_id=plate.id, language="en", text="A dish for food.", source="kaikki"))
    pic = _asset(session, m, tmp_path, ["plate", "table", "food"], "rival_plate")
    _approve(session, m, plate, pic)
    _approve(session, m, _en_sense(session, m, "table"), pic)
    monkeypatch.setattr(sense_order, "english_sense_translations", lambda *a: {"assiette"})
    projected = pack_label_words(session, "fr", pic.id, specific.lexeme_id)
    _approve(session, m, specific, pic)
    _, catalog = serve_app.catalog_snapshot(session, "fr")
    actual = {t['lexeme_id'] for p in catalog if p['id'] == pic.id for t in p['tags']}
    assert projected == actual == {default.lexeme_id, specific.lexeme_id, table.lexeme_id}
