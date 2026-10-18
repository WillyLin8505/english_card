"""Picture-need definition: one rule for the count, the queue, and the pack."""
from app.picture_need import assign_picture_ids, needs_own_picture, next_query


def test_only_a_full_noun_with_a_primary_sense_needs_its_own_picture():
    assert needs_own_picture("noun", "full", [0])
    assert needs_own_picture("noun", "full", [1])
    assert not needs_own_picture("noun", "full", [2])
    assert not needs_own_picture("verb", "full", [0])
    assert not needs_own_picture("adj", "full", [0])
    assert not needs_own_picture("noun", "stub", [0])


def test_other_parts_of_speech_show_the_noun_pictures():
    lexemes = [
        {"id": 1, "normalized": "run", "pos": "noun", "status": "full",
         "senses": [{"ordinal": 0}]},
        {"id": 2, "normalized": "run", "pos": "verb", "status": "full",
         "senses": [{"ordinal": 0}]},
        {"id": 3, "normalized": "elapse", "pos": "verb", "status": "full",
         "senses": [{"ordinal": 0}]},
        {"id": 4, "normalized": "tore", "pos": "verb", "status": "full",
         "redirect_to": 2, "senses": []},
    ]
    assign_picture_ids(lexemes)
    assert lexemes[0]["picture_ids"] == [1]
    assert lexemes[1]["picture_ids"] == [1]
    assert lexemes[2]["picture_ids"] == []
    assert lexemes[3]["picture_ids"] == []


def test_alternate_query_stops_at_the_cap_and_when_the_gloss_adds_nothing():
    gloss = "A small round fruit with red skin."
    assert next_query("apple", gloss, 0) == "apple small"
    assert next_query("apple", gloss, 1) == "apple round"
    assert next_query("apple", gloss, 2) is None
    assert next_query("apple", "A apple.", 0) is None


def test_enqueue_skips_a_lemma_with_no_picture_noun(session):
    from app import images, models as m
    verb = m.Lexeme(language="en", lemma="elapse", normalized="elapse", pos="verb", status="full")
    session.add(verb)
    session.flush()
    session.add(m.Sense(lexeme_id=verb.id, sense_key="elapse", ordinal=0))
    session.flush()
    assert images.enqueue_fetch(session, "en", "zh-TW", "elapse", ["sense_image"]) is None
    noun = m.Lexeme(language="en", lemma="apple", normalized="apple", pos="noun", status="full")
    session.add(noun)
    session.flush()
    session.add(m.Sense(lexeme_id=noun.id, sense_key="apple", ordinal=0))
    session.flush()
    task = images.enqueue_fetch(session, "en", "zh-TW", "apple", ["sense_image"])
    assert task is not None and task.status == "queued"


def test_ensure_picture_fetch_queues_a_bare_noun_and_keeps_the_rejected_cap(session):
    from app import images, models as m
    noun = m.Lexeme(language="en", lemma="apple", normalized="apple", pos="noun", status="full")
    session.add(noun)
    session.flush()
    sense = m.Sense(lexeme_id=noun.id, sense_key="apple", ordinal=0)
    session.add(sense)
    session.flush()
    task = images.ensure_picture_fetch(session, "en", "zh-TW", "apple")
    assert task is not None and task.status == "queued"
    task.status = "completed"
    task.attempts = 1
    again = images.ensure_picture_fetch(session, "en", "zh-TW", "apple")
    assert again.status == "queued" and again.attempts == 0
    again.status = "completed"
    again.rejected_retries = 2
    asset = m.ImageAsset(source="test", source_image_id="apple", path="apple.jpg",
                         mime="image/jpeg", width=10, height=10, status="ready",
                         safety_status="safe")
    session.add(asset)
    session.flush()
    session.add(m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="representative",
                             review_status="rejected", ordinal=0, alt_native={}))
    session.flush()
    kept = images.ensure_picture_fetch(session, "en", "zh-TW", "apple")
    assert kept.status == "completed" and kept.rejected_retries == 2


def test_claim_fetch_skips_a_queued_lemma_that_has_no_noun(session):
    from app import images, models as m
    verb = m.Lexeme(language="en", lemma="elapse", normalized="elapse", pos="verb", status="full")
    session.add(verb)
    session.flush()
    session.add(m.Sense(lexeme_id=verb.id, sense_key="elapse", ordinal=0))
    session.add_all([
        m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="elapse",
                         fields=["sense_image"], status="queued"),
        m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="not-yet",
                         fields=["sense_image"], status="queued"),
    ])
    session.flush()
    claimed = images.claim_fetch(session, "worker-1")
    assert claimed is not None and claimed.lemma == "not-yet"


def test_promote_rejected_refetch_changes_the_search_and_stops_at_the_cap(session):
    from app import images, models as m
    lx = m.Lexeme(language="en", lemma="blister", normalized="blister", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="blister", ordinal=0)
    session.add(sense)
    session.flush()
    session.add(m.Definition(sense_id=sense.id, language="en",
                             text="A small bubble between the layers of the skin.", source="test"))
    asset = m.ImageAsset(source="test", source_image_id="x", path="x.jpg", mime="image/jpeg",
                         width=10, height=10, status="ready", safety_status="safe")
    session.add(asset)
    session.flush()
    session.add(m.SenseImage(sense_id=sense.id, image_asset_id=asset.id, role="representative",
                             review_status="rejected", ordinal=0, alt_native={}))
    task = m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="blister",
                            fields=["sense_image"], status="completed", rejected_retries=0)
    session.add(task)
    session.flush()
    assert images.promote_rejected_refetch(session, limit=5) == 1
    assert task.status == "requeue"
    assert task.search_query == "blister small"
    assert task.rejected_retries == 1
    task.status = "completed"
    assert images.promote_rejected_refetch(session, limit=5) == 1
    assert task.search_query == "blister bubble"
    assert task.rejected_retries == 2
    task.status = "completed"
    assert images.promote_rejected_refetch(session, limit=5) == 0
    assert task.status == "completed"


def test_auto_fetch_searches_the_alternate_phrase(session, monkeypatch):
    from app import images, models as m
    lx = m.Lexeme(language="en", lemma="blister", normalized="blister", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="blister", ordinal=0)
    session.add(sense)
    session.flush()
    seen = []

    def search(s, sense_id, lemma, gloss, native, ctx):
        seen.append(lemma)
        return []

    for key in images.IMAGE_SOURCES:
        monkeypatch.setitem(images.IMAGE_SOURCES, key, (search, None))
    images.auto_fetch(session, "en", "zh-TW", "blister", query="blister bubble", per_sense=1)
    assert seen and set(seen) == {"blister bubble"}
