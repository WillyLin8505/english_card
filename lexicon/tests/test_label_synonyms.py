"""#427 (card #329): a picture labelled with a synonym of the word (dad for
father, refrigerator for fridge) counts as showing the word; the table is
quality/label_synonyms.json, re-read when it changes."""

import json

import pytest

from app import images, label_synonyms


@pytest.fixture
def synonyms_file(tmp_path, monkeypatch):
    path = tmp_path / "label_synonyms.json"

    def write(data):
        path.write_text(json.dumps(data), encoding="utf-8")
        label_synonyms._cache.update(mtime=None, index={})

    monkeypatch.setattr(label_synonyms, "FILE", path)
    label_synonyms._cache.update(mtime=None, index={})
    yield write
    label_synonyms._cache.update(mtime=None, index={})


def test_groups_are_symmetric_and_implies_one_way(synonyms_file):
    synonyms_file({"groups": [["father", "Dad", "papa"]],
                   "implies": {"bedroom": ["headboard"]}})
    assert label_synonyms.synonyms("father") == {"dad", "papa"}
    assert label_synonyms.synonyms("dad") == {"father", "papa"}
    assert label_synonyms.synonyms("bedroom") == {"headboard"}
    assert label_synonyms.synonyms("headboard") == set()
    assert label_synonyms.synonyms("cat") == set()
    assert label_synonyms.synonyms(None) == set()


def test_missing_file_means_no_synonyms(tmp_path, monkeypatch):
    monkeypatch.setattr(label_synonyms, "FILE", tmp_path / "none.json")
    label_synonyms._cache.update(mtime=None, index={})
    assert label_synonyms.synonyms("father") == set()


def test_file_edit_is_picked_up(synonyms_file):
    synonyms_file({"groups": [["fridge", "refrigerator"]]})
    assert label_synonyms.synonyms("fridge") == {"refrigerator"}
    synonyms_file({"groups": [["fridge", "icebox"]]})
    assert label_synonyms.synonyms("fridge") == {"icebox"}


def test_judge_keeps_a_picture_labelled_with_a_synonym(session, synonyms_file):
    from app import models as m
    synonyms_file({"groups": [["father", "dad"]]})
    lx = m.Lexeme(language="en", lemma="father", normalized="father", pos="noun", status="full")
    session.add(lx)
    session.flush()
    se = m.Sense(lexeme_id=lx.id, sense_key="en-father-0", ordinal=0)
    session.add(se)
    session.flush()
    asset = m.ImageAsset(source="wikimedia_commons", source_image_id="File:Dad.jpg",
                         license_code="CC0", status="ready", tag_status="done",
                         safety_status="safe",
                         tags=[{"word": "dad"}, {"word": "baby"}, {"word": "smile"}])
    session.add(asset)
    session.flush()
    binding = m.SenseImage(sense_id=se.id, image_asset_id=asset.id, role="primary",
                           review_status="pending", semantic_score=0.4)
    session.add(binding)
    session.flush()
    word, seen = images.sense_shows_word(session, asset, se.id, "en", "father")
    assert (word, seen) == ("father", True)
    images.judge(session, binding, asset, "father", "en")
    assert binding.review_status == "pending" and binding.semantic_score == 0.95
    # Without the table the same labels do not name the word.
    synonyms_file({"groups": []})
    assert images.sense_shows_word(session, asset, se.id, "en", "father") == ("father", False)
