"""Card #167: photo labels bind through one policy (base form, generic, synonym)."""
from pathlib import Path

from app import models as m
from app import images


def _lexeme(session, lemma, pos="noun", status="full"):
    row = m.Lexeme(language="en", lemma=lemma, normalized=lemma, pos=pos, status=status,
                   cefr="A1")
    session.add(row)
    session.flush()
    session.add(m.Sense(lexeme_id=row.id, sense_key=lemma, ordinal=0))
    session.flush()
    return row


def _asset(session, words, dropped=None, **tag_extra):
    tags = [{"word": word, "pos": "noun", "cefr": "A1", "score": 0.95, **tag_extra}
            for word in words]
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id=f"File:{words[0]}.jpg",
                         license_code="CC0", status="ready", tag_status="done",
                         safety_status="safe", tags=tags, dropped_tags=dropped or [])
    session.add(asset)
    session.flush()
    return asset


def _skip(asset, word):
    return next(tag.get("bindSkip") for tag in asset.tags if tag["word"] == word)


def test_an_inflection_binds_to_the_full_base(session):
    hold = _lexeme(session, "hold", pos="verb")
    asset = _asset(session, ["holding", "shadow"])
    assert images.share(session, asset) == 1
    binding = session.query(m.SenseImage).join(m.Sense).filter_by(lexeme_id=hold.id).one()
    assert binding.review_status == "pending"
    assert _skip(asset, "shadow") == "查無詞條"
    assert images.share(session, asset) == 0


def test_backfill_does_not_publish_a_sense_without_chinese(session):
    _lexeme(session, "hold", pos="verb")
    bench = _lexeme(session, "bench")
    asset = _asset(session, ["holding", "bench"])
    sense = session.query(m.Sense).filter_by(lexeme_id=bench.id).one()
    session.add(m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="context",
                             review_status="approved", alt_native={}))
    session.flush()
    assert images.share(session, asset, require_publishable=True) == 0
    assert _skip(asset, "holding") == "沒有可顯示的義項"


def test_a_stub_is_recorded_and_not_bound(session):
    _lexeme(session, "intricate", pos="adj", status="stub")
    asset = _asset(session, ["intricate"])
    assert images.share(session, asset) == 0
    assert _skip(asset, "intricate") == "只有 stub"


def test_generic_and_synonym_labels_are_not_bound(session):
    _lexeme(session, "stone")
    _lexeme(session, "rock")
    _lexeme(session, "surface")
    asset = _asset(session, ["stone", "rock", "surface"])
    assert images.share(session, asset) == 1
    words = {row[0] for row in session.query(m.Lexeme.normalized).join(m.Sense).join(m.SenseImage)}
    assert words == {"stone"}
    assert _skip(asset, "rock") == "近義重複"
    assert _skip(asset, "surface") == "泛用字"


def test_representative_needs_a_subject_box_and_confidence(session):
    noun = _lexeme(session, "bowl")
    asset = _asset(session, ["bowl"], box=[0.1, 0.1, 0.7, 0.8], visualConfidence=0.9)
    images.share(session, asset)
    binding = session.query(m.SenseImage).join(m.Sense).filter_by(lexeme_id=noun.id).one()
    assert binding.role == "representative"
    tiny = _asset(session, ["bowl"], box=[0.48, 0.58, 0.52, 0.62], visualConfidence=0.7)
    tiny.source_image_id = "File:bowl-tiny.jpg"
    session.flush()
    images.share(session, tiny)
    other = session.query(m.SenseImage).filter_by(image_asset_id=tiny.id).one()
    assert other.role == "context"


def test_rebind_drops_a_generic_label_when_three_words_remain(session):
    words = {w: _lexeme(session, w) for w in ("bench", "gravel", "tree", "surface")}
    asset = _asset(session, ["bench", "gravel", "tree", "surface"])
    for lemma, row in words.items():
        sense = session.query(m.Sense).filter_by(lexeme_id=row.id).one()
        session.add(m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="context",
                                 review_status="approved", alt_native={}))
    session.flush()
    result = images.rebind_asset(session, asset)
    assert result["generic"] == 1
    still = {row[0] for row in session.query(m.Lexeme.normalized).join(m.Sense).join(
        m.SenseImage).filter(m.SenseImage.review_status == "approved",
                             m.SenseImage.image_asset_id == asset.id)}
    assert still == {"bench", "gravel", "tree"}


def test_a_representative_without_the_word_is_demoted(session):
    noun = _lexeme(session, "cloud")
    sense = session.query(m.Sense).filter_by(lexeme_id=noun.id).one()
    asset = _asset(session, ["sky"])
    session.add(m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="representative",
                             review_status="approved", alt_native={}))
    session.flush()
    assert images.demote_unmentioned_representatives(session) == 1
    binding = session.query(m.SenseImage).one()
    assert binding.role == "context"


def test_relevance_queue_rejects_only_when_tagging_is_idle(session, tmp_path, monkeypatch):
    noun = _lexeme(session, "rosemary")
    sense = session.query(m.Sense).filter_by(lexeme_id=noun.id).one()
    asset = _asset(session, ["rosemary"])
    binding = m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="context",
                           review_status="approved", alt_native={})
    session.add(binding)
    session.flush()
    from app import relevance_queue
    path = Path(tmp_path) / "queue.json"
    assert relevance_queue.enqueue([{
        "asset_id": asset.id, "sense_image_id": binding.id, "lemma": "rosemary",
    }], path) == 1
    monkeypatch.setattr(relevance_queue, "tagging_pending", lambda _s: 3)
    assert relevance_queue.drain(session, path=path, checker=lambda _s, _item: (False, "no")) == 0
    assert binding.review_status == "approved"
    monkeypatch.setattr(relevance_queue, "tagging_pending", lambda _s: 0)
    assert relevance_queue.drain(session, path=path, checker=lambda _s, _item: (False, "no")) == 1
    assert binding.review_status == "rejected"
