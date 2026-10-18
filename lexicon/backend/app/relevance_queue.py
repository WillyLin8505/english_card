"""Idle-time picture relevance checks (#192).

The tags workers call ``drain`` only after a labelling pass finds nothing
waiting. While pictures are still pending, drain returns immediately and
does not call the vision model. The queue file starts empty; nothing runs
until a caller enqueues items.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import func, select

from . import config, models as m

QUEUE = Path(__file__).resolve().parents[2] / "state" / "relevance_queue.json"
LOCK = QUEUE.with_suffix(".lock")


def tagging_pending(s) -> int:
    return s.scalar(select(func.count()).select_from(m.ImageAsset).where(
        m.ImageAsset.status == 'ready',
        m.ImageAsset.tag_status == 'pending',
        m.ImageAsset.safety_status != 'blocked')) or 0


def load(path: Path | None = None) -> list[dict]:
    path = path or QUEUE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    items = data.get('items') if isinstance(data, dict) else data
    return list(items or [])


def save(items: list[dict], path: Path | None = None) -> None:
    path = path or QUEUE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'items': items}, ensure_ascii=False, indent=1), encoding='utf-8')


def enqueue(items: list[dict], path: Path | None = None) -> int:
    current = load(path)
    seen = {(row.get('sense_image_id'), row.get('lemma')) for row in current}
    added = 0
    for item in items:
        key = (item.get('sense_image_id'), item.get('lemma'))
        if key in seen:
            continue
        current.append({**item, 'status': 'queued'})
        seen.add(key)
        added += 1
    if added:
        save(current, path)
    return added


def _lock(path: Path):
    lock = path.with_suffix('.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    os.write(fd, b'1')
    return fd, lock


def _model_checker(s, item: dict) -> tuple[bool, str]:
    """Ask the tagger whether the picture shows the word. No answer keeps it."""
    asset = s.get(m.ImageAsset, item.get('asset_id'))
    if asset is None or not asset.path:
        return True, '沒有圖檔，保留'
    path = config.MEDIA / asset.path
    if not path.is_file():
        return True, '圖檔不在磁碟，保留'
    import sys
    tools = Path(__file__).resolve().parents[2] / 'tools'
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import quality_ai
    return quality_ai.image_shows(str(item.get('lemma') or ''), str(item.get('definition') or ''), path)


def drain(s, limit: int = 1, checker=None, path: Path | None = None) -> int:
    """Check up to ``limit`` queued pictures. Returns how many were checked.

    Does nothing while any picture is still waiting to be tagged, so this
    queue cannot take the GPU from the labelling workers.
    """
    if limit < 1 or tagging_pending(s) > 0:
        return 0
    # One checker at a time. The lock is a file, not a transaction, so the
    # model call does not hold a database row.
    path = path or QUEUE
    held = _lock(path)
    if held is None:
        return 0
    fd, lock = held
    checked = 0
    try:
        items = load(path)
        if checker is None:
            checker = _model_checker
        for item in items:
            if checked >= limit:
                break
            if item.get('status') != 'queued':
                continue
            ok, note = checker(s, item)
            item['status'] = 'keep' if ok else 'reject'
            item['note'] = (note or '')[:200]
            checked += 1
            if not ok and item.get('sense_image_id'):
                binding = s.get(m.SenseImage, item['sense_image_id'])
                if binding is not None and binding.review_status != 'rejected':
                    binding.review_status = 'rejected'
                    s.add(m.ImageReview(
                        sense_image_id=binding.id, decision='rejected',
                        note=f"相關性檢查：不像「{item.get('lemma')}」（#192） {item['note']}"))
        if checked:
            save(items, path)
            s.flush()
    finally:
        os.close(fd)
        try:
            lock.unlink()
        except OSError:
            pass
    return checked
