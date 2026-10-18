"""Retry regression tests use an isolated in-memory DB; no model calls."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import images, models as m


@pytest.fixture
def store():
    engine = create_engine('sqlite://')
    m.ImageAsset.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def asset(store, **values):
    row = m.ImageAsset(source='test', source_image_id='test', status='ready',
                       safety_status='safe', tag_status='pending')
    for key, value in values.items():
        setattr(row, key, value)
    store.add(row)
    store.commit()
    return row


def eligible(store):
    return list(store.scalars(select(m.ImageAsset.id).where(*images._tag_eligible())))


def test_failed_retry_has_bounded_share(monkeypatch):
    monkeypatch.setattr(images, '_failed_retry_tick', 0)
    assert [i for i in range(30) if images._failed_retry_turn()] == [0, 10, 20]


def test_failed_retry_precedes_new_work_and_respects_pause(store, monkeypatch):
    old = asset(store, tag_status='failed')
    asset(store, tag_status='pending')
    monkeypatch.setattr(images, '_failed_retry_tick', 0)
    monkeypatch.setattr(images.agent_pause, 'is_paused', lambda name: True)
    assert images.tag_pending(store) == 0
    assert images._failed_retry_tick == 0
    monkeypatch.setattr(images.agent_pause, 'is_paused', lambda name: False)
    monkeypatch.setattr(images, '_claim_pictures', lambda s, rows, limit: rows[:limit])
    called = []
    monkeypatch.setattr(images, 'tag_asset', lambda s, aid: called.append(aid))
    assert images.tag_pending(store) == 1
    assert called == [old.id]


@pytest.mark.parametrize('error', [ValueError('invalid model JSON'),
                                  FileNotFoundError('missing image')])
def test_persist_backoff_exhaustion(store, error):
    row = asset(store)
    def fail():
        raise error
    for attempt in range(1, 4):
        with pytest.raises(type(error)):
            images._tag_attempt(row, fail)
        store.commit()
        store.expire_all()
        assert row.tag_attempts == attempt
        assert str(error) in row.tag_error
        assert row.tag_status == 'failed'
        assert row.id not in eligible(store)
        if attempt < 3:
            assert row.tag_retry_at is not None
            row.tag_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            store.commit()
            assert row.id in eligible(store)
        else:
            assert row.tag_retry_at is None


def test_legacy_failed_and_unchecked_cannot_bypass_limit(store):
    legacy = asset(store, tag_status='failed')
    exhausted = asset(store, tag_status='failed', safety_status='unchecked', tag_attempts=3)
    blocked = asset(store, tag_status='failed', safety_status='blocked')
    assert legacy.id in eligible(store)
    assert exhausted.id not in eligible(store)
    assert blocked.id not in eligible(store)


def test_success_clears_failure_and_safety_is_terminal(store):
    row = asset(store, tag_status='failed', tag_attempts=2, tag_error='old failure')
    assert images._tag_attempt(row, lambda: ['tag']) == ['tag']
    assert row.tag_attempts == 0 and row.tag_error is None and row.tag_retry_at is None
    def unsafe():
        row.safety_status = 'blocked'
        raise ValueError('unsafe')
    with pytest.raises(ValueError):
        images._tag_attempt(row, unsafe)
    assert row.tag_retry_at is None
    assert row.id not in eligible(store)


def test_tagger_unavailable_leaves_asset_untouched(store):
    """A down/slow tagging service (#44 slot exhaustion, 502s) is never the
    picture's fault: no attempt is spent, no failure is recorded, and the
    picture stays eligible — unlike a genuine per-picture failure."""
    row = asset(store, tag_attempts=1, tag_error='previous failure')
    def fail():
        raise images.TaggerUnavailable('HTTP 502')
    with pytest.raises(images.TaggerUnavailable):
        images._tag_attempt(row, fail)
    store.commit()
    store.expire_all()
    assert row.tag_attempts == 1
    assert row.tag_error == 'previous failure'
    assert row.tag_status == 'pending'
    assert row.tag_retry_at is None
    assert row.id in eligible(store)


def test_tag_asset_records_errors_before_model_call(store, monkeypatch):
    row = asset(store)
    def missing(*args):
        raise FileNotFoundError('pixels missing')
    monkeypatch.setattr(images, '_tag_asset', missing)
    with pytest.raises(FileNotFoundError):
        images.tag_asset(store, row.id)
    store.commit()
    store.expire_all()
    assert row.tag_error == 'FileNotFoundError: pixels missing'


@pytest.mark.parametrize('detail', ['empty model output', 'truncated JSON output',
                                   'repeated candidate loop'])
def test_http_model_diagnostic_survives_retry_persistence(store, detail):
    import io
    import json
    from urllib.error import HTTPError
    row = asset(store)
    error = HTTPError('http://tagger/tag', 422, 'Unprocessable Entity', {},
                      io.BytesIO(json.dumps({'error': detail}).encode()))
    def fail():
        raise images._tag_http_failure(error)
    with pytest.raises(ValueError, match=detail):
        images._tag_attempt(row, fail)
    store.commit()
    store.expire_all()
    assert detail in row.tag_error
    assert row.tag_attempts == 1 and row.tag_retry_at is not None


@pytest.mark.parametrize('code', [429, 502, 503])
def test_http_service_failure_does_not_consume_retry(store, code):
    from urllib.error import HTTPError
    row = asset(store)
    def fail():
        raise images._tag_http_failure(HTTPError('http://tagger/tag', code, 'busy', {}, None))
    with pytest.raises(images.TaggerUnavailable):
        images._tag_attempt(row, fail)
    assert row.tag_attempts == 0
    assert row.tag_status == 'pending'


def test_http_non_json_diagnostic_is_safe_and_bounded():
    import io
    from urllib.error import HTTPError
    body = io.BytesIO(b'<html>' + b'x' * 20000)
    response = HTTPError('http://tagger/tag', 422, 'bad', {}, body)
    error = images._tag_http_failure(response)
    assert 'HTTP 422' in str(error) and '<html>' not in str(error)
    assert body.tell() == 8192


def test_rescore_missing_file_consumes_picture_retry(store, monkeypatch, tmp_path):
    row = asset(store, path='missing.jpg', tags=[])
    monkeypatch.setattr(images.config, 'MEDIA', tmp_path)
    monkeypatch.setattr(images, 'split_made_up', lambda *a: ([], []))
    with pytest.raises(FileNotFoundError):
        images._tag_attempt(row, lambda: images.rescore(store, row))
    assert row.tag_attempts == 1
    assert row.tag_error.startswith('FileNotFoundError:')
