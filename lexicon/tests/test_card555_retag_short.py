"""問題回報 #593 (card #555): done pictures short of five labels per level are
re-labelled in the background without ever leaving tag_status 'done'."""

from __future__ import annotations

from datetime import datetime, timezone

from app import images, models as m

import itertools

_N = itertools.count()
OLD = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _tags(per_level):
    return [{'word': f'{lv}{i}', 'cefr': lv} for lv in images.CEFR_LEVELS for i in range(per_level)]


def _asset(s, tags, **kw):
    kw.setdefault('source_image_id', f'{len(tags)}-{kw.get("tag_status")}-{next(_N)}')
    kw = {'tag_status': 'done', **kw}
    row = m.ImageAsset(source='test', status='ready', safety_status='safe',
                       tags=tags, tagged_at=OLD, **kw)
    s.add(row)
    s.flush()
    return row


def test_only_short_old_done_pictures_are_picked(session, monkeypatch):
    short = _asset(session, _tags(3))
    _asset(session, _tags(5))
    _asset(session, _tags(2), tag_status='failed')
    seen = []
    monkeypatch.setattr(images.agent_pause, 'is_paused', lambda n: False)
    monkeypatch.setattr(images, 'tag_asset', lambda s, aid: seen.append(aid))
    assert images.retag_short(session, limit=5) == 1
    assert seen == [short.id]


def test_failure_keeps_picture_done_and_is_not_repeated(session, monkeypatch):
    row = _asset(session, _tags(3))
    monkeypatch.setattr(images.agent_pause, 'is_paused', lambda n: False)

    def boom(s, aid):
        row.tag_status = 'failed'
        raise ValueError('bad')
    monkeypatch.setattr(images, 'tag_asset', boom)
    assert images.retag_short(session) == 1
    assert row.tag_status == 'done'
    session.flush()
    assert images.retag_short(session) == 0


def test_request_retag_queues_a_recent_short_picture(session):
    row = _asset(session, _tags(3))
    row.tagged_at = datetime.now(timezone.utc)
    session.flush()
    assert images.request_retag(session, row.id) is True
    assert row.tagged_at is None
    full = _asset(session, _tags(5), source_image_id='x')
    assert images.request_retag(session, full.id) is False
