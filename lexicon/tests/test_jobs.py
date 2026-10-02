"""Jobs in PostgreSQL: migrations, two workers never take the same job,
pause / resume / cancel, checkpoint recovery, API idempotency."""

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app import config, db, jobs
from app import models as m
from conftest import apple_data


def test_migration_created_every_table(pg):
    names = set(inspect(db.engine).get_table_names())
    required = {"sources", "source_capabilities", "source_snapshots", "source_policies",
                "source_policy_steps", "languages", "language_pairs", "lexemes", "senses",
                "definitions", "sense_translations", "localized_labels", "forms",
                "pronunciations", "audio_assets", "image_assets", "image_candidates",
                "sense_images", "image_reviews", "synsets", "semantic_relations",
                "lexeme_relations", "relation_target_senses", "relation_translations",
                "examples", "example_translations", "card_templates", "card_template_versions",
                "card_template_sections", "field_candidates", "field_values", "field_provenance",
                "user_overrides", "missing_lexeme_requests", "missing_localization_requests",
                "dictionary_releases", "import_jobs", "import_job_steps", "import_attempts",
                "import_errors", "api_usage", "image_fetch_tasks"}
    assert required <= names


def _job(session, words=("apple",), mode="fill_missing"):
    j = jobs.create(session, {"target_language": "en", "native_language": "zh-TW", "mode": mode,
                              "words": list(words), "fields": ["pos", "definition", "ipa"]})
    session.commit()
    return j.id


def test_two_workers_never_claim_the_same_job(session):
    ids = {_job(session), _job(session)}
    got, barrier = [], threading.Barrier(2)

    def worker(name):
        with db.SessionLocal() as s:
            barrier.wait()
            j = jobs.claim(s, name)
            got.append(j.id if j else None)
            s.commit()

    ts = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert set(got) == ids  # each job exactly once
    with db.SessionLocal() as s:
        assert jobs.claim(s, "w3") is None  # nothing left (both have live heartbeats)


def test_required_languages(session):
    with pytest.raises(jobs.JobError, match="必填"):
        jobs.create(session, {"target_language": "en", "words": ["apple"]})


def test_create_shards_splits_words_and_is_idempotent(session):
    body = {"target_language": "en", "native_language": "zh-TW",
            "words": ["one", "two", "three", "four", "five"],
            "fields": ["ipa"], "parallelism": 4}
    made = jobs.create_shards(session, body, "parallel-test")
    session.commit()
    assert len(made) == 4
    assert sorted(w for job in made for w in job.words) == sorted(body["words"])
    assert jobs.create_shards(session, body, "parallel-test") == made


def test_pause_resume_cancel_state_machine(session):
    jid = _job(session)
    assert jobs.control(session, jid, "pause").status == "paused"  # queued → paused
    assert jobs.control(session, jid, "pause").status == "paused"  # idempotent
    assert jobs.control(session, jid, "resume").status == "queued"
    j = jobs.claim(session, "w")
    assert jobs.control(session, j.id, "pause").status == "pausing"
    assert jobs.control(session, j.id, "cancel").status == "cancelling"
    session.commit()
    assert jobs.run(db.SessionLocal, j.id, "w") == "cancelled"
    with pytest.raises(jobs.JobError):
        jobs.control(session, jid, "resume")


def test_checkpoint_recovery_and_completion(session, fakes):
    apple_data(fakes)
    jid = _job(session, ["apple", "pear", "plum"])
    with db.SessionLocal() as s:
        jobs.claim(s, "w1")
        s.commit()
    done = []
    state = jobs.run(db.SessionLocal, jid, "w1", stop=lambda: len(done) >= 1,
                     on_word=lambda w, t: done.append(w))
    assert state == "released" and done == ["apple"]
    with db.SessionLocal() as s:
        j = s.get(m.ImportJob, jid)
        assert j.checkpoint == 1 and j.status == "running" and j.worker_id is None
        again = jobs.claim(s, "w2")  # a released job can be taken by another worker
        assert again.id == jid
        s.commit()
    rest = []
    assert jobs.run(db.SessionLocal, jid, "w2", on_word=lambda w, t: rest.append(w)) in (
        "completed", "completed_with_errors")
    assert rest == ["pear", "plum"]  # resumed after the checkpoint, apple not redone


def test_worker_slice_yields_after_one_word(session, fakes):
    apple_data(fakes)
    jid = _job(session, ["apple", "pear"])
    with db.SessionLocal() as s:
        jobs.claim(s, "w1")
        s.commit()
    assert jobs.run(db.SessionLocal, jid, "w1", max_words=1) == "yielded"
    with db.SessionLocal() as s:
        job = s.get(m.ImportJob, jid)
        assert (job.checkpoint, job.status, job.worker_id) == (1, "queued", None)


def test_unreachable_source_ends_completed_with_errors(session, fakes):
    apple_data(fakes)
    fakes["kaikki"].fail = {"*"}
    jid = _job(session, ["apple"])
    with db.SessionLocal() as s:
        jobs.claim(s, "w")
        s.commit()
    assert jobs.run(db.SessionLocal, jid, "w") == "completed_with_errors"
    with db.SessionLocal() as s:
        errs = s.execute(select(m.ImportError_).where(m.ImportError_.job_id == jid)).scalars().all()
        assert {(e.field, e.source) for e in errs} >= {("ipa", "kaikki")}
        retry = jobs.retry_failures(s, jid)
        assert retry.retry_of == jid and "ipa" in retry.fields


@pytest.fixture
def client(session, monkeypatch):
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    with TestClient(app) as c:
        yield c


def test_api_requires_key_and_is_idempotent(client):
    assert client.get("/sources").status_code == 401
    h = {"X-API-Key": "test-key", "Idempotency-Key": "abc-123"}
    body = {"target_language": "en", "native_language": "zh-TW", "words": ["apple"],
            "fields": ["ipa"], "mode": "dry_run"}
    a = client.post("/imports", json=body, headers=h)
    b = client.post("/imports", json=body, headers=h)
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] == b.json()["id"]
    listed = client.get("/imports", headers=h).json()
    assert len(listed) == 1
    assert listed[0]["word_preview"] == ["apple"]
    assert listed[0]["word_preview_remaining"] == 0
    assert listed[0]["current_word"] == "apple"
    missing = client.post("/imports", json={"words": ["x"]}, headers=h)
    assert missing.status_code == 422


def test_api_policy_endpoints(client):
    h = {"X-API-Key": "test-key"}
    ov = client.get("/policies/en/zh-TW", headers=h).json()
    assert [b["block"] for b in ov["blocks"]][:3] == ["basic", "pronunciation", "forms"]
    p = client.get("/policies/en/zh-TW/verb_past", headers=h).json()
    assert [s["source"] for s in p["steps"]] == ["kaikki"]
    assert any(u["source"] == "cmudict" for u in p["unsupported"])
    r = client.put("/policies/en/zh-TW/verb_past", headers=h,
                   json={"strategy": "FIRST_VALID", "steps": [{"source": "datamuse"}]})
    assert r.status_code == 422


def test_a_failed_step_marks_the_job_even_if_another_source_filled_the_field(session, fakes):
    apple_data(fakes)
    fakes["oewn"].fail = {"synonyms"}  # Kaikki still supplies synonyms
    j = jobs.create(session, {"target_language": "en", "native_language": "zh-TW",
                              "words": ["apple"], "fields": ["synonyms"]})
    session.commit()
    with db.SessionLocal() as s:
        jobs.claim(s, "w")
        s.commit()
    assert jobs.run(db.SessionLocal, j.id, "w") == "completed_with_errors"


def test_missing_word_requests_are_a_word_list(session):
    """問題回報: the app's 缺詞請求 can start an import job."""
    from app import jobs
    from app import models as m
    session.add_all([m.MissingLexemeRequest(target_language="en", lemma="texture", pos="noun", count=3),
                     m.MissingLexemeRequest(target_language="en", lemma="pebble", pos="noun"),
                     m.MissingLexemeRequest(target_language="en", lemma="apple", pos="noun")])
    session.add(m.Lexeme(language="en", lemma="apple", normalized="apple", pos="noun", status="full"))
    session.flush()
    assert jobs.missing_words(session, "en") == ["texture", "pebble"]
    session.add_all([m.MissingLexemeRequest(target_language="en", lemma="stained_glass", pos="noun"),
                     m.MissingLexemeRequest(target_language="en", lemma="calendrier", pos="noun")])
    session.flush()
    assert jobs.missing_words(session, "en") == ["texture", "pebble", "stained glass"]
    # apples is a form of apple, which is in the lexicon: not missing.
    session.add(m.FieldValue(target_language="en", native_language="*", lemma="apple",
                             field="noun_plural", items=[{"form": "apples"}], status="complete"))
    session.add(m.MissingLexemeRequest(target_language="en", lemma="apples", pos="noun"))
    session.flush()
    assert "apples" not in jobs.missing_words(session, "en")
    assert jobs.resolve_words(session, "en", ["kettle"], jobs.MISSING_LIST) == [
        "texture", "pebble", "stained glass", "kettle"]
