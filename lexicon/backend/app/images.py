"""Sense-bound image acquisition (Wikidata／Commons → Open Images →
Smithsonian CC0 → Openverse, the spec's order) and review. No automatic
approval."""
import csv
import hashlib
import html
import io
import ipaddress
import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import contextvars
import urllib.parse
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image
from sqlalchemy import case, func, or_, select, text

from . import config
from . import agent_pause, db, models as m

HOSTS = {'www.wikidata.org', 'commons.wikimedia.org', 'upload.wikimedia.org', 'thumb.wikimedia.org'}
# Our own API endpoints for the two other live sources: an exact host match,
# the strongest check, because we chose these hosts ourselves.
SMITHSONIAN_HOSTS = {'api.si.edu', 'ids.si.edu'}
OPENVERSE_HOSTS = {'api.openverse.org'}
MAX_BYTES = 15 * 1024 * 1024


def allowed_license(value):
    value = (value or '').upper().strip()
    return value in ('CC0', 'CC0 1.0', 'PUBLIC DOMAIN') or bool(re.fullmatch(r'CC BY(?: [1-4]\.0)?', value))


def check_host_url(url, hosts, message):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError(message)
    return url


def check_url(url):
    return check_host_url(url, HOSTS, '只接受 Wikidata／Wikimedia 官方 HTTPS 網址')


def check_smithsonian_url(url):
    return check_host_url(url, SMITHSONIAN_HOSTS, '只接受 Smithsonian Open Access 官方 HTTPS 網址')


def check_openverse_api_url(url):
    return check_host_url(url, OPENVERSE_HOSTS, '只接受 Openverse 官方 HTTPS 網址')


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


def check_public_image_url(url):
    """A picture's own URL from a source with no fixed host (Open Images:
    whichever Flickr CDN host; Openverse: whichever provider it indexed) —
    accepted only when every address the host resolves to is public (not a
    private network, the loopback or link-local range, or the cloud metadata
    address): an SSRF guard for a host that can't be named ahead of time."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('只接受公開的 HTTPS 圖片網址')
    host = parsed.hostname
    if not host:
        raise ValueError('網址缺少主機名稱')
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f'無法解析主機：{host}') from e
    if not infos or not all(_is_public_ip(info[4][0]) for info in infos):
        raise ValueError('圖片網址指向非公開位址')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, validate=check_url):
        self._validate = validate

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._validate(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_last_request = [0.0]
_throttle = threading.Lock()
# Per-process: start_lexicon.bat runs two --lane images workers, each its own
# process with its own lock, so the combined rate against one host is up to
# 2x this. 2.0s keeps that combined rate near the old single-worker 1/s
# instead of doubling it (source of the 429s diagnosed on 卡 #3, 2026-10-15).
MIN_INTERVAL = 2.0


def enqueue_fetch(s, target: str, native: str, lemma: str, fields: list[str]):
    """Queue image acquisition after text materialization; idempotent per word.

    A spelling with no picture noun is not queued (picture_need)."""
    from .picture_need import lemma_needs_picture
    wanted = sorted(set(fields) & {"sense_image", "context_image", "thumbnail"})
    if not wanted or not lemma_needs_picture(s, target, lemma):
        return None
    task = s.execute(select(m.ImageFetchTask).where(
        m.ImageFetchTask.target_language == target,
        m.ImageFetchTask.native_language == native,
        m.ImageFetchTask.lemma == lemma,
    )).scalar_one_or_none()
    if task is None:
        task = m.ImageFetchTask(target_language=target, native_language=native,
                                lemma=lemma, fields=wanted, status="queued")
        s.add(task)
    else:
        task.fields = sorted(set(task.fields or []) | set(wanted))
        if task.status in ("failed", "completed_with_errors"):
            task.status, task.error, task.finished_at = "queued", None, None
    s.flush()
    return task


def ensure_picture_fetch(s, target: str, native: str, lemma: str):
    """Queue a picture when a full noun has none.

    Saving a word (materialize) can add a noun, or replace its senses and
    cascade-delete the pictures, without asking for image fields. A finished
    task would then never run again. A noun that already used up the
    rejected-picture search cap is left finished.
    """
    from .picture_need import PICTURE_POS, REJECTED_REFETCH_CAP, lemma_needs_picture
    if not lemma_needs_picture(s, target, lemma):
        return None
    has_live = s.scalar(text("""
        SELECT 1 FROM lexemes l
        JOIN senses sn ON sn.lexeme_id = l.id
        JOIN sense_images si ON si.sense_id = sn.id
        WHERE l.language = :language AND l.normalized = lower(:lemma)
          AND l.pos = :pos AND si.review_status <> 'rejected'
        LIMIT 1
    """), {"language": target, "lemma": lemma, "pos": PICTURE_POS})
    if has_live:
        return None
    task = s.execute(select(m.ImageFetchTask).where(
        m.ImageFetchTask.target_language == target,
        func.lower(m.ImageFetchTask.lemma) == lemma.lower(),
    )).scalars().first()
    if task is not None and task.status in ("queued", "running", "requeue", "cancelled", "failed"):
        return task
    if task is not None and (task.rejected_retries or 0) >= REJECTED_REFETCH_CAP:
        rejected = s.scalar(text("""
            SELECT 1 FROM lexemes l
            JOIN senses sn ON sn.lexeme_id = l.id
            JOIN sense_images si ON si.sense_id = sn.id
            WHERE l.language = :language AND l.normalized = lower(:lemma)
              AND l.pos = :pos AND si.review_status = 'rejected'
            LIMIT 1
        """), {"language": target, "lemma": lemma, "pos": PICTURE_POS})
        if rejected:
            return task
    now = datetime.now(timezone.utc)
    if task is None:
        task = m.ImageFetchTask(target_language=target, native_language=native,
                                lemma=lemma, fields=["sense_image"], status="queued")
        s.add(task)
    else:
        task.status = "queued"
        task.error = None
        task.finished_at = None
        task.retry_at = None
        task.attempts = 0
        task.created_at = now
        task.fields = sorted(set(task.fields or []) | {"sense_image"})
    s.flush()
    return task


# A running fetch with no heartbeat (worker refreshes started_at) this long
# belongs to a dead worker. Reclaim it before any queued row (#236).
FETCH_STALE_AFTER = timedelta(minutes=10)
# Timeouts and undecodable downloads are transient. Backoff is capped at 1h;
# after this many attempts the row is a permanent failure, not
# completed_with_errors (#233).
TRANSIENT_ATTEMPT_CAP = 8
_WORKER_LANES = {"images", "text", "tags"}


def _aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_worker_pid(worker_id: str | None) -> tuple[str | None, int | None]:
    """worker_id is '{hostname}-{pid}' or '{hostname}-{pid}-{lane}'."""
    if not worker_id:
        return None, None
    parts = worker_id.split("-")
    if parts and parts[-1] in _WORKER_LANES:
        parts = parts[:-1]
    if not parts or not parts[-1].isdigit():
        return None, None
    host = "-".join(parts[:-1]) or None
    return host, int(parts[-1])


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _worker_process_gone(worker_id: str | None) -> bool:
    """True when this machine can see that the worker pid is not running.

    A worker_id from another host is left to the heartbeat timeout: a local
    pid with the same number would be a different process.
    """
    host, pid = _parse_worker_pid(worker_id)
    if pid is None or not host or host != socket.gethostname():
        return False
    return not _pid_alive(pid)


def _running_is_orphan(started_at, worker_id: str | None, stale_before) -> bool:
    started = _aware(started_at)
    if started is None or started < stale_before:
        return True
    return _worker_process_gone(worker_id)


def _lemma_has_picture():
    """Exists() correlated to the image_fetch_tasks row being claimed."""
    return (
        select(m.SenseImage.id)
        .join(m.Sense, m.Sense.id == m.SenseImage.sense_id)
        .join(m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id)
        .where(
            m.Lexeme.language == m.ImageFetchTask.target_language,
            m.Lexeme.normalized == func.lower(m.ImageFetchTask.lemma),
            m.SenseImage.review_status != "rejected",
        )
        .exists()
    )


def promote_rejected_refetch(s, limit: int = 1) -> int:
    """Queue a new search phrase for nouns whose pictures are all rejected.

    Stops at picture_need.REJECTED_REFETCH_CAP. ``claim_fetch`` takes
    ``requeue`` before the ordinary ``queued`` backlog.
    """
    from .picture_need import PICTURE_POS, PRIMARY_ORDINAL, REJECTED_REFETCH_CAP, next_query
    rows = s.execute(text("""
        SELECT t.id, t.lemma, t.rejected_retries,
          (SELECT d.text FROM lexemes l
           JOIN senses sn ON sn.lexeme_id = l.id AND sn.ordinal < :k
           LEFT JOIN definitions d ON d.sense_id = sn.id AND d.language = l.language
           WHERE l.language = t.target_language AND l.normalized = lower(t.lemma)
             AND l.status = 'full' AND l.pos = :pos
           ORDER BY l.id, sn.ordinal LIMIT 1) AS gloss
        FROM image_fetch_tasks t
        WHERE t.status IN ('completed', 'completed_with_errors')
          AND t.rejected_retries < :cap
          AND EXISTS (
            SELECT 1 FROM lexemes l JOIN senses sn ON sn.lexeme_id = l.id
            WHERE l.language = t.target_language AND l.normalized = lower(t.lemma)
              AND l.status = 'full' AND l.pos = :pos AND sn.ordinal < :k)
          AND EXISTS (
            SELECT 1 FROM lexemes l JOIN senses sn ON sn.lexeme_id = l.id
            JOIN sense_images si ON si.sense_id = sn.id
            WHERE l.language = t.target_language AND l.normalized = lower(t.lemma)
              AND l.pos = :pos AND si.review_status = 'rejected')
          AND NOT EXISTS (
            SELECT 1 FROM lexemes l JOIN senses sn ON sn.lexeme_id = l.id
            JOIN sense_images si ON si.sense_id = sn.id
            WHERE l.language = t.target_language AND l.normalized = lower(t.lemma)
              AND l.pos = :pos AND si.review_status <> 'rejected')
        ORDER BY t.id
        LIMIT :lim
    """), {"k": PRIMARY_ORDINAL, "pos": PICTURE_POS, "cap": REJECTED_REFETCH_CAP,
           "lim": limit}).mappings().all()
    now = datetime.now(timezone.utc)
    changed = 0
    for row in rows:
        task = s.get(m.ImageFetchTask, row["id"])
        if task is None:
            continue
        phrase = next_query(row["lemma"], row["gloss"], row["rejected_retries"] or 0)
        if not phrase:
            task.rejected_retries = REJECTED_REFETCH_CAP
            continue
        task.search_query = phrase
        task.rejected_retries = (task.rejected_retries or 0) + 1
        task.status = "requeue"
        task.error = (f"圖片都被退回，改搜尋「{phrase}」"
                      f"（第 {task.rejected_retries} 次，上限 {REJECTED_REFETCH_CAP}）")
        task.finished_at = None
        task.retry_at = None
        task.created_at = now
        changed += 1
    if rows:
        s.flush()
    return changed


def claim_fetch(s, worker_id: str):
    """Claim one deferred image lookup without blocking other workers.

    Orphan running rows (heartbeat older than 10 minutes, or the worker
    process is gone) are taken before any queued row, including older ones
    (#236). A ``requeue`` row (every picture was rejected; search a new
    phrase) is taken before the ordinary ``queued`` backlog, which is
    otherwise oldest-first. Among those, a word that still has no picture
    comes before a word that already has one.
    """
    stale_before = datetime.now(timezone.utc) - FETCH_STALE_AFTER
    now = datetime.now(timezone.utc)
    running_rows = s.execute(select(
        m.ImageFetchTask.id, m.ImageFetchTask.worker_id, m.ImageFetchTask.started_at,
    ).where(m.ImageFetchTask.status == "running")).all()
    orphans = [row for row in running_rows if _running_is_orphan(row.started_at, row.worker_id, stale_before)]
    orphans.sort(key=lambda row: _aware(row.started_at) or datetime.min.replace(tzinfo=timezone.utc))
    task = None
    for row in orphans:
        locked = s.execute(select(m.ImageFetchTask).where(
            m.ImageFetchTask.id == row.id).with_for_update(skip_locked=True)).scalar_one_or_none()
        if locked is not None and locked.status == "running":
            task = locked
            break
    if task is None:
        from .picture_need import lemma_ineligible_for_fetch
        promote_rejected_refetch(s, limit=1)
        task = s.execute(select(m.ImageFetchTask).where(
            m.ImageFetchTask.status.in_(("queued", "requeue")),
            or_(m.ImageFetchTask.retry_at.is_(None), m.ImageFetchTask.retry_at <= now),
            ~lemma_ineligible_for_fetch(),
        ).order_by(
            case((m.ImageFetchTask.status == "requeue", 0), else_=1),
            _lemma_has_picture(),
            m.ImageFetchTask.created_at,
        ).limit(1).with_for_update(skip_locked=True)
        ).scalar_one_or_none()
    if task is None:
        return None
    task.status = "running"
    task.worker_id = worker_id
    task.started_at = datetime.now(timezone.utc)
    task.attempts = (task.attempts or 0) + 1
    s.flush()
    return task


def _fetch_retry_backoff(attempts: int) -> float:
    """1m, 2m, 4m, … capped at 1h, keyed off the task's own attempts count."""
    return min(3600.0, 60.0 * 2 ** min(max(attempts, 1) - 1, 6))


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    low = str(exc).lower()
    return "timed out" in low or "timeout" in low or "逾時" in str(exc)


def _is_permanent_fetch_error(message: str) -> bool:
    """A candidate or concept that will not succeed on a plain retry."""
    text = message or ""
    if any(mark in text for mark in ("無法辨識", "429", "503")):
        return False
    low = text.lower()
    if "timeout" in low or "timed out" in low or "逾時" in text:
        return False
    if "沒有任何語言標籤" in text or "概念沒有英文標籤" in text:
        return True
    return "圖片格式或尺寸不適合字卡" in text or "短邊不足" in text


def _requeue_transient(task, now):
    task.status = "queued"
    task.retry_at = now + timedelta(seconds=_fetch_retry_backoff(task.attempts))
    task.finished_at = None


def run_fetch(s, task_id: int):
    """Run a queued lookup. Downloaded assets remain pending human/AI review."""
    task = s.get(m.ImageFetchTask, task_id)
    if task is None:
        return None
    try:
        share_existing(s, task.target_language, task.lemma)
        got = auto_fetch(s, task.target_language, task.native_language, task.lemma,
                         query=task.search_query)
        task.error = "；".join(got.get("errors", [])[:3]) or None
        incomplete = got.get("incomplete_senses", 0)
        if incomplete and not task.error:
            # Every source came back with a plain empty result (no 429, no
            # format rejection): not an error to log, but still a sense with
            # no picture. Leaving this "completed" hides it from every future
            # scan and from enqueue_fetch's own retry-on-error check.
            task.error = f"{incomplete} 個詞義沒有來源回候選圖片（無錯誤，純查無結果）"
        transient = bool(got.get("rate_limited") or got.get("timed_out") or got.get("transient"))
        if transient and incomplete:
            # 429/503 (#99) and timeouts / bad downloads (#233) go back on the
            # queue with a capped backoff. A timeout that has used up the
            # attempt cap is a permanent failure, not completed_with_errors.
            now = datetime.now(timezone.utc)
            if (not got.get("rate_limited") and (task.attempts or 0) >= TRANSIENT_ATTEMPT_CAP):
                task.status = "failed"
                task.error = ("暫時性錯誤重試已達上限：" + (task.error or "timeout"))[:2000]
                task.retry_at = None
                task.finished_at = now
                return got
            _requeue_transient(task, now)
            return got
        if incomplete and got.get("permanent"):
            now = datetime.now(timezone.utc)
            task.status = "failed"
            task.error = ("永久失敗：" + (task.error or "無法取得合格圖片"))[:2000]
            task.retry_at = None
            task.finished_at = now
            return got
        # A source hiccup (timeout, one-off error) that another source still
        # covered leaves every sense with a picture: not a failure worth
        # flagging.
        task.status = "completed_with_errors" if task.error and incomplete else "completed"
        task.retry_at = None
    except Exception as exc:  # noqa: BLE001 -- keep the independent queue moving
        got = {"senses": 0, "images": 0, "errors": [str(exc)]}
        now = datetime.now(timezone.utc)
        if _is_timeout_error(exc) and (task.attempts or 0) < TRANSIENT_ATTEMPT_CAP:
            task.error = str(exc)[:2000]
            _requeue_transient(task, now)
            return got
        task.status = "failed"
        task.error = f"{type(exc).__name__}: {exc}"[:2000]
        task.retry_at = None
        task.finished_at = now
        return got
    task.finished_at = datetime.now(timezone.utc)
    return got


def fetch(url, limit=MAX_BYTES, validate=check_url):
    request = urllib.request.Request(validate(url), headers={'User-Agent': config.USER_AGENT})
    opener = urllib.request.build_opener(Redirect(validate))
    for attempt in range(4):
        with _throttle:
            wait = _last_request[0] + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_request[0] = time.monotonic()
        try:
            with opener.open(request, timeout=25) as response:
                data = response.read(limit + 1)
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 3:
                raise
            retry = e.headers.get('Retry-After', '')
            time.sleep(min(60.0, float(retry) if retry.isdigit() else 5.0 * 2 ** attempt))
    if len(data) > limit:
        raise ValueError('圖片或回應超過大小限制')
    return data


def commons(params):
    return json.loads(fetch('https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode({'format': 'json', **params})))


def plain(value):
    return html.unescape(re.sub('<[^>]+>', '', value or '')).strip()


def _concept_search_label(entity: dict, lemma: str | None = None) -> str | None:
    """Commons search text for a Wikidata item (#235).

    English label, then English aliases, then the dictionary word, then any
    other language's label or alias. None only when nothing is usable.
    """
    labels = entity.get('labels') or {}
    aliases = entity.get('aliases') or {}
    english = ('en', 'en-gb', 'en-ca')

    def clean(value) -> str | None:
        text = str(value or '').strip()
        return text or None

    for lang in english:
        found = clean((labels.get(lang) or {}).get('value'))
        if found:
            return found
    for lang in english:
        for alias in aliases.get(lang) or []:
            found = clean((alias or {}).get('value'))
            if found:
                return found
    # The dictionary word is English even when Wikidata has no English label.
    found = clean(lemma)
    if found:
        return found
    for obj in labels.values():
        found = clean((obj or {}).get('value'))
        if found:
            return found
    for items in aliases.values():
        for alias in items or []:
            found = clean((alias or {}).get('value'))
            if found:
                return found
    return None


def search(s, sense_id, qid, lemma=None):
    if not s.get(m.Sense, sense_id):
        raise ValueError('找不到指定詞義')
    if not re.fullmatch(r'Q[1-9][0-9]*', qid):
        raise ValueError('請輸入有效 Wikidata 概念 ID，例如 Q89')
    entity = json.loads(fetch(f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json'))['entities'][qid]
    titles = ['File:' + c['mainsnak']['datavalue']['value'] for c in entity.get('claims', {}).get('P18', []) if 'datavalue' in c['mainsnak']]
    label = _concept_search_label(entity, lemma)
    if not label and not titles:
        raise ValueError('概念沒有任何語言標籤或別名，也沒有代表圖，無法搜尋')
    if not label:
        label = qid
    p18 = list(titles)
    results = commons({'action': 'query', 'list': 'search', 'srsearch': label + ' filetype:bitmap', 'srnamespace': 6, 'srlimit': 30})
    titles += [r['title'] for r in results.get('query', {}).get('search', [])]
    titles = list(dict.fromkeys(titles))[:40]
    if not titles:
        return {'candidates': [], 'concept': label, 'p18': []}
    data = commons({'action': 'query', 'titles': '|'.join(titles), 'prop': 'imageinfo', 'iiprop': 'url|extmetadata|size|mime', 'iiurlwidth': 1000})
    # Serialize requests for this sense to avoid repeated candidate rows.
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': 880000000 + sense_id})
    output = []
    for page in data.get('query', {}).get('pages', {}).values():
        info = next(iter(page.get('imageinfo', [])), None)
        if not info or info.get('mime') not in ('image/jpeg', 'image/png', 'image/webp'):
            continue
        meta = info.get('extmetadata', {})
        get = lambda key: plain(meta.get(key, {}).get('value'))
        license_code = get('LicenseShortName')
        if not allowed_license(license_code) or not info.get('descriptionurl') or not get('Artist'):
            continue
        record = {'title': page['title'], 'concept': label, 'qid': qid, 'file_url': info['url'],
                  'download_url': info.get('thumburl') or info['url'], 'page_url': info['descriptionurl'],
                  'license_code': license_code, 'license_url': get('LicenseUrl'), 'author': get('Artist'),
                  'attribution': get('Attribution') or get('Credit'), 'description': get('ImageDescription'), 'raw': info}
        existing = s.scalars(select(m.ImageCandidate).where(m.ImageCandidate.sense_id == sense_id, m.ImageCandidate.source == 'wikimedia_commons')).all()
        candidate = next((c for c in existing if c.metadata_.get('title') == page['title'] and c.concept_id == qid), None)
        if candidate is None:
            candidate = m.ImageCandidate(sense_id=sense_id, source='wikimedia_commons', query=label, concept_id=qid, metadata_=record)
            s.add(candidate); s.flush()
        output.append({'id': candidate.id, **{k: v for k, v in candidate.metadata_.items() if k != 'raw'}, 'imported': candidate.image_asset_id is not None})
    return {'candidates': output, 'concept': label, 'p18': p18}


def _fit_box(width: int, height: int, max_pixels: int) -> tuple[int, int]:
    """Largest aspect-preserving box whose area is within max_pixels."""
    scale = (max_pixels / (width * height)) ** 0.5
    w, h = max(1, int(width * scale)), max(1, int(height * scale))
    while w * h > max_pixels and (w > 1 or h > 1):
        if w >= h and w > 1:
            w -= 1
        elif h > 1:
            h -= 1
        else:
            break
    return w, h


def _normalize_card_bytes(raw: bytes, *, max_pixels: int = 30_000_000, min_side: int = 120,
                          safe_pixels: int = 80_000_000) -> bytes:
    """Bytes that pass the card rules, converting when that is enough (#234).

    A decodable format other than JPEG/PNG/WEBP is re-encoded as JPEG. An
    image over max_pixels is shrunk when the short side can stay >= min_side.
    A short side that is already too small, or a file too large to decode
    safely, raises ValueError so the caller can try the next candidate.
    """
    try:
        im = Image.open(io.BytesIO(raw))
    except Image.UnidentifiedImageError as exc:
        raise ValueError('圖片格式或尺寸不適合字卡：無法辨識格式') from exc
    try:
        im.seek(0)
        width, height = im.size
        if width * height > safe_pixels:
            raise ValueError('圖片格式或尺寸不適合字卡：像素過多，無法安全處理')
        fmt = (im.format or '').upper()
        if fmt in ('JPEG', 'PNG', 'WEBP') and width * height <= max_pixels:
            if min(width, height) < min_side:
                raise ValueError('圖片格式或尺寸不適合字卡：短邊不足')
            return raw
        out_fmt = fmt if fmt in ('JPEG', 'PNG', 'WEBP') else 'JPEG'
        frame = im.convert('RGB') if out_fmt == 'JPEG' else im.copy()
        if frame.width * frame.height > max_pixels:
            frame.thumbnail(_fit_box(frame.width, frame.height, max_pixels), Image.Resampling.LANCZOS)
        if min(frame.size) < min_side:
            raise ValueError('圖片格式或尺寸不適合字卡：短邊不足')
        if frame.width * frame.height > max_pixels:
            raise ValueError('圖片格式或尺寸不適合字卡：縮小後仍超過尺寸上限')
        buf = io.BytesIO()
        if out_fmt == 'JPEG':
            frame.save(buf, 'JPEG', quality=90)
        elif out_fmt == 'PNG':
            frame.save(buf, 'PNG')
        else:
            frame.save(buf, 'WEBP', quality=90)
        return buf.getvalue()
    finally:
        im.close()


def _finalize_image(s, c, *, source_key, raw, license_code, license_url, author, attribution,
                    page_url, file_url, source_image_id):
    """The shared tail of every source's ingest: validate the downloaded
    bytes, store the file (deduped by content hash) under media/images/
    <source>/, and bind it to the candidate's sense — pending review, never
    approved automatically."""
    raw = _normalize_card_bytes(raw)
    with Image.open(io.BytesIO(raw)) as im:
        if im.format not in ('JPEG', 'PNG', 'WEBP') or im.width * im.height > 30_000_000 or min(im.size) < 120:
            raise ValueError('圖片格式或尺寸不適合字卡')
        im.load()
        mime = Image.MIME[im.format]
        extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}[im.format]
        width, height = im.size
        im = im.convert('RGB'); im.thumbnail((400, 400))
        thumb = io.BytesIO(); im.save(thumb, 'WEBP', quality=85)
    digest = hashlib.sha256(raw).hexdigest()
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': int(digest[:15], 16)})
    asset = s.scalars(select(m.ImageAsset).where(m.ImageAsset.sha256 == digest)).first()
    if asset is None:
        folder = config.MEDIA / 'images' / source_key; folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{digest}.{extension}'; thumbnail = folder / f'{digest}.thumb.webp'
        for file, data in [(path, raw), (thumbnail, thumb.getvalue())]:
            temp = file.with_name(uuid.uuid4().hex + '.part')
            try:
                temp.write_bytes(data); os.replace(temp, file)
            finally:
                temp.unlink(missing_ok=True)
        now = datetime.now(timezone.utc)
        asset = m.ImageAsset(source=source_key, source_image_id=source_image_id, page_url=page_url, file_url=file_url,
                             author=author, attribution=attribution, license_code=license_code, license_url=license_url,
                             retrieved_at=now, verified_at=now, mime=mime, width=width, height=height, size_bytes=len(raw), sha256=digest,
                             path=str(path.relative_to(config.MEDIA)), thumbnail_path=str(thumbnail.relative_to(config.MEDIA)), status='ready', safety_status='unchecked')
        s.add(asset); s.flush()
    c.image_asset_id = asset.id
    binding = s.scalars(select(m.SenseImage).where(m.SenseImage.sense_id == c.sense_id, m.SenseImage.image_asset_id == asset.id)).first()
    if binding is None:
        binding = m.SenseImage(sense_id=c.sense_id, image_asset_id=asset.id, role='representative', review_status='pending', alt_native={})
        s.add(binding); s.flush()
    return {'id': binding.id, 'status': binding.review_status}


def ingest(s, candidate_id):
    c = s.get(m.ImageCandidate, candidate_id)
    if not c:
        raise ValueError('找不到圖片候選')
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': 880000000 + c.sense_id})
    meta = c.metadata_
    if not allowed_license(meta.get('license_code')):
        raise ValueError('圖片授權不符合允許清單')
    # Recheck the original host metadata immediately before downloading.
    fresh = commons({'action': 'query', 'titles': meta['title'], 'prop': 'imageinfo', 'iiprop': 'extmetadata'})
    info = next(iter(fresh.get('query', {}).get('pages', {}).values()), {}).get('imageinfo', [{}])[0]
    license_now = plain(info.get('extmetadata', {}).get('LicenseShortName', {}).get('value'))
    if license_now != meta['license_code'] or not allowed_license(license_now):
        raise ValueError('來源授權已改變，請重新搜尋')
    raw = fetch(meta['download_url'])
    return _finalize_image(s, c, source_key='wikimedia_commons', raw=raw, license_code=license_now,
                           license_url=meta['license_url'], author=meta['author'], attribution=meta['attribution'],
                           page_url=meta['page_url'], file_url=meta['file_url'], source_image_id=meta['title'])


# ── Automatic acquisition (import jobs) ──────────────────────────────
# Each sense is matched to a Wikidata concept by its gloss, part of speech
# and native meaning (never by the spelling alone: bat, bank), then its
# images are searched and downloaded. Nothing is approved automatically:
# downloads wait in the review queue with a semantic score.

NOT_CONCEPTS = ('disambiguation', 'family name', 'given name', 'surname', 'film', 'album',
                'song', 'single by', 'band', 'company', 'magazine', 'journal', 'novel by',
                'television', 'video game', 'episode', 'scientific article', 'painting by')
PLACE = re.compile(r'\b(river|stream|village|town|city|municipality|commune|lake|mountain|'
                   r'island|county|district|province|hamlet|parish)\b( \w+)? (in|of) ')
STOP = {'a', 'an', 'the', 'of', 'or', 'and', 'to', 'in', 'on', 'for', 'with', 'by', 'as', 'is',
        'that', 'which', 'used', 'any', 'some', 'something', 'one', 'from', 'at', 'its', 'be'}


def _words(text):
    """Content words, plural -s dropped (mammal / mammals)."""
    out = set()
    for w in re.findall(r"[a-z]+", (text or '').lower()):
        if w in STOP or len(w) <= 2:
            continue
        out.add(w[:-1] if w.endswith('s') and not w.endswith('ss') and len(w) > 3 else w)
    return out


def wikidata(params):
    return json.loads(fetch('https://www.wikidata.org/w/api.php?' + urllib.parse.urlencode(
        {'format': 'json', **params})))


def match_concept(lemma, gloss, native=None):
    """The Wikidata item for one sense, or None: the label must be the word,
    and the description must share words with the gloss (or the Chinese
    label must be the sense's meaning)."""
    found = wikidata({'action': 'wbsearchentities', 'search': lemma, 'language': 'en',
                      'type': 'item', 'limit': 12}).get('search', [])
    if not found:
        return None
    ids = [f['id'] for f in found]
    entities = wikidata({'action': 'wbgetentities', 'ids': '|'.join(ids),
                         'props': 'labels|descriptions|aliases|claims',
                         'languages': 'en|zh-tw|zh-hant|zh'}).get('entities', {})
    gloss_words = _words(gloss)
    natives = {x.strip() for x in re.split(r'[、，,；;]', native or '') if x.strip()}
    best, best_score, exact = None, 0.0, 0
    for qid in ids:
        e = entities.get(qid, {})
        label = e.get('labels', {}).get('en', {}).get('value', '')
        aliases = [a['value'].lower() for a in e.get('aliases', {}).get('en', [])]
        desc = e.get('descriptions', {}).get('en', {}).get('value', '')
        if any(x in desc.lower() for x in NOT_CONCEPTS) or PLACE.search(desc.lower()):
            continue
        if not e.get('claims', {}).get('P18'):
            continue  # nothing to picture (meaning, freedom): no representative image
        if lemma.islower() and label[:1].isupper():
            continue  # a proper name (Run, a stream in the Netherlands)
        if label.lower() == lemma.lower():
            score = 2.0
            exact += 1
        elif lemma.lower() in aliases:
            score = 1.5
        else:
            continue
        shared = gloss_words & (_words(desc) | _words(label))
        score += 3.0 * len(shared) / max(1, min(len(gloss_words), 6))
        zh = {z for z in (e.get('labels', {}).get(k, {}).get('value')
                          for k in ('zh-tw', 'zh-hant', 'zh')) if z}
        if natives & zh:
            score += 3.0
        elif any(z in n or n in z for z in zh for n in natives):  # 杯 / 杯子
            score += 2.0
        if e.get('claims', {}).get('P18'):
            score += 0.5
        if score > best_score:
            best, best_score = (qid, label, desc), score
    # The only concept named exactly the word (cup: "vessel for liquids") is
    # taken on less evidence than one of several.
    return best if best and (best_score >= 3.0 or (exact == 1 and best_score >= 2.5)) else None


def semantic_score(meta, lemma, concept):
    """How sure we are the picture shows the sense, from where it came from:
    the concept's own image (Wikidata P18) most; a file whose name and
    description mention the word, less."""
    if meta.get('p18'):
        return 0.9
    text = f"{meta.get('title', '')} {meta.get('description', '')}".lower()
    hits = sum(w in text for w in {lemma.lower(), (concept or '').lower()} if w)
    return 0.7 if hits else 0.4


# ── Open Images, Smithsonian, Openverse: the spec's three fallbacks ─────
# wikimedia_commons above is tried first, concept by concept. These three
# never found a concept to skip; auto_fetch below just asks each, in the
# sense_image policy's order, until a sense has enough pictures.

OPEN_IMAGES_INDEX = config.RAW_DATA / 'open_images.sqlite3'
# A human verified the label (Confidence=1); strong evidence, though not
# the concept's own canonical picture (Commons P18, 0.9) or an arbitrary
# aggregator match (Openverse/Smithsonian title match, 0.7).
OPEN_IMAGES_SCORE = 0.8

# Flickr licence deed URLs (Open Images' own per-image licence column) →
# our licence codes; only CC0／PD／CC BY pass allowed_license (not
# BY-SA／BY-NC／BY-ND, which Flickr also uses).
_CC_DEED = re.compile(r'creativecommons\.org/(licenses/(?P<kind>[a-z-]+)/(?P<version>[0-9.]+)|'
                      r'publicdomain/(?P<mark>zero|mark))', re.I)


def _cc_code_from_url(url: str) -> str | None:
    m_ = _CC_DEED.search(url or '')
    if not m_:
        return None
    if m_.group('mark'):
        return 'CC0' if m_.group('mark') == 'zero' else 'PUBLIC DOMAIN'
    kind, version = m_.group('kind'), m_.group('version')
    return f'CC BY {version}' if kind == 'by' else None


def _cc_code_from_slug(slug: str, version: str | None) -> str | None:
    """Openverse's own licence slugs (cc0, by, by-sa, pdm, …)."""
    slug = (slug or '').lower()
    if slug == 'cc0':
        return 'CC0'
    if slug == 'pdm':
        return 'PUBLIC DOMAIN'
    if slug == 'by':
        return f'CC BY {version}' if version else 'CC BY'
    return None  # by-sa / by-nc / by-nd / by-nc-sa / by-nc-nd: not on the allowed list


def build_open_images_index(files) -> int:
    """class-descriptions-boxable.csv (which of the ~600 boxable classes is
    "cat", "chair", …) plus the validation split's own-URL
    (validation-images-with-rotation.csv: each image's Flickr URL, licence
    and author) and human-verified-label
    (validation-annotations-human-imagelabels-boxable.csv) files → one
    local sqlite index, read by search_open_images. ~24 MB total; the full
    dataset's billions of rows aren't needed for a word's 2-3 pictures."""
    by_name = {Path(f).name: Path(f) for f in files}
    classes = by_name.get('class-descriptions-boxable.csv')
    images_csv = by_name.get('validation-images-with-rotation.csv')
    labels_csv = by_name.get('validation-annotations-human-imagelabels-boxable.csv')
    if not (classes and images_csv and labels_csv):
        raise ValueError('快照缺少 Open Images 需要的檔案（class-descriptions-boxable／'
                         'validation-images-with-rotation／validation-annotations-human-imagelabels-boxable）')
    tmp = OPEN_IMAGES_INDEX.with_suffix(f'.{os.getpid()}.tmp')
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        db.execute('CREATE TABLE classes (mid TEXT PRIMARY KEY, name TEXT)')
        db.execute('CREATE TABLE images (image_id TEXT PRIMARY KEY, url TEXT, license_url TEXT, '
                   'author TEXT, author_url TEXT, title TEXT, landing_url TEXT)')
        db.execute('CREATE TABLE labels (image_id TEXT, mid TEXT)')
        with open(classes, encoding='utf-8', newline='') as f:
            db.executemany('INSERT OR IGNORE INTO classes VALUES (?, ?)',
                           ((row[0], row[1]) for row in csv.reader(f) if len(row) >= 2))
        with open(images_csv, encoding='utf-8', newline='') as f:
            db.executemany('INSERT OR IGNORE INTO images VALUES (?, ?, ?, ?, ?, ?, ?)', (
                (r['ImageID'], r['OriginalURL'], r['License'], r.get('Author', ''),
                 r.get('AuthorProfileURL', ''), r.get('Title', ''), r.get('OriginalLandingURL', ''))
                for r in csv.DictReader(f) if r.get('OriginalURL')))
        with open(labels_csv, encoding='utf-8', newline='') as f:
            db.executemany('INSERT INTO labels VALUES (?, ?)', (
                (r['ImageID'], r['LabelName']) for r in csv.DictReader(f) if r.get('Confidence') == '1'))
        db.execute('CREATE INDEX labels_mid ON labels (mid)')
        db.execute('CREATE INDEX classes_name ON classes (name)')
        count = db.execute('SELECT count(*) FROM images').fetchone()[0]
        db.commit()
    finally:
        db.close()
    os.replace(tmp, OPEN_IMAGES_INDEX)
    return count


def search_open_images(s, sense_id, lemma):
    """Open Images candidates for [lemma]: images a human verified show one
    of its boxable classes, each with its own Flickr licence (checked here,
    one by one — not every Open Images picture is reusable)."""
    if not s.get(m.Sense, sense_id):
        raise ValueError('找不到指定詞義')
    if not OPEN_IMAGES_INDEX.exists():
        return []  # no snapshot yet: download one on the Policies page
    db = sqlite3.connect(str(OPEN_IMAGES_INDEX))
    try:
        mids = [r[0] for r in db.execute(
            'SELECT mid FROM classes WHERE lower(name) = ?', (lemma.lower(),)).fetchall()]
        if not mids:
            return []
        rows = db.execute(
            'SELECT i.image_id, i.url, i.license_url, i.author, i.author_url, i.title, i.landing_url '
            'FROM images i JOIN labels l ON l.image_id = i.image_id '
            f"WHERE l.mid IN ({','.join('?' * len(mids))}) LIMIT 20", mids).fetchall()
    finally:
        db.close()
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': 880000000 + sense_id})
    existing = {c.concept_id: c for c in s.scalars(select(m.ImageCandidate).where(
        m.ImageCandidate.sense_id == sense_id, m.ImageCandidate.source == 'open_images')).all()}
    out = []
    for image_id, url, license_url, author, author_url, title, landing_url in rows:
        license_code = _cc_code_from_url(license_url)
        if not license_code:
            continue  # by-sa / by-nc / by-nd: not on the allowed list
        record = {'title': title or lemma, 'concept': lemma, 'file_url': url, 'download_url': url,
                  'page_url': landing_url or url, 'license_code': license_code, 'license_url': license_url,
                  'author': author or author_url, 'attribution': f'{author} (Flickr／Open Images)' if author else '',
                  'description': title or ''}
        cand = existing.get(image_id)
        if cand is None:
            cand = m.ImageCandidate(sense_id=sense_id, source='open_images', query=lemma,
                                    concept_id=image_id, metadata_=record)
            s.add(cand); s.flush()
            existing[image_id] = cand
        else:
            cand.metadata_ = record
        cand.score = OPEN_IMAGES_SCORE
        out.append({'id': cand.id, 'score': cand.score, 'imported': cand.image_asset_id is not None})
    return sorted(out, key=lambda c: -c['score'])


def ingest_open_images(s, candidate_id):
    c = s.get(m.ImageCandidate, candidate_id)
    if not c:
        raise ValueError('找不到圖片候選')
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': 880000000 + c.sense_id})
    meta = c.metadata_
    if not allowed_license(meta.get('license_code')):
        raise ValueError('圖片授權不符合允許清單')
    raw = fetch(meta['download_url'], validate=check_public_image_url)
    return _finalize_image(s, c, source_key='open_images', raw=raw, license_code=meta['license_code'],
                           license_url=meta['license_url'], author=meta['author'], attribution=meta['attribution'],
                           page_url=meta['page_url'], file_url=meta['file_url'], source_image_id=c.concept_id)


def search_smithsonian(s, sense_id, lemma):
    """Smithsonian Open Access candidates for [lemma]: only media the API
    itself marks usage.access == CC0 (catalog: 只收 CC0)."""
    if not s.get(m.Sense, sense_id):
        raise ValueError('找不到指定詞義')
    url = ('https://api.si.edu/openaccess/api/v1.0/search?' + urllib.parse.urlencode({
        'q': f'online_media_type:Images AND {lemma}', 'api_key': config.SMITHSONIAN_API_KEY, 'rows': 10}))
    data = json.loads(fetch(url, validate=check_smithsonian_url))
    rows = data.get('response', {}).get('rows', [])
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': 880000000 + sense_id})
    existing = {c.concept_id: c for c in s.scalars(select(m.ImageCandidate).where(
        m.ImageCandidate.sense_id == sense_id, m.ImageCandidate.source == 'smithsonian')).all()}
    out = []
    for row in rows:
        desc = (row.get('content') or {}).get('descriptiveNonRepeating') or {}
        title = (desc.get('title') or {}).get('content') or row.get('title') or lemma
        page_url = desc.get('guid') or ''
        data_source = desc.get('data_source') or ''
        for media in (desc.get('online_media') or {}).get('media') or []:
            if media.get('type') != 'Images' or (media.get('usage') or {}).get('access') != 'CC0':
                continue
            media_id = media.get('id') or media.get('idsId')
            download_url = media.get('content') or media.get('thumbnail')
            if not media_id or not download_url:
                continue
            record = {'title': title, 'concept': lemma, 'file_url': download_url, 'download_url': download_url,
                      'page_url': page_url or download_url, 'license_code': 'CC0',
                      'license_url': 'https://creativecommons.org/publicdomain/zero/1.0/',
                      'author': data_source or 'Smithsonian Institution', 'attribution': data_source,
                      'description': title}
            cand = existing.get(media_id)
            if cand is None:
                cand = m.ImageCandidate(sense_id=sense_id, source='smithsonian', query=lemma,
                                        concept_id=media_id, metadata_=record)
                s.add(cand); s.flush()
                existing[media_id] = cand
            else:
                cand.metadata_ = record
            cand.score = semantic_score(record, lemma, lemma)
            out.append({'id': cand.id, 'score': cand.score, 'imported': cand.image_asset_id is not None})
    return sorted(out, key=lambda c: -c['score'])


def ingest_smithsonian(s, candidate_id):
    c = s.get(m.ImageCandidate, candidate_id)
    if not c:
        raise ValueError('找不到圖片候選')
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': 880000000 + c.sense_id})
    meta = c.metadata_
    if meta.get('license_code') != 'CC0':
        raise ValueError('圖片授權不符合允許清單')
    raw = fetch(meta['download_url'], validate=check_smithsonian_url)
    return _finalize_image(s, c, source_key='smithsonian', raw=raw, license_code='CC0',
                           license_url=meta['license_url'], author=meta['author'], attribution=meta['attribution'],
                           page_url=meta['page_url'], file_url=meta['file_url'], source_image_id=c.concept_id)


def search_openverse(s, sense_id, lemma):
    """Openverse candidates for [lemma] (catalog: 只作最後搜尋入口): an
    aggregator over many providers, so only licences Openverse itself marks
    cc0／pdm／by are kept, and ingest_openverse re-asks before downloading."""
    if not s.get(m.Sense, sense_id):
        raise ValueError('找不到指定詞義')
    url = ('https://api.openverse.org/v1/images/?' + urllib.parse.urlencode({
        'q': lemma, 'license': 'cc0,by,pdm', 'mature': 'false', 'page_size': 10}))
    data = json.loads(fetch(url, validate=check_openverse_api_url))
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': 880000000 + sense_id})
    existing = {c.concept_id: c for c in s.scalars(select(m.ImageCandidate).where(
        m.ImageCandidate.sense_id == sense_id, m.ImageCandidate.source == 'openverse')).all()}
    out = []
    for r in data.get('results', []):
        license_code = _cc_code_from_slug(r.get('license'), r.get('license_version'))
        oid, download_url = r.get('id'), r.get('url')
        if not license_code or not oid or not download_url:
            continue
        tags = ' '.join(str(t.get('name', '')) for t in (r.get('tags') or []))
        record = {'title': r.get('title') or lemma, 'concept': lemma, 'file_url': download_url,
                  'download_url': download_url, 'page_url': r.get('foreign_landing_url') or download_url,
                  'license_code': license_code, 'license_url': r.get('license_url') or '',
                  'author': r.get('creator') or r.get('provider') or '',
                  'attribution': r.get('attribution') or '', 'description': f"{r.get('title', '')} {tags}".strip()}
        cand = existing.get(oid)
        if cand is None:
            cand = m.ImageCandidate(sense_id=sense_id, source='openverse', query=lemma,
                                    concept_id=oid, metadata_=record)
            s.add(cand); s.flush()
            existing[oid] = cand
        else:
            cand.metadata_ = record
        cand.score = semantic_score(record, lemma, lemma)
        out.append({'id': cand.id, 'score': cand.score, 'imported': cand.image_asset_id is not None})
    return sorted(out, key=lambda c: -c['score'])


def ingest_openverse(s, candidate_id):
    c = s.get(m.ImageCandidate, candidate_id)
    if not c:
        raise ValueError('找不到圖片候選')
    s.execute(text('SELECT pg_advisory_xact_lock(:id)'), {'id': 880000000 + c.sense_id})
    meta = c.metadata_
    if not allowed_license(meta.get('license_code')):
        raise ValueError('圖片授權不符合允許清單')
    # Openverse is a last-resort aggregator over many providers' own pages
    # (catalog: 須回原站核對授權): re-ask its own index right before
    # downloading, instead of scraping each provider's HTML ourselves.
    detail = json.loads(fetch(f'https://api.openverse.org/v1/images/{c.concept_id}/',
                              validate=check_openverse_api_url))
    license_now = _cc_code_from_slug(detail.get('license'), detail.get('license_version'))
    if license_now != meta['license_code'] or not allowed_license(license_now):
        raise ValueError('來源授權已改變，請重新搜尋')
    raw = fetch(meta['download_url'], validate=check_public_image_url)
    return _finalize_image(s, c, source_key='openverse', raw=raw, license_code=license_now,
                           license_url=meta['license_url'], author=meta['author'], attribution=meta['attribution'],
                           page_url=meta['page_url'], file_url=meta['file_url'], source_image_id=c.concept_id)


def _search_wikimedia_commons(s, sense_id, lemma, gloss, native, ctx):
    """Wraps match_concept + search as one of IMAGE_SOURCES: the only source
    with its own concept id, so it is the only one that needs ``ctx`` (two
    senses of a word must not show the same Wikidata concept)."""
    concept = match_concept(lemma, gloss, native)
    if concept is None:
        return []
    qid, label, _ = concept
    if qid in ctx['used_concepts']:
        return []  # the word's earlier sense already shows this concept
    ctx['used_concepts'].add(qid)
    found = search(s, sense_id, qid, lemma)
    p18 = set(found.get('p18', []))
    out = []
    for c in found['candidates']:
        cand = s.get(m.ImageCandidate, c['id'])
        meta = {**cand.metadata_, 'p18': c['title'] in p18}
        cand.metadata_ = meta
        cand.score = semantic_score(meta, lemma, label)
        out.append({'id': c['id'], 'score': cand.score, 'imported': c['imported']})
    return sorted(out, key=lambda c: -c['score'])


# Spec order (問題回報 #3): Wikidata／Commons → Open Images → Smithsonian
# CC0 → Openverse. Each entry: (search(s, sense_id, lemma, gloss, native,
# ctx) -> ranked [{"id", "score", "imported"}], ingest(s, candidate_id)).
IMAGE_SOURCE_CHAIN = ('wikimedia_commons', 'open_images', 'smithsonian', 'openverse')
IMAGE_SOURCES = {
    'wikimedia_commons': (_search_wikimedia_commons, ingest),
    'open_images': (lambda s, sense_id, lemma, gloss, native, ctx:
                    search_open_images(s, sense_id, lemma), ingest_open_images),
    'smithsonian': (lambda s, sense_id, lemma, gloss, native, ctx:
                    search_smithsonian(s, sense_id, lemma), ingest_smithsonian),
    'openverse': (lambda s, sense_id, lemma, gloss, native, ctx:
                 search_openverse(s, sense_id, lemma), ingest_openverse),
}


def _enabled_image_sources(s, target, native) -> list[str]:
    """The sense_image policy's enabled sources, in spec order; every known
    source when the field has no policy yet (「未設定」, catalog default)."""
    from . import policies
    _, steps = policies.load_for_run(s, target, native).get('sense_image', (None, []))
    if not steps:
        return list(IMAGE_SOURCE_CHAIN)
    return [st.source for st in steps if st.enabled and st.source in IMAGE_SOURCES]


def _note_fetch_error(out: dict, exc: BaseException) -> None:
    """Classify one source failure. The next candidate or source still runs."""
    if isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 503):
        out['rate_limited'] = True
        return
    message = str(exc)
    if _is_timeout_error(exc):
        out['timed_out'] = True
        out['transient'] = True
    elif '無法辨識' in message:
        # A truncated download can look like an unknown format; retry later.
        out['transient'] = True


def english_search_term(meaning: str | None, gloss: str | None = None) -> str | None:
    """The English word to search pictures with for a non-English headword
    (card #325): the sense's English meaning (fr→en native text, else the
    English Wiktionary gloss) cut to its first item — "cat (feline)" → cat,
    "to eat" → eat, "house; home" → house, "big, large" → big. None when
    nothing English and short enough is left."""
    for text_ in (meaning, gloss):
        t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(text_ or ""))
        t = re.split(r"[;,，、/]", t)[0]
        t = re.sub(r"^(to|a|an|the)\s+", "", t.strip().lower())
        t = re.sub(r"[^a-z' -]", " ", t)
        words = t.split()
        if words and len(words) <= 3:
            return " ".join(words)
    return None


def auto_fetch(s, target, native, lemma, *, senses_per_lexeme=None, per_sense=3, sources=None,
               query=None):
    """Find and download pictures for a word's first senses, trying each
    enabled source in turn (wikimedia_commons → open_images → smithsonian →
    openverse) until a sense has ``per_sense`` pictures. Returns
    {"senses": n, "images": n, "errors": [...]}."""
    from .picture_need import PICTURE_POS, PRIMARY_ORDINAL
    if senses_per_lexeme is None:
        senses_per_lexeme = PRIMARY_ORDINAL
    term = (query or lemma).strip() or lemma
    chain = [src for src in (sources if sources is not None else
                             _enabled_image_sources(s, target, native)) if src in IMAGE_SOURCES]
    rows = s.execute(text('''SELECT sn.id, d.text AS gloss, l.pos, t.text AS native
        FROM senses sn JOIN lexemes l ON l.id = sn.lexeme_id
        LEFT JOIN definitions d ON d.sense_id = sn.id AND d.language = l.language
        LEFT JOIN sense_translations t ON t.sense_id = sn.id AND t.native_language = :native
        WHERE l.language = :target AND l.normalized = :lemma AND l.status = 'full'
          AND l.pos = :pos AND sn.ordinal < :k ORDER BY l.id, sn.ordinal'''),
        {'target': target, 'native': native, 'lemma': lemma, 'k': senses_per_lexeme,
         'pos': PICTURE_POS}).all()
    out = {'senses': 0, 'images': 0, 'errors': [], 'incomplete_senses': 0,
           'rate_limited': False, 'timed_out': False, 'transient': False, 'permanent': False}
    # Two senses of one word matching the same picture would get it twice:
    # a file already used for this word is not used again.
    used_assets = set(s.scalars(select(m.SenseImage.image_asset_id).join(
        m.Sense, m.Sense.id == m.SenseImage.sense_id).join(m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id)
        .where(m.Lexeme.language == target, m.Lexeme.normalized == lemma)).all())
    ctx = {'used_concepts': set()}
    for sense_id, gloss, pos, meaning in rows:
        have = s.scalar(select(func.count()).select_from(m.SenseImage).where(
            m.SenseImage.sense_id == sense_id, m.SenseImage.review_status != 'rejected'))
        if have >= per_sense:
            out['senses'] += 1
            continue
        got, attempted = have, False
        # Every picture source is English (Wikidata labels, Open Images
        # classes, Openverse queries): a French headword searches by the
        # sense's English meaning instead (chat → cat), card #325.
        sense_term = term
        if target != "en" and not query:
            sense_term = english_search_term(meaning if native == "en" else None, gloss)
            if not sense_term:
                out['incomplete_senses'] += 1
                out['errors'].append(f'詞義 #{sense_id}：沒有英文詞義可用來搜圖')
                continue
        for source_key in chain:
            if got >= per_sense:
                break
            search_fn, ingest_fn = IMAGE_SOURCES[source_key]
            try:
                ranked = search_fn(s, sense_id, sense_term, gloss, meaning, ctx)
            except (ValueError, KeyError, OSError) as e:
                _note_fetch_error(out, e)
                out['errors'].append(f'{source_key} 詞義 #{sense_id}：{e}')
                continue
            if not ranked:
                continue
            attempted = True
            for c in ranked:
                if got >= per_sense:
                    break
                if c.get('imported'):
                    continue
                if c['score'] < 0.7:
                    continue  # stays a candidate for manual review; not downloaded
                try:
                    bound = ingest_fn(s, c['id'])
                except (ValueError, OSError) as e:
                    _note_fetch_error(out, e)
                    out['errors'].append(f"{source_key} #{c['id']}：{e}")
                    continue
                binding = s.get(m.SenseImage, bound['id'])
                if binding.image_asset_id in used_assets:
                    s.delete(binding)  # the same file under another sense of this word
                    continue
                used_assets.add(binding.image_asset_id)
                binding.semantic_score = c['score']
                # One representative picture a sense (the first, best one).
                binding.role = 'representative' if got == 0 else 'context'
                binding.ordinal = got
                got += 1
                out['images'] += 1
        if attempted:
            out['senses'] += 1
        if got == 0:
            out['incomplete_senses'] += 1
    if (out['incomplete_senses'] and out['errors'] and not out['rate_limited']
            and not out['transient'] and not out['timed_out']
            and all(_is_permanent_fetch_error(err) for err in out['errors'])):
        out['permanent'] = True
    return out


# ── AI labels ─────────────────────────────────────────────────────────
# Every downloaded picture goes through the local vision model, like a
# learner's photo: the labels and where they are. A label that is the
# sense's own word confirms the picture (the spec's semantic check).

CEFR_LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')
# A label passes only when the vision model, checking it against the picture
# again, is at least this sure it is shown (the user: 辨識 ≥ 80 以上才通過).
TAG_PASS = 0.8
# Default import/tag path uses one CEFR-band call (~3 labels per A1–C2).
# Set LEXICON_TAG_MODE=legacy to restore the multi-focus TAG_LOOKS loop.
TAG_MODE = os.environ.get('LEXICON_TAG_MODE', 'cefr').strip().lower() or 'cefr'
CEFR_PER_LEVEL = int(os.environ.get('LEXICON_CEFR_PER_LEVEL', '3'))
# Owner decision #114 C: up to 24 labels a picture — at most four a level;
# a level under three (CEFR_PER_LEVEL) is still a gap.
CEFR_LEVEL_MAX = int(os.environ.get('LEXICON_CEFR_LEVEL_MAX', '4'))
TAGS_WANTED = CEFR_PER_LEVEL * len(CEFR_LEVELS)
TAGS_MAX = CEFR_LEVEL_MAX * len(CEFR_LEVELS)
# Empty difficulty bands are valid. Repeated requests to fill them amplify
# latency and encourage synonyms/meta labels instead of new visible evidence.
CEFR_TAG_ROUNDS = int(os.environ.get('LEXICON_CEFR_TAG_ROUNDS', '1'))
CEFR_EXPAND_VOCABULARY = os.environ.get(
    'LEXICON_CEFR_EXPAND_VOCABULARY', '0').strip().lower() in {'1', 'true', 'yes', 'on'}
CEFR_BEGINNER_LEVELS = ('A1', 'A2')
CEFR_BEGINNER_MAX = int(os.environ.get(
    'LEXICON_CEFR_BEGINNER_MAX', str(CEFR_PER_LEVEL)))
# When 1/true: skip the second /score vision pass and assign provisional scores
# for grounded labels (point/box or CEFR band). Later tag_pending/rescore can refine.
DEFER_TAG_SCORE = os.environ.get('LEXICON_DEFER_TAG_SCORE', '0').strip().lower() in {
    '1', 'true', 'yes', 'on'}
# Legacy multi-look focuses (only when TAG_MODE=legacy).
TAG_LOOKS = ('', 'harder', 'descriptions')


def labelled(asset) -> bool:
    """A settled picture's labels confirm or take it off a word, and share it.
    Levels it can't fill are gaps (owner decision A), not a reason to wait:
    waiting left red / cluster / stem approved on an apple pile whose labels
    no longer name them."""
    return asset.tag_status == 'done'


def tag_level(tag: dict) -> str | None:
    """The CEFR-list level (owner decision A); never the vision model's own."""
    level = str(tag.get('cefr') or '').strip().upper()
    return level if level in CEFR_LEVELS else None


def cefr_counts(tags: list[dict] | None) -> dict[str, int]:
    counts = {level: 0 for level in CEFR_LEVELS}
    for tag in tags or []:
        level = tag_level(tag)
        if level:
            counts[level] += 1
    return counts


def cefr_gaps(tags: list[dict] | None) -> list[str]:
    counts = cefr_counts(tags)
    return [level for level in CEFR_LEVELS if counts[level] < CEFR_PER_LEVEL]


def cefr_complete(tags: list[dict] | None) -> bool:
    return not cefr_gaps(tags) and all(tag_level(tag) for tag in tags or [])


CEFR_RANK = {level: index for index, level in enumerate(CEFR_LEVELS)}
PHRASE_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'at', 'by', 'for',
    'from', 'with', 'without', 'into', 'over', 'under', 'up', 'down',
}


def _morphology_lemmas(word: str) -> list[str]:
    """Conservative English inflection candidates, verified against our lexicon later."""
    out: list[str] = []
    if word.endswith('ies') and len(word) > 4:
        out.append(word[:-3] + 'y')
    if word.endswith('ves') and len(word) > 4:
        out.extend((word[:-3] + 'f', word[:-3] + 'fe'))
    if word.endswith('es') and len(word) > 3:
        out.extend((word[:-2], word[:-1]))
    elif word.endswith('s') and not word.endswith(('ss', 'us', 'is')) and len(word) > 3:
        out.append(word[:-1])
    if word.endswith('ied') and len(word) > 4:
        out.append(word[:-3] + 'y')
    elif word.endswith('ed') and len(word) > 3:
        stem = word[:-2]
        out.extend((stem, stem + 'e'))
        if len(stem) > 2 and stem[-1] == stem[-2]:
            out.append(stem[:-1])
    if word.endswith('ing') and len(word) > 5:
        stem = word[:-3]
        out.extend((stem, stem + 'e'))
        if len(stem) > 2 and stem[-1] == stem[-2]:
            out.append(stem[:-1])
    return list(dict.fromkeys(candidate for candidate in out if candidate and candidate != word))


CEFR_POS = {'adjective': 'adj', 'adverb': 'adv', 'preposition': 'prep'}


def _dictionary_cefr(s, words: list[str], include_exact: bool = True,
                     pos: str | None = None):
    candidates = list(dict.fromkeys(w for w in words if w))
    if not candidates:
        return None
    queries = []
    if include_exact:
        queries.append(select(m.Lexeme.normalized, m.Lexeme.cefr, m.Lexeme.pos).where(
            m.Lexeme.language == 'en', m.Lexeme.normalized.in_(candidates),
            m.Lexeme.cefr.in_(CEFR_LEVELS)))
    queries.append(select(m.Lexeme.normalized, m.Lexeme.cefr, m.Lexeme.pos).join(
        m.Form, m.Form.lexeme_id == m.Lexeme.id).where(
        m.Lexeme.language == 'en', m.Lexeme.cefr.in_(CEFR_LEVELS),
        (func.lower(m.Form.form).in_(candidates)
         | func.lower(m.Form.normalized).in_(candidates))))
    found = []
    for query in queries:
        found.extend(s.execute(query).all())
    if not found:
        return None
    wanted_pos = CEFR_POS.get(str(pos or '').lower(), str(pos or '').lower())
    same_pos = [row for row in found if row[2] == wanted_pos]
    lemma, level, _ = max(same_pos or found, key=lambda row: CEFR_RANK[row[1]])
    return str(lemma), str(level)


_LIST_POS = {'adjective': 'adj.', 'adj': 'adj.', 'adverb': 'adv.', 'adv': 'adv.'}


def _list_level(s, word: str, pos: str):
    """(level, lemma) from the CEFR-J / Octanove list for this word's part of
    speech — the word itself, then its dictionary lemma (clustered → cluster,
    holding → hold), then its regular inflection stems. None when the list
    has no level for that part of speech."""
    from .adapters.local import cefr_list
    listed = cefr_list()
    want = _LIST_POS.get(pos, pos)
    lemmas = [word]
    lemmas += [w for (w,) in s.execute(select(m.Lexeme.normalized).join(
        m.Form, m.Form.lexeme_id == m.Lexeme.id).where(
        m.Lexeme.language == 'en', func.lower(m.Form.form) == word)).all()]
    lemmas += _morphology_lemmas(word)
    for lemma in dict.fromkeys(lemmas):
        level = (listed.get(lemma) or (None, {}))[1].get(want)
        if level in CEFR_LEVELS:
            return level, lemma
    return None


def _easiest_listed(word: str):
    """The easiest level the CEFR list gives a word under any part of speech."""
    from .adapters.local import cefr_list
    levels = [lv for lv in (cefr_list().get(word) or (None, {}))[1].values() if lv in CEFR_LEVELS]
    return min(levels, key=CEFR_RANK.get) if levels else None


def _base_candidates(word: str, s=None) -> list[str]:
    """Words a derived word is built on: inflection stems, suffix stems with
    the usual spelling repairs (arched → arch, sunny → sun, happily → happy),
    and the word without a prefix (unripe → ripe)."""
    from .adapters.local import PREFIX, SUFFIX_POS
    out = list(_morphology_lemmas(word))
    # A single consonant after a short vowel before -ed/-ing means the base
    # ends in -e (striped ← stripe, baked ← bake; strip would be stripped).
    for suf in ('ed', 'ing'):
        stem = word[:-len(suf)]
        if word.endswith(suf) and re.search(r'[^aeiou][aeiou][^aeiouwxy]$', stem) \
                and stem + 'e' in out and stem in out:
            out.remove(stem + 'e')
            out.insert(out.index(stem), stem + 'e')
    suffixes = set(SUFFIX_POS) | {'ed', 'ing', 'ly', 'ness', 'ful', 'less', 'y', 'ic', 'ish'}
    for suf in sorted(suffixes, key=len, reverse=True):
        stem = word[:-len(suf)]
        if word.endswith(suf) and len(stem) >= 3:
            out += [stem, stem + 'e']
            if stem[-1] == stem[-2]:
                out.append(stem[:-1])          # sunny → sun, shopping → shop
            if stem.endswith('i'):
                out.append(stem[:-1] + 'y')    # happily → happy
    for pre in PREFIX:
        if word.startswith(pre) and len(word) - len(pre) >= 3:
            out.append(word[len(pre):])
    if s is not None:  # last: irregular forms the dictionary stores (lit → light);
        # spelling stems first, as a rare dialect entry can list baked under book
        out += [w for (w,) in s.execute(select(m.Lexeme.normalized).join(
            m.Form, m.Form.lexeme_id == m.Lexeme.id).where(
            m.Lexeme.language == 'en', func.lower(m.Form.form) == word)).all()]
    return [w for w in dict.fromkeys(out) if w != word]


def _base_level(word: str, s=None):
    """(level, base) for a word the list lacks, from the word it is derived
    from (owner decision 2026-10-06: 衍生字跟著原形的等級), or for a closed
    compound from its two listed parts (sunlit → sun + lit): the harder part."""
    for base in _base_candidates(word, s):
        level = _easiest_listed(base)
        if level:
            return level, base
    for cut in range(3, len(word) - 2):
        a, b = word[:cut], word[cut:]
        la = _easiest_listed(a) or _base_level_simple(a, s)
        lb = _easiest_listed(b) or _base_level_simple(b, s)
        if la and lb:
            return max(la, lb, key=CEFR_RANK.get), f'{a}+{b}'
    return None


def _base_level_simple(word: str, s=None):
    for base in _base_candidates(word, s):
        level = _easiest_listed(base)
        if level:
            return level
    return None


def classify_tag_cefr(s, tag: dict, *, include_exact: bool = True) -> dict:
    """A label's level (owner decisions, 問題回報 option A + 2026-10-06):
    1. the CEFR-J / Octanove list's level for the same word and part of
       speech (its lemma: holding → hold);
    2. a word the list lacks takes the level of the word it is derived from
       (arched → arch B2), shown as 「衍生」;
    3. a phrase takes its hardest word (each word by rule 1/2);
    4. only then a word-frequency estimate, shown as 「估算」.
    The vision model's own level is never used (fruit C1, flower C2)."""
    from .adapters.base import frequency_profile, zipf
    tag = dict(tag)
    for k in ('cefr', 'cefrSource', 'cefrLemma', 'cefrCoreWord', 'cefrComponents'):
        tag.pop(k, None)
    word = ' '.join(str(tag.get('word') or '').strip().lower().split())
    pos = str(tag.get('pos') or '').strip().lower()
    if not word:
        return tag
    hit = _list_level(s, word, pos)
    if hit:
        tag['cefr'], tag['cefrSource'] = hit[0], 'cefrj'
        if hit[1] != word:
            tag['cefrLemma'] = hit[1]
        return tag
    parts = [p for p in re.findall(r"[a-z]+(?:'[a-z]+)?", word) if p not in PHRASE_STOPWORDS]
    if len(parts) == 1:
        base = _base_level(parts[0], s)
        # The tagger's part of speech is often wrong (furniture tagged as an
        # adjective, person/feather as adjectives, number as an adverb): when
        # the exact word is on the list under some *other* part of speech,
        # never guess higher than that - it beats a derivation/letter-split
        # guess (furniture → estimate B1, person → per+son B1, number → numb
        # C1) but a rarer, harder sense of the same spelling (standing noun
        # C2, "social standing") must not override a good easier guess
        # (standing adj → stand A2) just because the spelling matches.
        other_pos = _easiest_listed(word)
        if other_pos:
            # Never harder than whatever this word would otherwise get (the
            # derivation guess, or the frequency estimate if there is none):
            # a wrong pos must only ever make a label easier, never harder.
            ceiling = base[0] if base else frequency_profile(zipf(word, 'en'))['cefr']
            if CEFR_RANK[other_pos] <= CEFR_RANK[ceiling]:
                tag['cefr'], tag['cefrSource'] = other_pos, 'cefrj'
                return tag
        if base:
            tag['cefr'], tag['cefrSource'], tag['cefrLemma'] = base[0], 'base', base[1]
            return tag
    elif len(parts) > 1:
        levels = []
        for p in parts:
            lv = _easiest_listed(p) or (_base_level(p, s) or (None,))[0]
            levels.append((p, lv))
        if all(lv for _, lv in levels):
            core = max(levels, key=lambda x: CEFR_RANK[x[1]])
            tag['cefr'], tag['cefrSource'], tag['cefrCoreWord'] = core[1], 'phrase', core[0]
            return tag
    tag['cefr'] = frequency_profile(zipf(word, 'en'))['cefr']
    tag['cefrSource'] = 'estimate'  # shown as 「估算」
    return tag


def _old_classify_tag_cefr(s, tag: dict, *, include_exact: bool = True) -> dict:
    """Previous rule (dictionary or vision level); kept for comparison only."""
    tag = dict(tag)
    word = ' '.join(str(tag.get('word') or '').strip().lower().split())
    model_level = str(tag.get('modelLevel') or tag.get('cefr') or '').strip().upper()
    if model_level in CEFR_LEVELS:
        tag['modelLevel'] = model_level
    pos = str(tag.get('pos') or '').strip().lower()
    match = _dictionary_cefr(s, [word], include_exact=include_exact, pos=pos) if word else None
    source = ('lexicon' if include_exact and match and match[0] == word
              else ('form' if match else None))
    if not match and word:
        match = _dictionary_cefr(s, _morphology_lemmas(word), include_exact=True, pos=pos)
        source = 'morphology' if match else None
    if not match and (' ' in word or '-' in word):
        parts = [part for part in re.findall(r"[a-z]+(?:'[a-z]+)?", word)
                 if part not in PHRASE_STOPWORDS]
        resolved = []
        for part in parts:
            part_match = _dictionary_cefr(
                s, [part, *_morphology_lemmas(part)], include_exact=True)
            if not part_match:
                resolved = []
                break
            resolved.append((part, part_match[0], part_match[1]))
        if resolved:
            core = max(resolved, key=lambda item: CEFR_RANK[item[2]])
            match = (word, core[2])
            source = 'phrase'
            tag['cefrCoreWord'] = core[0]
            tag['cefrComponents'] = [
                {'word': part, 'lemma': lemma, 'cefr': level}
                for part, lemma, level in resolved
            ]
    dictionary_level = match[1] if match else None
    level = dictionary_level or (model_level if include_exact and model_level in CEFR_LEVELS else None)
    if level:
        tag['cefr'] = level
        tag['cefrSource'] = source or 'vision'
        if match and source in {'form', 'morphology'}:
            tag['cefrLemma'] = match[0]
    return tag


def own_words(s, asset) -> set[str]:
    """The words a picture is attached to (not rejected): their labels are
    the reason the picture is there, so the per-level cap never drops them
    (balcony A2 was pushed out by column, furniture and plant)."""
    if asset is None or asset.id is None:
        return set()
    return {w for (w,) in s.execute(select(m.Lexeme.normalized).join(
        m.Sense, m.Sense.lexeme_id == m.Lexeme.id).join(
        m.SenseImage, m.SenseImage.sense_id == m.Sense.id).where(
        m.SenseImage.image_asset_id == asset.id,
        m.SenseImage.review_status != 'rejected')).all()}


def _select_cefr_tags(tags: list[dict], keep: set[str] | frozenset = frozenset()):
    """The best verified labels in every CEFR band, up to CEFR_LEVEL_MAX (four)
    — plus, always, the labels naming the picture's own words (``keep``)."""
    kept, overflow = [], []
    for level in CEFR_LEVELS:
        band = sorted((tag for tag in tags if tag_level(tag) == level),
                      key=lambda tag: -(tag.get('score') or 0))
        own = [tag for tag in band if any(shows_word([tag], w) for w in keep)]
        rest = [tag for tag in band if tag not in own]
        room = max(0, CEFR_LEVEL_MAX - len(own))
        kept.extend(own + rest[:room])
        overflow.extend(rest[room:])
    overflow.extend(tag for tag in tags if tag_level(tag) is None)
    return kept, overflow


def expand_visible_vocabulary(s, data: bytes, mime: str | None, passed: list[dict],
                              seen: list[str]) -> tuple[list[dict], list[dict]]:
    """Generate harder wording for already-grounded evidence, then verify it visually."""
    gaps = cefr_gaps(passed)
    if not CEFR_EXPAND_VOCABULARY or not gaps or not passed:
        return [], []
    # Prefer qualities/actions because one object can truthfully carry several
    # graded descriptions (clear / transparent / reflective). Keep the prompt small.
    priority = {'adjective': 0, 'adj': 0, 'verb': 1, 'adverb': 2, 'adv': 2,
                'noun': 3, 'phrase': 4}
    bases = sorted(passed, key=lambda tag: (
        priority.get(str(tag.get('pos') or '').lower(), 5), -(tag.get('score') or 0)))[:8]
    items = []
    for index, tag in enumerate(bases):
        word = str(tag.get('word') or '').strip()
        items.append({
            'id': str(index),
            'text': (f'{word}; part of speech: {tag.get("pos") or "word"}; '
                     f'visible meaning: the photo visibly shows {word}; '
                     f'CEFR levels still needed: {", ".join(gaps)}'),
        })
    request = urllib.request.Request(
        config.AI_URL.rstrip('/') + '/translate',
        data=json.dumps({'lang': 'en', 'native': 'zh-TW', 'kind': 'synonyms',
                         'items': items}).encode(), method='POST',
        headers={'X-API-Key': config.AI_KEY, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            output = json.loads(response.read())
    except (urllib.error.URLError, OSError):
        return [], []  # optional fast expansion; ordinary vision labels remain valid
    note_tagger_stages(output)

    by_id = {str(item.get('id')): str(item.get('text') or '')
             for item in output.get('items', [])}
    known = {word.strip().lower() for word in seen}
    candidates = []
    for index, base in enumerate(bases):
        raw_words = re.split(r'[,;\n]+', by_id.get(str(index), ''))
        for raw in raw_words:
            word = ' '.join(raw.strip().lower().strip(' ."\'').split())
            if not word or word in known or len(word) > 40 or len(word.split()) > 3:
                continue
            tag = classify_tag_cefr(s, {
                'word': word, 'pos': base.get('pos') or 'noun',
                'point': base.get('point'), 'box': base.get('box'),
                'derivedFrom': base.get('word'),
            })
            if tag_level(tag) not in gaps:
                continue
            known.add(word)
            candidates.append(tag)
            if len(candidates) >= 24:
                break
        if len(candidates) >= 24:
            break
    score_tags(data, candidates, mime, defer=False)
    accepted = [tag for tag in candidates if (tag.get('score') or 0) >= TAG_PASS]
    rejected = [tag for tag in candidates if (tag.get('score') or 0) < TAG_PASS]
    for tag in rejected:
        tag.setdefault('dropReason', '高階替代詞的圖片辨識分數低於 80%')
    return accepted, rejected


class TaggerUnavailable(ValueError):
    """The tagging service can't be reached; the picture stays pending."""


def _block_unsafe(s, asset) -> None:
    """Quarantine explicit adult content and reject every word binding."""
    asset.safety_status = 'blocked'
    asset.tag_status = 'failed'
    asset.tags = []
    asset.dropped_tags = []
    asset.tagged_at = datetime.now(timezone.utc)
    for binding in s.scalars(select(m.SenseImage).where(
            m.SenseImage.image_asset_id == asset.id)).all():
        if binding.review_status != 'rejected':
            binding.review_status = 'rejected'
            s.add(m.ImageReview(sense_image_id=binding.id, decision='rejected',
                                note='成人內容安全檢查未通過（自動）'))


def _cap_beginner_tags(tags: list[dict], beginner_max: int | None = None):
    """Keep at most ``beginner_max`` A1 and A2 tags (by score); return (kept, overflow)."""
    if beginner_max is None:
        beginner_max = CEFR_BEGINNER_MAX
    beginner_max = max(1, int(beginner_max))
    ordered = sorted(tags, key=lambda t: -(t.get('score') or 0))
    counts = {lv: 0 for lv in CEFR_BEGINNER_LEVELS}
    kept, overflow = [], []
    for t in ordered:
        level = str(t.get('cefr') or t.get('modelLevel') or '').strip().upper()
        if level in counts:
            if counts[level] >= beginner_max:
                overflow.append(t)
                continue
            counts[level] += 1
        kept.append(t)
    return kept, overflow



# The picture being labelled, so score_tags' request can name it on the 排程 page.
PICTURE: contextvars.ContextVar[int | None] = contextvars.ContextVar('picture', default=None)

# Stage timing per labelling run (問題回報 #229): one JSONL line per picture, so the
# ≤10 s target is measured stage by stage before anything is tuned.
TAG_TIMING_LOG = Path(os.environ.get('LEXICON_TAG_TIMING_LOG',
                                     config.HOME / 'logs' / 'tag_timing.jsonl'))
TAG_TIMING: contextvars.ContextVar[list | None] = contextvars.ContextVar('tag_timing', default=None)


class tag_stage:
    """``with tag_stage('cefr'):`` adds {'stage', 'ms', 'tagger': [...]} to the run."""

    def __init__(self, name: str):
        self.entry = {'stage': name, 'ms': 0, 'tagger': []}

    def __enter__(self):
        stages = TAG_TIMING.get()
        if stages is not None:
            stages.append(self.entry)
        self.started = time.perf_counter()
        return self.entry

    def __exit__(self, *exc):
        self.entry['ms'] = round((time.perf_counter() - self.started) * 1000)
        return False


def note_tagger_stages(payload) -> None:
    """The tagger's own split (queue / prep / model / prompt / decode) for the open stage."""
    stages = TAG_TIMING.get()
    if stages and isinstance(payload, dict) and isinstance(payload.get('stages'), dict):
        stages[-1]['tagger'].append(payload['stages'])


def _write_tag_timing(asset_id, stages: list, seconds: float, outcome: str) -> None:
    line = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'asset': asset_id, 'outcome': outcome, 'totalMs': round(seconds * 1000),
            'rounds': CEFR_TAG_ROUNDS, 'mode': TAG_MODE, 'stages': stages}
    try:
        TAG_TIMING_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(TAG_TIMING_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(line, ensure_ascii=False, separators=(',', ':')) + '\n')
    except OSError:
        pass  # timing is diagnostic only; never fail a picture over it


TAG_MAX_ATTEMPTS = 3


def _tag_response(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('candidates'), list):
        raise ValueError('Invalid tag response: candidates must be a list')
    if any(not isinstance(candidate, dict) for candidate in payload['candidates']):
        raise ValueError('Invalid tag response: candidate must be an object')
    return payload


def _tag_http_failure(error):
    """Preserve the tagger's model diagnostic, not just 'HTTP 422'.

    Availability failures must never spend a picture's retry budget.
    Only the bounded JSON error field is retained, not an arbitrary HTML body.
    """
    if error.code >= 500 or error.code == 429:
        return TaggerUnavailable(f'標籤服務暫時無法使用：HTTP {error.code}')
    detail = ''
    try:
        payload = json.loads(error.read(8192))
        if isinstance(payload, dict) and isinstance(payload.get('error'), str):
            detail = payload['error'][:1500]
    except (ValueError, OSError, TypeError):
        pass
    return ValueError(f'AI 標籤失敗：HTTP {error.code}' + (f': {detail}' if detail else ''))


def _tag_attempt(asset, run):
    """Keep diagnostics even when callers intentionally handle a failed attempt.

    Three consecutive attempts, with 1/5 minute backoff. Successful work resets
    the budget. Blocked content is terminal regardless of the remaining budget.
    The tagging *service* being down or slow (TaggerUnavailable: 502/connection
    refused/timeout) is never this picture's fault — it is left exactly as it
    was, so a stretch of outage or slot exhaustion never burns a picture's
    budget. Callers must commit the session after a handled exception.
    """
    try:
        result = run()
    except TaggerUnavailable:
        raise
    except (ValueError, OSError) as exc:
        asset.tag_attempts = (asset.tag_attempts or 0) + 1
        asset.tag_status = 'failed'
        asset.tag_error = f'{type(exc).__name__}: {exc}'[:2000]
        retry = asset.safety_status != 'blocked' and asset.tag_attempts < TAG_MAX_ATTEMPTS
        asset.tag_retry_at = (datetime.now(timezone.utc) + timedelta(
            seconds=60 if asset.tag_attempts == 1 else 300)) if retry else None
        raise
    else:
        asset.tag_attempts = 0
        asset.tag_error = None
        asset.tag_retry_at = None
        return result


def tag_asset(s, asset_id):
    asset = s.get(m.ImageAsset, asset_id)
    if asset is None:
        raise ValueError('圖片不存在')
    stages: list = []
    token = TAG_TIMING.set(stages)
    started, outcome = time.perf_counter(), 'error'
    try:
        result = _tag_attempt(asset, lambda: _tag_asset(s, asset_id))
        outcome = 'ok'
        return result
    finally:
        TAG_TIMING.reset(token)
        _write_tag_timing(asset_id, stages, time.perf_counter() - started, outcome)


def _tag_asset(s, asset_id):
    asset = s.get(m.ImageAsset, asset_id)
    if not asset or asset.status != 'ready' or not asset.path:
        raise ValueError('圖片尚未下載')
    data = (config.MEDIA / asset.path).read_bytes()
    # For the 排程 page's 「Qwen 正在做什麼」 (URL-encoded: headers are Latin-1).
    PICTURE.set(asset_id)
    doing = urllib.parse.quote(f"圖片 #{asset_id} 產生標籤（{'、'.join(sorted(own_words(s, asset))[:2]) or '未連結單字'}）")

    def ask(extra=''):
        request = urllib.request.Request(
            config.AI_URL.rstrip('/') + '/tag?level=B1&lang=en&native=zh-TW' + extra, data=data,
            method='POST', headers={'X-API-Key': config.AI_KEY, 'X-Activity': doing,
                                    'X-Inference-Priority': 'background',
                                    'X-Activity-Ref': f'image:{asset_id}',
                                    'Content-Type': asset.mime or 'image/jpeg'})
        with urllib.request.urlopen(request, timeout=300) as response:
            return _tag_response(json.loads(response.read()))

    def ask_cefr(exclude: list[str], levels: list[str], counts: dict[str, int]):
        qs = urllib.parse.urlencode({
            'mode': 'cefr', 'lang': 'en', 'native': 'zh-TW',
            'per_level': str(CEFR_PER_LEVEL),
            'levels': ','.join(levels),
            'counts': ','.join(f'{level}:{counts[level]}' for level in CEFR_LEVELS),
            # The backend already retries with fresh exclusions. A second
            # generation inside every request doubled GPU time and often
            # produced more words for bands that were already nearly full.
            'topup': '0',
            **({'exclude': ','.join(exclude[:60])} if exclude else {}),
        })
        request = urllib.request.Request(
            config.AI_URL.rstrip('/') + '/tag?' + qs, data=data, method='POST',
            headers={'X-API-Key': config.AI_KEY, 'X-Activity': doing,
                     'X-Inference-Priority': 'background',
                     'X-Activity-Ref': f'image:{asset_id}',
                     'Content-Type': asset.mime or 'image/jpeg'})
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = json.loads(response.read())
        note_tagger_stages(payload)
        return _tag_response(payload)

    keep = own_words(s, asset)
    if asset.safety_status == 'safe':
        existing = [classify_tag_cefr(s, tag) for tag in (asset.tags or [])]
        # A deferred 0.80 is only a placeholder from fast imports. Before it can
        # count toward the six-band requirement, replace it with a real score.
        with tag_stage('rescore-existing'):
            score_tags(data, existing, asset.mime, defer=False)
        passed = [tag for tag in existing
                  if tag_level(tag) and (tag.get('score') or 0) >= TAG_PASS]
        passed, old_overflow = _select_cefr_tags(passed, keep)
        dropped = list(old_overflow)
    else:
        # Unchecked pixels must pass the combined safety + label call. Do not
        # trust or expose labels produced before safety filtering existed.
        passed, dropped = [], []
    seen = [str(tag.get('word', '')) for tag in passed]
    model = asset.tag_model or ''
    try:
        if TAG_MODE in ('cefr', 'bands', 'cefr-bands'):
            stalled_rounds = 0
            for _round in range(max(1, CEFR_TAG_ROUNDS)):
                gaps = cefr_gaps(passed)
                if not gaps:
                    break
                passed_before = len(passed)
                with tag_stage(f'cefr-{_round + 1}'):
                    out = ask_cefr(seen, gaps, cefr_counts(passed))
                model = model or str(out.get('model', ''))
                new = []
                known = {w.lower() for w in seen}
                for c in out.get('candidates', []):
                    word = str(c.get('word', '')).strip()
                    if word and word.lower() not in known:
                        seen.append(word)
                        known.add(word.lower())
                        tag = {'word': word, 'pos': c.get('pos') or 'noun',
                               'point': c.get('point'), 'box': c.get('box')}
                        # Recognition supplies no CEFR. Classification below
                        # comes exclusively from the dictionary pipeline.
                        if c.get('visualConfidence') is not None:
                            tag['visualConfidence'] = c.get('visualConfidence')
                        new.append(classify_tag_cefr(s, tag))
                new, aside = split_made_up(s, new, seen)
                dropped.extend(aside)
                seen.extend(t['word'] for t in new if t.get('splitFrom'))
                with tag_stage(f'score-{_round + 1}'):
                    score_tags(data, new, asset.mime, defer=DEFER_TAG_SCORE)
                for tag in new:
                    if tag_level(tag) and (tag.get('score') or 0) >= TAG_PASS:
                        passed.append(tag)
                    else:
                        dropped.append(tag)
                passed, overflow = _select_cefr_tags(passed, keep)
                for tag in overflow:
                    tag.setdefault('dropReason', '該等級已滿 4 個')
                dropped.extend(overflow)
                if cefr_complete(passed):
                    break
                stalled_rounds = stalled_rounds + 1 if len(passed) == passed_before else 0
                if stalled_rounds >= 2:
                    break
            with tag_stage('expand'):
                expanded, rejected = expand_visible_vocabulary(
                    s, data, asset.mime, passed, seen)
            passed.extend(expanded)
            dropped.extend(rejected)
            passed, overflow = _select_cefr_tags(passed, keep)
            for tag in overflow:
                tag.setdefault('dropReason', '該等級已滿 4 個')
            dropped.extend(overflow)
            if model and 'cefr' not in (model or '').lower():
                model = f'cefr+{model}'
            else:
                model = model or 'cefr'
        else:
            for focus in TAG_LOOKS:
                extra = (f'&focus={focus}' if focus else '') + (
                    '&exclude=' + urllib.parse.quote(','.join(seen)) if seen else '')
                out = ask(extra)
                model = model or str(out.get('model', ''))
                new = []
                for c in out.get('candidates', []):
                    word = str(c.get('word', '')).strip()
                    if word and word.lower() not in {w.lower() for w in seen}:
                        seen.append(word)
                        new.append({'word': word, 'pos': c.get('pos'),
                                    'point': c.get('point'), 'box': c.get('box')})
                new, aside = split_made_up(s, new, seen)
                dropped.extend(aside)
                score_tags(data, new, asset.mime, defer=DEFER_TAG_SCORE)
                for t in new:
                    (passed if (t.get('score') or 0) >= TAG_PASS else dropped).append(t)
                if len(passed) >= TAGS_WANTED:
                    break
    except urllib.error.HTTPError as e:
        if e.code == 451:
            _block_unsafe(s, asset)
            raise ValueError('成人內容安全檢查未通過') from e
        raise _tag_http_failure(e) from e
    except (urllib.error.URLError, OSError) as e:
        # The tagging service is down or busy: try this picture again later.
        raise TaggerUnavailable(f'標籤服務無法連線：{e}') from e
    except ValueError as e:
        asset.tag_status = 'failed'
        raise ValueError(f'AI 標籤失敗：{e}') from e
    # One full labelling attempt settles the picture: a level the picture
    # cannot fill with three listed words stays a gap (cefr_gaps, shown as
    # 「缺漏」) instead of being asked again and again (owner decision A).
    _settle(s, asset, passed, dropped, model, done=True)
    return asset.tags



_PHRASE_CACHE: dict[str, bool] = {}


def dictionary_phrase(s, word: str) -> bool:
    """A label of several words must be a dictionary phrase (in the lexicon
    or Wiktionary): ceiling fan, palm tree, in a row — not a description made
    up for one picture (vehicle ahead, sunlit area, dark surface) or a brand
    (lebara mobile). 問題回報 #62."""
    w = ' '.join(str(word or '').lower().split())
    if ' ' not in w and '-' not in w:
        return True
    if w not in _PHRASE_CACHE:
        known = s.execute(select(m.Lexeme.id).where(
            m.Lexeme.language == 'en', m.Lexeme.normalized == w,
            m.Lexeme.status == 'full').limit(1)).first() is not None
        if not known:
            from .adapters import ADAPTERS, Context
            try:
                entries = ADAPTERS['kaikki'].fetch(Context('en', 'zh-TW', w, w)) or []
                known = any(e.get('pos') != 'name' for e in entries)
            except Exception:  # noqa: BLE001 — can't tell: keep the label
                known = True
        _PHRASE_CACHE[w] = known
    return _PHRASE_CACHE[w]


def split_made_up(s, tags: list[dict], seen=()) -> tuple[list[dict], list[dict]]:
    """A made-up phrase (wooden surface, glass bowl) becomes its words at the
    same place, each to be scored on its own; the phrase is set aside (#62)."""
    from .adapters.local import cefr_list
    listed = cefr_list()
    have = {str(t.get('word', '')).strip().lower() for t in tags} | {w.lower() for w in seen}
    out, aside = [], []
    for t in tags:
        w = ' '.join(str(t.get('word') or '').lower().split())
        if dictionary_phrase(s, w):
            out.append(t)
            continue
        aside.append({**t, 'dropReason': '不是詞典片語（已拆成單字）'})
        for part in re.findall(r"[a-z]+(?:'[a-z]+)?", w):
            if part in PHRASE_STOPWORDS or part in have or len(part) < 2:
                continue
            have.add(part)
            pos = next(iter((listed.get(part) or (None, {}))[1]), None)
            pos = {'adj.': 'adjective', 'adv.': 'adverb'}.get(pos, pos) or t.get('pos')
            out.append(classify_tag_cefr(s, {'word': part, 'pos': pos, 'point': t.get('point'),
                                              'box': t.get('box'), 'splitFrom': w}))
    return out, aside


def _settle(s, asset, passed, dropped, model, done=True):
    """Passed labels (best first) on the picture, the others aside; a done
    picture then belongs to the words its labels name, and only those."""
    made_up = [t for t in passed if not dictionary_phrase(s, t.get('word'))]
    for tag in made_up:
        tag['dropReason'] = '不是詞典片語'
    passed = [t for t in passed if t not in made_up]
    dropped = [*dropped, *made_up]
    if any(tag_level(tag) for tag in passed):
        passed, overflow = _select_cefr_tags(passed, own_words(s, asset))
        for tag in overflow:
            tag.setdefault('dropReason', '該等級已滿 4 個')
        dropped = [*dropped, *overflow]
        asset.tags = sorted(passed, key=lambda tag: (
            CEFR_LEVELS.index(tag_level(tag)), -(tag.get('score') or 0)))
    else:
        asset.tags = sorted(passed, key=lambda t: -(t.get('score') or 0))[:TAGS_MAX]
    asset.dropped_tags = sorted(dropped, key=lambda t: -(t.get('score') or 0))
    asset.tag_model = (model or asset.tag_model or '')[:64]
    asset.tagged_at = datetime.now(timezone.utc)
    asset.tag_status = 'done' if done else 'pending'
    asset.safety_status = 'safe'
    for binding, lemma in s.execute(select(m.SenseImage, m.Lexeme.normalized).join(
            m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
            m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
            m.SenseImage.image_asset_id == asset.id)).all():
        judge(s, binding, asset, lemma)
    share(s, asset)
    auto_accept_asset(s, asset)


def rescore(s, asset) -> None:
    """A picture labelled before the 80% rule: score the labels it already
    has (one quick check, no new look) so every picture shows its scores at
    once. Eight passing is enough; with fewer it stays pending for the full
    re-labelling (more looks)."""
    # Levels from the CEFR list again (never a stored vision-model level).
    tags = [classify_tag_cefr(s, {k: t.get(k) for k in
                                  ('word', 'pos', 'point', 'box', 'score', 'scoreDeferred')})
            for t in asset.tags or [] if str(t.get('word', '')).strip()]
    for t in tags:  # a deferred 0.80 is a placeholder, not a measurement
        if t.pop('scoreDeferred', None):
            t['score'] = None
    PICTURE.set(asset.id)
    tags, aside = split_made_up(s, tags)  # wooden surface → wooden, surface (#62)
    # A missing local image is a picture failure, not a service outage.
    data = (config.MEDIA / asset.path).read_bytes()
    try:
        score_tags(data, tags, asset.mime, defer=False)
    except urllib.error.HTTPError as e:
        if e.code == 451:
            _block_unsafe(s, asset)
            raise ValueError('成人內容安全檢查未通過') from e
        raise _tag_http_failure(e) from e
    except (urllib.error.URLError, OSError) as e:
        raise TaggerUnavailable(f'標籤服務無法連線：{e}') from e
    passed = [t for t in tags if tag_level(t) and (t.get('score') or 0) >= TAG_PASS]
    dropped = [t for t in tags if not tag_level(t) or (t.get('score') or 0) < TAG_PASS]
    for tag in dropped:
        if not tag_level(tag):
            tag['dropReason'] = '缺少 CEFR 等級'
    dropped.extend(aside)
    # Measured and leveled from the list: settled; levels it can't fill are
    # gaps (owner decision A), not another full labelling.
    _settle(s, asset, passed, dropped, None, done=True)


TAG_POS = {'adjective': 'adj', 'adverb': 'adv'}

# Card #167. One binding policy for live tagging and the stored-tag backfill.
# Generic words are real dictionary entries, but they describe the photo
# instead of a thing a learner came to study (#199).
GENERIC_TAG_WORDS = frozenset({
    'surface', 'edge', 'handle', 'pattern', 'structure', 'vertical', 'center',
    'object', 'area', 'part', 'side', 'background', 'photograph', 'image',
    'portrait', 'depict', 'display', 'close-up', 'picture', 'scene', 'view',
    'item', 'thing', 'shape', 'texture', 'color', 'colour', 'foreground',
})
# When both words are on the same photo, the second one is the duplicate.
SYNONYM_PAIRS = (
    ('stone', 'rock'), ('bowl', 'container'), ('light', 'illuminated'),
    ('cup', 'mug'), ('road', 'street'), ('picture', 'image'), ('photo', 'photograph'),
)
# A subject box has to cover more of the frame than the tagger's point marker
# (those markers are about 0.04 by 0.04). visualConfidence is stored by the
# tagger; labels with no confidence cannot be the representative (#186).
REP_MIN_BOX_AREA = 0.02
REP_MIN_VISUAL_CONFIDENCE = 0.7
ADJECTIVE_IMAGE_MAX = 12
_DROPPED_KEEP_ASIDE = (
    '不是詞典片語', '高階替代詞', '泛用字', '近義重複', '形容詞張數已滿',
)


def tag_word(tag) -> str:
    return ' '.join(str((tag or {}).get('word') or '').strip().lower().split())


def tag_box_area(tag) -> float | None:
    """Fraction of the frame a label's box covers, or None when there is no box."""
    box = tag.get('box') if isinstance(tag, dict) else None
    if not isinstance(box, (list, tuple)) or len(box) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    except (TypeError, ValueError):
        return None
    area = abs(x2 - x1) * abs(y2 - y1)
    if area <= 0 or area > 1.5:
        return None
    return area


def representative_tag_ok(tag, lemma: str) -> bool:
    """The representative picture has to name the word, with a subject-sized
    box and a visual confidence at or above the tagger's stored scale."""
    lemma = (lemma or '').strip().lower()
    # The label text has to be the entry's own spelling. A longer phrase
    # ("coffee cup") does not make the picture that word's representative.
    if not lemma or tag_word(tag) != lemma:
        return False
    area = tag_box_area(tag)
    if area is None or area < REP_MIN_BOX_AREA:
        return False
    try:
        confidence = float(tag.get('visualConfidence'))
    except (TypeError, ValueError):
        return False
    return confidence >= REP_MIN_VISUAL_CONFIDENCE


def _resolve_cache(s) -> dict:
    return s.info.setdefault('bind_resolve', {})


def resolve_full_lexeme(s, word: str, pos: str | None = None):
    """The full entry a label should hang on: the word itself, or the full
    base of an inflection (holding → hold). Stubs are not entries (#197)."""
    word = ' '.join(str(word or '').strip().lower().split())
    if not word:
        return None
    wanted = TAG_POS.get(str(pos or '').strip().lower(), str(pos or '').strip().lower())
    key = ('lx', word, wanted)
    cache = _resolve_cache(s)
    if key in cache:
        found_id = cache[key]
        return s.get(m.Lexeme, found_id) if found_id else None
    exact = s.scalars(select(m.Lexeme).where(
        m.Lexeme.language == 'en', m.Lexeme.normalized == word,
        m.Lexeme.status == 'full').order_by(m.Lexeme.id)).all()
    found = list(exact)
    if not found:
        found.extend(s.scalars(select(m.Lexeme).join(
            m.Form, m.Form.lexeme_id == m.Lexeme.id).where(
            m.Lexeme.language == 'en', m.Lexeme.status == 'full',
            or_(func.lower(m.Form.form) == word,
                func.lower(m.Form.normalized) == word)).order_by(m.Lexeme.id)).all())
        bases = _morphology_lemmas(word)
        if bases:
            found.extend(s.scalars(select(m.Lexeme).where(
                m.Lexeme.language == 'en', m.Lexeme.status == 'full',
                m.Lexeme.normalized.in_(bases)).order_by(m.Lexeme.id)).all())
    same = [lx for lx in found if lx.pos == wanted] if wanted else []
    pool = same or found
    # The shortest full spelling is the base (hold, not holding).
    lexeme = sorted(pool, key=lambda lx: (len(lx.normalized), lx.id))[0] if pool else None
    cache[key] = lexeme.id if lexeme else 0
    return lexeme


def unbound_reason(s, word: str) -> str:
    """Why a label was not bound. Recorded on the tag; nothing is dropped quietly."""
    word = ' '.join(str(word or '').strip().lower().split())
    cache = _resolve_cache(s)
    key = ('why', word)
    if key in cache:
        return cache[key]
    statuses = {status for (status,) in s.execute(select(m.Lexeme.status).where(
        m.Lexeme.language == 'en', m.Lexeme.normalized == word)).all()}
    reason = '查無詞條'
    if 'stub' in statuses and 'full' not in statuses:
        reason = '只有 stub'
    elif statuses and 'full' not in statuses:
        reason = 'redirect 沒有完整詞條' if 'redirect' in statuses else '不是完整詞條'
    elif not statuses:
        for base in _morphology_lemmas(word):
            base_status = {status for (status,) in s.execute(select(m.Lexeme.status).where(
                m.Lexeme.language == 'en', m.Lexeme.normalized == base)).all()}
            if 'stub' in base_status and 'full' not in base_status:
                reason = '只有 stub'
                break
    cache[key] = reason
    return reason


def _remember_skips(asset, skips: dict[str, str], bound: set[str]) -> None:
    if not skips and not bound:
        return
    tags = []
    changed = False
    for item in asset.tags or []:
        item = dict(item)
        word = tag_word(item)
        if word in bound and item.pop('bindSkip', None) is not None:
            changed = True
        elif word in skips and item.get('bindSkip') != skips[word]:
            item['bindSkip'] = skips[word]
            changed = True
        tags.append(item)
    if changed:
        asset.tags = tags


def _binding_tags(asset):
    """Labels to consider: the kept ones, plus stored labels set aside only
    because the level was full or they had no recorded reason. Low-score and
    made-up labels stay aside. This uses the saved tagger output, not a new call."""
    seen = set()
    for tag in asset.tags or []:
        word = tag_word(tag)
        if word and word not in seen:
            seen.add(word)
            yield tag
    for tag in asset.dropped_tags or []:
        word = tag_word(tag)
        if not word or word in seen:
            continue
        if (tag.get('score') or 0) < TAG_PASS:
            continue
        reason = str(tag.get('dropReason') or '')
        if any(reason.startswith(prefix) for prefix in _DROPPED_KEEP_ASIDE):
            continue
        seen.add(word)
        yield tag


def _already_bound(s, asset_id: int, normalized: str) -> bool:
    return s.scalar(select(func.count()).select_from(m.SenseImage).join(
        m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
        m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
        m.SenseImage.image_asset_id == asset_id,
        m.SenseImage.review_status != 'rejected',
        m.Lexeme.normalized == normalized)) > 0


def _nongeneric_level_counts(s, asset_id: int) -> dict[str, int]:
    counts = {level: 0 for level in CEFR_LEVELS}
    rows = s.execute(select(m.Lexeme.normalized, m.Lexeme.cefr).join(
        m.Sense, m.Sense.lexeme_id == m.Lexeme.id).join(
        m.SenseImage, m.SenseImage.sense_id == m.Sense.id).where(
        m.SenseImage.image_asset_id == asset_id,
        m.SenseImage.review_status == 'approved')).all()
    seen = set()
    for normalized, cefr in rows:
        if normalized in GENERIC_TAG_WORDS or normalized in seen:
            continue
        seen.add(normalized)
        level = str(cefr or '').upper()
        if level in counts:
            counts[level] += 1
    return counts


def _synonym_loser(tags) -> set[str]:
    """The broader word of a known pair, when both labels are present."""
    words = {tag_word(tag) for tag in tags}
    return {right for left, right in SYNONYM_PAIRS if left in words and right in words}


def _tag_sense_rows(s, lexeme) -> list[dict]:
    """choose_sense candidates for a lexeme's senses, ``low`` decided by the
    same quality.rank_senses the pack uses (card #164: the earlier per-sense
    check ignored that an AI translation after a dictionary one is a
    sub-sense, so tags landed on senses the pack then had to replace)."""
    from app import quality as _q
    rows = []
    for se in s.scalars(select(m.Sense).where(m.Sense.lexeme_id == lexeme.id)
                        .order_by(m.Sense.ordinal)):
        tr = s.scalars(select(m.SenseTranslation).where(
            m.SenseTranslation.sense_id == se.id,
            m.SenseTranslation.native_language == "zh-TW")).first()
        df = s.scalars(select(m.Definition).where(m.Definition.sense_id == se.id)).first()
        rows.append({"id": se.id, "lexeme_pos": lexeme.pos, "ordinal": se.ordinal,
                     "definition": df.text if df else "", "native": tr.text if tr else None,
                     "native_ai": bool(tr and tr.is_ai), "labels": list(se.labels or [])})
    ranked = _q.rank_senses([{"id": r["id"], "native": r["native"], "native_ai": r["native_ai"],
                              "labels": list(r["labels"])} for r in rows])
    priority = {r["id"]: r["priority"] for r in ranked}
    for r in rows:
        r["low"] = priority.get(r["id"]) == "low"
    return rows


def share(s, asset, only_lemma=None, require_publishable: bool = False) -> int:
    """Put a picture under every word its AI labels name (a bench picture
    labelled gravel also shows gravel). A picture a reviewer already approved
    for another word is approved here too; otherwise it waits for review.

    Labels that cannot be bound record why (no entry, stub, generic, synonym,
    adjective cap). An inflection is bound to its full base form (#197)."""
    if not labelled(asset) or asset.status != 'ready' or asset.safety_status != 'safe':
        return 0
    reviewed = s.scalar(select(func.count()).select_from(m.SenseImage).where(
        m.SenseImage.image_asset_id == asset.id, m.SenseImage.review_status == 'approved')) > 0
    candidates = list(_binding_tags(asset))
    losers = _synonym_loser(candidates)
    levels = _nongeneric_level_counts(s, asset.id)
    skips: dict[str, str] = {}
    bound: set[str] = set()
    added = 0
    for tag in candidates:
        word = tag_word(tag)
        if not word:
            continue
        if word in GENERIC_TAG_WORDS:
            if not _already_bound(s, asset.id, word):
                skips[word] = '泛用字'
            continue
        if word in losers:
            skips[word] = '近義重複'
            continue
        pos = TAG_POS.get(str(tag.get('pos', '')), str(tag.get('pos', '')))
        lexeme = resolve_full_lexeme(s, word, pos)
        if lexeme is None:
            if not only_lemma or word == only_lemma:
                skips[word] = unbound_reason(s, word)
            continue
        if only_lemma and only_lemma not in {word, lexeme.normalized}:
            continue
        if _already_bound(s, asset.id, lexeme.normalized):
            bound.add(word)
            continue
        if lexeme.pos in ('adj', 'adjective'):
            have = s.scalar(select(func.count(func.distinct(m.SenseImage.image_asset_id))).select_from(
                m.SenseImage).join(m.Sense, m.Sense.id == m.SenseImage.sense_id).where(
                m.Sense.lexeme_id == lexeme.id, m.SenseImage.review_status != 'rejected'))
            if (have or 0) >= ADJECTIVE_IMAGE_MAX:
                skips[word] = '形容詞張數已滿'
                continue
        level = tag_level(tag) or str(lexeme.cefr or '').upper()
        if level in levels and levels[level] >= CEFR_LEVEL_MAX:
            skips[word] = '該等級已滿 4 個'
            continue
        from app import quality as _q
        # Context = the other AI labels on this photo (#195 / P2).
        context = _q.tokens(" ".join(
            str(t.get("word", "")) for t in (asset.tags or []) if tag_word(t) != word))
        sense_rows = _tag_sense_rows(s, lexeme)
        if not sense_rows:
            skips[word] = '詞條沒有義項'
            continue
        publishable = [row for row in sense_rows
                       if (row.get('native') or '').strip() and not row.get('low')]
        if require_publishable and not publishable:
            # Card #164: the resolved part of speech may be a rare usage
            # whose only senses are colloquial (brick the adjective 極冷):
            # a sister entry of the same spelling with a publishable sense
            # takes the label instead (the album checks by spelling).
            for sister in s.scalars(select(m.Lexeme).where(
                    m.Lexeme.language == 'en', m.Lexeme.normalized == lexeme.normalized,
                    m.Lexeme.status == 'full', m.Lexeme.id != lexeme.id).order_by(m.Lexeme.id)):
                rows = _tag_sense_rows(s, sister)
                pub = [row for row in rows if (row.get('native') or '').strip() and not row.get('low')]
                if pub:
                    lexeme, sense_rows, publishable = sister, rows, pub
                    break
        if require_publishable and not publishable:
            # A low-priority or Chinese-less sense must not become a learner
            # label (#195). Leave the word unbound and say why.
            skips[word] = '沒有可顯示的義項'
            continue
        best, top, second = _q.choose_sense(
            publishable if require_publishable else sense_rows, context, None, pos or None)
        if best is None:
            if require_publishable:
                skips[word] = '沒有可顯示的義項'
                continue
            # No sense has Chinese yet: bind the dictionary's first sense at a
            # low confidence; the pack guard and review handle it later.
            best, score = sense_rows[0], 0.3
        else:
            # Confidence from how clearly the photo context prefers this sense.
            score = 0.5 if second == float("-inf") else max(0.35, min(0.99, 0.55 + (top - second) * 0.08))
        occupied = s.scalar(select(func.count()).select_from(m.SenseImage).where(
            m.SenseImage.sense_id == best["id"], m.SenseImage.review_status != "rejected")) or 0
        has_rep = s.scalar(select(func.count()).select_from(m.SenseImage).where(
            m.SenseImage.sense_id == best["id"], m.SenseImage.role == "representative",
            m.SenseImage.review_status != "rejected")) or 0
        role = "representative" if has_rep == 0 and representative_tag_ok(tag, lexeme.normalized) else "context"
        binding = m.SenseImage(sense_id=best["id"], image_asset_id=asset.id,
                               role=role, ordinal=occupied,
                               semantic_score=score, alt_native={},
                               review_status="approved" if reviewed else "pending")
        s.add(binding)
        s.flush()
        note = f'共用圖片：AI 標籤認出「{lexeme.normalized}」'
        if word != lexeme.normalized:
            note += f'（由「{word}」導向本形）'
        if reviewed:
            note += '（原圖已由管理者核准）'
        s.add(m.ImageReview(sense_image_id=binding.id, decision=binding.review_status, note=note))
        if level in levels:
            levels[level] += 1
        bound.add(word)
        added += 1
    _remember_skips(asset, skips, bound)
    return added


def _approved_words(s, asset_id: int) -> list[tuple]:
    return s.execute(select(
        m.SenseImage, m.Lexeme.normalized, m.Lexeme.pos, m.Lexeme.id).join(
        m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
        m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
        m.SenseImage.image_asset_id == asset_id,
        m.SenseImage.review_status == 'approved')).all()


def _reject_binding(s, binding, note: str) -> None:
    binding.review_status = 'rejected'
    s.add(m.ImageReview(sense_image_id=binding.id, decision='rejected', note=note))


def rebind_asset(s, asset) -> dict:
    """Bind from the tags already stored on this picture, then drop generic
    and synonym labels when the picture still has three other words."""
    added = share(s, asset, require_publishable=True) if labelled(asset) else 0
    rows = _approved_words(s, asset.id)
    distinct = {lexeme_id for _, _, _, lexeme_id in rows}
    generic_rows = [row for row in rows if row[1] in GENERIC_TAG_WORDS]
    kept = len(distinct - {row[3] for row in generic_rows})
    generic = 0
    if kept >= 3:
        for binding, _word, _pos, _lexeme_id in generic_rows:
            _reject_binding(s, binding, '泛用字，不佔學習標籤（#199）')
            generic += 1
        rows = [row for row in rows if row[1] not in GENERIC_TAG_WORDS]
    names = {word for _binding, word, _pos, _lexeme_id in rows}
    synonym = 0
    for left, right in SYNONYM_PAIRS:
        if left not in names or right not in names:
            continue
        loser = right
        loser_rows = [row for row in rows if row[1] == loser]
        if len(names) - 1 < 3:
            continue
        for binding, _word, _pos, _lexeme_id in loser_rows:
            _reject_binding(s, binding, '近義重複，保留另一個（#199）')
            synonym += 1
        names.discard(loser)
    skips = {}
    for tag in asset.tags or []:
        if tag.get('bindSkip'):
            skips[tag['bindSkip']] = skips.get(tag['bindSkip'], 0) + 1
    return {'added': added, 'generic': generic, 'synonym': synonym, 'skips': skips}


def cap_adjective_images(s, protect: set[int] | None = None) -> int:
    """Keep at most ADJECTIVE_IMAGE_MAX pictures on an adjective, rejecting
    the weakest first. Never take a picture below three approved words."""
    rows = s.execute(select(
        m.SenseImage, m.Lexeme.id, m.SenseImage.image_asset_id).join(
        m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
        m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
        m.Lexeme.pos.in_(('adj', 'adjective')),
        m.SenseImage.review_status == 'approved').order_by(
        m.SenseImage.semantic_score.asc().nullsfirst(), m.SenseImage.id)).all()
    by_lexeme: dict[int, list] = {}
    for binding, lexeme_id, asset_id in rows:
        by_lexeme.setdefault(lexeme_id, []).append((binding, asset_id))
    photo_words: dict[int, set[int]] = {}
    for asset_id, lexeme_id in s.execute(select(
            m.SenseImage.image_asset_id, m.Lexeme.id).join(
            m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
            m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
            m.SenseImage.review_status == 'approved')).all():
        photo_words.setdefault(asset_id, set()).add(lexeme_id)
    rejected = 0
    for lexeme_id, bindings in by_lexeme.items():
        if len(bindings) <= ADJECTIVE_IMAGE_MAX:
            continue
        # Weakest first: reject from the front, keep the strongest tail.
        protect = protect or set()
        for binding, asset_id in bindings[:-ADJECTIVE_IMAGE_MAX]:
            if asset_id in protect:
                continue
            words = photo_words.get(asset_id, set())
            if len(words) - (1 if lexeme_id in words else 0) < 3:
                continue
            _reject_binding(s, binding, '形容詞圖片超過上限（#186）')
            words.discard(lexeme_id)
            rejected += 1
    return rejected


def demote_unmentioned_representatives(s, protect: set[int] | None = None) -> int:
    """A representative picture whose stored labels do not contain the word
    stops being the representative (#146). Promote another approved picture
    of that sense when its label is the word and clears the box gates."""
    rows = s.execute(select(m.SenseImage, m.Lexeme.normalized, m.Lexeme.lemma, m.ImageAsset.tags).join(
        m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
        m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).join(
        m.ImageAsset, m.ImageAsset.id == m.SenseImage.image_asset_id).where(
        m.SenseImage.role == 'representative',
        m.SenseImage.review_status == 'approved')).all()
    protect = protect or set()
    changed = 0
    for binding, normalized, lemma, tags in rows:
        if binding.image_asset_id in protect:
            continue
        names = {tag_word(tag) for tag in tags or []}
        if normalized in names or (lemma or '').lower() in names:
            continue
        binding.role = 'context'
        changed += 1
        others = s.execute(select(m.SenseImage, m.ImageAsset.tags).join(
            m.ImageAsset, m.ImageAsset.id == m.SenseImage.image_asset_id).where(
            m.SenseImage.sense_id == binding.sense_id,
            m.SenseImage.id != binding.id,
            m.SenseImage.review_status == 'approved')).all()
        promoted = None
        for other, other_tags in others:
            match = next((tag for tag in other_tags or [] if tag_word(tag) == normalized), None)
            if match and representative_tag_ok(match, normalized):
                promoted = other
                break
        if promoted is not None:
            promoted.role = 'representative'
            s.add(m.ImageReview(sense_image_id=promoted.id, decision='approved',
                                note='改為代表圖：標籤含該字且主體框達門檻（#186）'))
        s.add(m.ImageReview(sense_image_id=binding.id, decision='approved',
                            note='取消代表圖：標籤沒有這個字（#146）'))
    return changed


def share_existing(s, target, lemma) -> int:
    """A word imported after pictures were labelled gets those that name it."""
    added = 0
    for asset in s.scalars(select(m.ImageAsset).where(
            m.ImageAsset.tag_status == 'done',
            text("EXISTS (SELECT 1 FROM jsonb_array_elements(image_assets.tags::jsonb) t"
                 " WHERE lower(t->>'word') = :w)").bindparams(w=lemma))).all():
        added += share(s, asset, only_lemma=lemma)
    return added


def lemma_forms(s, lemma: str) -> set[str]:
    """A word's spellings a label may use: the dictionary's stored forms
    (children for child) and, for a plural headword, its singular
    (coffee bean for coffee beans)."""
    lemma = lemma.lower()
    found = {f.lower() for (f,) in s.execute(select(m.Form.form).join(
        m.Lexeme, m.Lexeme.id == m.Form.lexeme_id).where(
        m.Lexeme.language == 'en', m.Lexeme.normalized == lemma,
        m.Form.field.in_(('noun_plural', 'verb_third_person', 'verb_past',
                          'verb_past_participle', 'verb_present_participle')))).all()}
    return found | set(_morphology_lemmas(lemma))


AUTO_ACCEPT_MIN = 0.35  # #34: below this only the no-Chinese fallback binding (0.3)


def auto_accept_ok(asset, tags_lemma, score) -> bool:
    """#34 (owner): a picture the vision model labelled with the word is
    accepted automatically, no manual review, when the same guards the old
    review-batch used still hold (ready, allowed licence, safe, file on disk,
    labelling done, labels name the word)."""
    return bool(tags_lemma and (score or 0) >= AUTO_ACCEPT_MIN
                and asset.status == 'ready' and allowed_license(asset.license_code)
                and asset.safety_status == 'safe' and asset.tag_status == 'done'
                and asset.path and (config.MEDIA / asset.path).is_file()
                and len(asset.tags or []) >= 3)


AUTO_ACCEPT_MIN_TAGS = 3  # same floor as the pack metric photo.fewer_than_3_tags


def auto_accept_asset(s, asset, note='自動採用（#34）') -> int:
    """#34 (owner: 標完不用再審): once labelling is done, the picture's pending
    word bindings are approved without manual review when every guard holds
    (auto_accept_ok + auto_accept_sense_ok) and the picture then shows at
    least 3 approved words; otherwise they stay pending for the QC/review."""
    if not labelled(asset):
        return 0
    rows = s.execute(select(m.SenseImage, m.Lexeme.normalized).join(
        m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
        m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
        m.SenseImage.image_asset_id == asset.id)).all()
    approved = sum(1 for b, _ in rows if b.review_status == 'approved')
    ok = [(b, w) for b, w in rows if b.review_status == 'pending'
          and auto_accept_ok(asset, shows_word(asset.tags, w, lemma_forms(s, w)), b.semantic_score)
          and auto_accept_sense_ok(s, b.sense_id)]
    if not ok or approved + len(ok) < AUTO_ACCEPT_MIN_TAGS:
        return 0
    for b, w in ok:
        b.review_status = 'approved'
        s.add(m.ImageReview(sense_image_id=b.id, decision='approved',
                            note=f'AI 標籤認出「{w}」，{note}'))
    return len(ok)


def auto_accept_sense_ok(s, sense_id) -> bool:
    """#34 quality guard: auto-accept only onto a sense that has Chinese and
    is not low-priority (same rules as the pack metrics); else it waits."""
    from app import quality as _q
    se = s.get(m.Sense, sense_id)
    if se is None:
        return False
    tr = s.scalars(select(m.SenseTranslation).where(
        m.SenseTranslation.sense_id == sense_id,
        m.SenseTranslation.native_language == 'zh-TW')).first()
    if not (tr and (tr.text or '').strip()):
        return False
    return not _q.sense_is_low({'labels': se.labels or [], 'native': tr.text,
                                'native_ai': bool(tr.is_ai)}, False)


def shows_word(tags, lemma, forms=()) -> bool:
    """The AI labels name the word (or its plural, or a phrase with it);
    ``forms``: more spellings from the dictionary (lemma_forms)."""
    from .adapters.local import regular_plural
    forms = {lemma.lower(), regular_plural(lemma.lower()), *forms}
    words = {str(t.get('word', '')).lower() for t in tags or []}
    return bool(forms & words) or any(f in w.split() for w in words for f in forms)


def judge(s, binding, asset, lemma) -> None:
    """A picture belongs to a word only when the vision model sees the word
    in it: confirmed pictures score 0.95; the others are taken off the word
    (the user: 沒有該單字的圖片不要放在該單字內)."""
    if not labelled(asset):
        return
    if shows_word(asset.tags, lemma, lemma_forms(s, lemma)):
        binding.semantic_score = max(binding.semantic_score or 0, 0.95)
    elif binding.review_status != 'rejected':
        binding.review_status = 'rejected'
        s.add(m.ImageReview(sense_image_id=binding.id, decision='rejected',
                            note=f'AI 標籤沒有認出「{lemma}」（自動）'))


def score_tags(data: bytes, tags: list[dict], mime: str | None = None,
               defer: bool | None = None) -> None:
    """Each label's own recognition score (0–1): the vision model checks the
    picture again and answers yes/no per label; the yes-token probability
    becomes the label's score (tag['score']).

    Safe skips:
    - tags that already have a numeric score are left untouched (cache-/resume-friendly)
    - when defer=True (or LEXICON_DEFER_TAG_SCORE), grounded labels (point/box or CEFR
      band) get a provisional TAG_PASS without a second vision call; others stay None
      so they do not pass. tag_pending/rescore can refine later.
    """
    if not tags:
        return
    if defer is None:
        defer = DEFER_TAG_SCORE
    pending = [t for t in tags if t.get('score') is None or t.get('scoreDeferred')]
    if not pending:
        return  # already scored (resume / cache path)
    if defer:
        for t in pending:
            grounded = bool(t.get('point') or t.get('box') or t.get('cefr') or t.get('modelLevel'))
            if grounded:
                t['score'] = float(TAG_PASS)
                t['scoreDeferred'] = True
            # else leave None → fails TAG_PASS
        return
    labels = json.dumps([{'word': t['word'], 'pos': t.get('pos')} for t in pending])
    request = urllib.request.Request(
        config.AI_URL.rstrip('/') + '/score?lang=en&labels=' + urllib.parse.quote(labels),
        data=data, method='POST',
        headers={'X-API-Key': config.AI_KEY, 'Content-Type': mime or 'image/jpeg',
                 'X-Inference-Priority': 'background',
                 **({'X-Activity-Ref': f'image:{PICTURE.get()}'} if PICTURE.get() else {}),
                 'X-Activity': urllib.parse.quote(
                     f"評分 {len(pending)} 個標籤：{'、'.join(t['word'] for t in pending[:4])}"
                     + ('…' if len(pending) > 4 else ''))})
    with urllib.request.urlopen(request, timeout=300) as response:
        out = json.loads(response.read())
    note_tagger_stages(out)
    scores = {str(x.get('word', '')).lower(): x.get('score') for x in out.get('scores', [])}
    for t in pending:
        t['score'] = scores.get(str(t['word']).strip().lower())
        t.pop('scoreDeferred', None)


# Several labelling workers run at once (the model server has several slots):
# each takes a picture only while it holds that picture's lock, which lasts
# until its transaction ends, so two workers never label the same picture.
TAG_LOCK = 770002


def _claim_pictures(s, assets, limit):
    if s.get_bind().dialect.name != 'postgresql':
        return assets[:limit]
    taken = []
    for asset in assets:
        if s.scalar(text('SELECT pg_try_advisory_xact_lock(:k, :id)'),
                    {'k': TAG_LOCK, 'id': asset.id}):
            taken.append(asset)
            if len(taken) >= limit:
                break
    return taken


def _tag_eligible():
    return (
        m.ImageAsset.safety_status != 'blocked',
        m.ImageAsset.tag_attempts < TAG_MAX_ATTEMPTS,
        or_(m.ImageAsset.tag_retry_at.is_(None),
            m.ImageAsset.tag_retry_at <= datetime.now(timezone.utc)),
        or_(m.ImageAsset.tag_status.in_(['pending', 'failed']),
            m.ImageAsset.safety_status == 'unchecked'),
    )


_failed_retry_tick = 0


def _failed_retry_turn():
    """Reserve one in ten full-worker polls for eligible failures (#212)."""
    global _failed_retry_tick
    turn = _failed_retry_tick % 10 == 0
    _failed_retry_tick += 1
    return turn


def tag_pending(s, limit=1, quick_only=False):
    """Label (and score) the next downloaded pictures still without AI labels,
    pictures waiting for review first: the reviewer reads their labels."""
    # Owner paused Qwen on the board: back off without claiming or failing pictures.
    if agent_pause.is_paused("Qwen"):
        return 0
    done = 0
    # Apply the same gate to BOTH queues: unchecked must not bypass backoff
    # or the terminal failure budget. Legacy failures (attempts=0) get a retry.
    eligible = _tag_eligible()
    # New unlabelled images must not starve legacy failures indefinitely.
    # Keep quick-only callers quick, share the existing retry budget/backoff,
    # and claim at most one picture with the normal cross-process lock.
    if not quick_only and _failed_retry_turn():
        retries = s.scalars(select(m.ImageAsset).where(
            m.ImageAsset.status == 'ready', *eligible,
            m.ImageAsset.tag_status == 'failed'
        ).order_by(m.ImageAsset.id).limit(21)).all()
        for asset in _claim_pictures(s, list(retries), min(limit, 1)):
            try:
                tag_asset(s, asset.id)
            except TaggerUnavailable:
                return 0
            except (ValueError, OSError):
                pass
            return 1
    # First every picture still carrying unscored (or failing) labels gets
    # its scores and the 80% rule (quick), then the full re-labelling of
    # those still short of 8.
    waiting = s.scalars(select(m.ImageAsset).where(
            m.ImageAsset.status == 'ready', *eligible,
            m.ImageAsset.safety_status == 'safe',
            text("EXISTS (SELECT 1 FROM json_array_elements(image_assets.tags::json) t"
                 " WHERE t->'score' IS NULL OR (t->>'score')::float < :pass)")
            .bindparams(**{'pass': TAG_PASS}))
            .order_by(m.ImageAsset.id).limit(limit + 20)).all()
    for asset in _claim_pictures(s, list(waiting), limit):
        try:
            _tag_attempt(asset, lambda: rescore(s, asset))
        except TaggerUnavailable:
            return 0
        except (ValueError, OSError):
            pass  # _tag_attempt persisted diagnostics and the retry deadline
        done += 1
    if done:
        return done
    # Then the full labelling: pictures with no labels at all first (always,
    # every picture needs scored labels), the rest only when not quick_only.
    unlabelled = text("(image_assets.tags IS NULL OR image_assets.tags::text = '[]')")
    waiting = s.scalars(select(m.ImageAsset).where(
            m.ImageAsset.status == 'ready',
            *eligible,
            *([unlabelled] if quick_only else []))
            .order_by(text("(image_assets.tags IS NULL OR image_assets.tags::text = '[]') DESC"),
                      text("EXISTS (SELECT 1 FROM sense_images b WHERE b.image_asset_id ="
                           " image_assets.id AND b.review_status = 'pending') DESC"),
                      m.ImageAsset.id).limit(limit + 20)).all()
    for asset in _claim_pictures(s, list(waiting), limit):
        try:
            tag_asset(s, asset.id)
        except TaggerUnavailable:
            return 0  # the worker waits and tries again
        except (ValueError, OSError):
            pass
        done += 1
    return done


class SearchBody(BaseModel):
    sense_id: int
    qid: str


class ReviewBody(BaseModel):
    decision: str
    note: str = Field(min_length=1, max_length=2000)


class NoteBody(BaseModel):
    note: str = Field(default='', max_length=2000)


class RebindBody(BaseModel):
    sense_id: int


class RefetchBody(BaseModel):
    target_language: str = 'en'
    native_language: str = 'zh-TW'
    lemma: str = Field(min_length=1, max_length=128)


class BatchReviewBody(BaseModel):
    min_score: float = Field(ge=0.5, le=1.0)
    note: str = Field(min_length=1, max_length=2000)


def register(app, auth):
    @app.get('/images/fetch-audit', dependencies=[auth])
    def fetch_audit(s=Depends(db.get_session)):
        from .image_fetch_audit import snapshot
        return snapshot(s)

    @app.get('/images/senses', dependencies=[auth])
    def senses(target: str = 'en', native: str = 'zh-TW', s=Depends(db.get_session)):
        return [dict(r) for r in s.execute(text('''SELECT s.id,l.lemma,l.pos,t.text AS translation
            FROM senses s JOIN lexemes l ON l.id=s.lexeme_id
            LEFT JOIN sense_translations t ON t.sense_id=s.id AND t.native_language=:native
            WHERE l.language=:target AND l.status='full' ORDER BY l.lemma,s.ordinal LIMIT 2000'''), {'target': target, 'native': native}).mappings()]

    def decide(image_id, decision, note, s):
        binding = s.get(m.SenseImage, image_id)
        if not binding:
            raise HTTPException(404, '找不到圖片')
        asset = s.get(m.ImageAsset, binding.image_asset_id)
        if decision == 'approved' and (asset.status != 'ready' or not allowed_license(asset.license_code)
                                       or asset.safety_status != 'safe'
                                       or not (config.MEDIA / asset.path).is_file()):
            raise HTTPException(400, '檔案或授權尚未就緒')
        if decision == 'approved':
            lemma = s.execute(select(m.Lexeme.normalized).join(
                m.Sense, m.Sense.lexeme_id == m.Lexeme.id).where(m.Sense.id == binding.sense_id)).scalar()
            if not labelled(asset):
                raise HTTPException(400, '圖片還在等 AI 標籤，標完才能核准')
            if not shows_word(asset.tags, lemma):
                raise HTTPException(400, f'AI 標籤沒有認出「{lemma}」，這張圖不能放在這個字')
        binding.review_status = decision
        if decision == 'approved':
            asset.safety_status = 'safe'
        s.add(m.ImageReview(sense_image_id=binding.id, decision=decision, note=note))
        return {'id': binding.id, 'status': binding.review_status}

    @app.post('/images/{image_id}/approve', dependencies=[auth])
    def approve(image_id: int, body: NoteBody, s=Depends(db.get_session)):
        return decide(image_id, 'approved', body.note or '管理者確認詞義相符與內容適用', s)

    @app.post('/images/{image_id}/reject', dependencies=[auth])
    def reject(image_id: int, body: NoteBody, s=Depends(db.get_session)):
        return decide(image_id, 'rejected', body.note or '管理者拒絕此詞義圖片', s)

    @app.post('/images/{image_id}/rebind', dependencies=[auth])
    def rebind(image_id: int, body: RebindBody, s=Depends(db.get_session)):
        """Move a picture to another sense of the same word; it is reviewed again there."""
        binding = s.get(m.SenseImage, image_id)
        target = s.get(m.Sense, body.sense_id)
        if not binding or not target:
            raise HTTPException(404, '找不到圖片或詞義')
        old = s.get(m.Sense, binding.sense_id)
        a, b = s.get(m.Lexeme, old.lexeme_id), s.get(m.Lexeme, target.lexeme_id)
        if a.normalized != b.normalized or a.language != b.language:
            raise HTTPException(400, '只能改綁到同一個單字的其他詞義')
        if s.scalars(select(m.SenseImage).where(m.SenseImage.sense_id == target.id,
                                                m.SenseImage.image_asset_id == binding.image_asset_id)).first():
            raise HTTPException(400, '這張圖已綁在該詞義')
        binding.sense_id, binding.review_status, binding.role = target.id, 'pending', 'context'
        s.add(m.ImageReview(sense_image_id=binding.id, decision='rebind',
                            note=f'改綁到詞義 #{target.id}'))
        return {'id': binding.id, 'sense_id': target.id, 'status': 'pending'}

    @app.post('/images/{image_id}/representative', dependencies=[auth])
    def representative(image_id: int, s=Depends(db.get_session)):
        """The sense's representative picture; its other pictures become context."""
        binding = s.get(m.SenseImage, image_id)
        if not binding:
            raise HTTPException(404, '找不到圖片')
        for other in s.scalars(select(m.SenseImage).where(m.SenseImage.sense_id == binding.sense_id)):
            other.role = 'representative' if other.id == binding.id else 'context'
            other.ordinal = 0 if other.id == binding.id else max(other.ordinal, 1)
        return {'id': binding.id, 'role': 'representative'}

    @app.post('/images/refetch', dependencies=[auth])
    def refetch(body: RefetchBody, s=Depends(db.get_session)):
        """Search a word's pictures again: the pictures still waiting are
        dropped and the next candidates downloaded."""
        dropped = s.execute(text('''DELETE FROM sense_images si USING senses sn, lexemes l
            WHERE sn.id = si.sense_id AND l.id = sn.lexeme_id AND l.language = :t
              AND l.normalized = :w AND si.review_status = 'pending' '''),
            {'t': body.target_language, 'w': body.lemma.lower()}).rowcount
        got = auto_fetch(s, body.target_language, body.native_language, body.lemma.lower())
        return {'dropped': dropped, **got}

    @app.post('/images/review-batch', dependencies=[auth])
    def review_batch(body: BatchReviewBody, s=Depends(db.get_session)):
        """The reviewer approves at once every pending picture the vision
        model confirmed (its AI labels name the word)."""
        approved = 0
        for binding, lemma in s.execute(select(m.SenseImage, m.Lexeme.normalized).join(
                m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
                m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
                m.SenseImage.review_status == 'pending',
                m.SenseImage.semantic_score >= body.min_score)).all():
            asset = s.get(m.ImageAsset, binding.image_asset_id)
            if asset.status != 'ready' or not allowed_license(asset.license_code) \
                    or asset.safety_status != 'safe' \
                    or not (config.MEDIA / asset.path).is_file() \
                    or asset.tag_status != 'done' or not shows_word(asset.tags, lemma):
                continue
            binding.review_status = 'approved'
            asset.safety_status = 'safe'
            s.add(m.ImageReview(sense_image_id=binding.id, decision='approved', note=body.note))
            approved += 1
        return {'approved': approved}

    @app.get('/images', dependencies=[auth])
    def library(limit: int | None = Query(default=None, ge=1, le=500),
                offset: int = Query(default=0, ge=0),
                review_status: Literal['pending', 'approved', 'rejected'] | None = None,
                tag_status: Literal['pending', 'done', 'failed'] | None = None,
                s=Depends(db.get_session)):
        # By word and sense; "shared" counts the other senses using the same file.
        # Keep the existing list response and unbounded default for old callers.
        filters, params = ["a.safety_status = 'safe'"], {'offset': offset}
        if review_status is not None:
            filters.append('si.review_status = :review_status')
            params['review_status'] = review_status
        if tag_status is not None:
            filters.append('a.tag_status = :tag_status')
            params['tag_status'] = tag_status
        where = (' WHERE ' + ' AND '.join(filters)) if filters else ''
        page = ' LIMIT :limit' if limit is not None else ''
        if limit is not None:
            params['limit'] = limit
        return [dict(r) for r in s.execute(text('''SELECT si.id,si.sense_id,si.review_status,si.semantic_score,si.role,
            sn.ordinal,l.lemma,l.normalized,l.pos,l.language,d.text AS gloss,t.text AS native,
            a.id AS asset_id,a.author,a.license_code,a.page_url,a.size_bytes,a.width,a.height,a.status,
            a.tag_status,a.tag_attempts,a.tag_error,a.tag_retry_at,
            coalesce(jsonb_array_length(a.tags::jsonb),0) AS tag_count,
            coalesce((SELECT jsonb_agg(jsonb_build_object('word',x->>'word','pos',x->>'pos',
                'score',x->'score','cefr',x->>'cefr','cefrSource',x->>'cefrSource',
                'cefrLemma',x->>'cefrLemma','cefrCoreWord',x->>'cefrCoreWord'))
                FROM jsonb_array_elements(a.tags::jsonb) x),'[]'::jsonb) AS tags,
            coalesce((SELECT jsonb_agg(jsonb_build_object('word',x->>'word','pos',x->>'pos',
                'score',x->'score','cefr',x->>'cefr','cefrSource',x->>'cefrSource',
                'cefrLemma',x->>'cefrLemma','cefrCoreWord',x->>'cefrCoreWord',
                'dropReason',x->>'dropReason'))
                FROM jsonb_array_elements(a.dropped_tags::jsonb) x),
                '[]'::jsonb) AS dropped_tags,
            (SELECT count(*) FROM sense_images o WHERE o.image_asset_id=a.id)-1 AS shared
            FROM sense_images si JOIN image_assets a ON a.id=si.image_asset_id
            JOIN senses sn ON sn.id=si.sense_id JOIN lexemes l ON l.id=sn.lexeme_id
            LEFT JOIN definitions d ON d.sense_id=sn.id AND d.language=l.language
            LEFT JOIN sense_translations t ON t.sense_id=sn.id AND t.native_language='zh-TW'
            ''' + where + '''
            ORDER BY l.normalized,l.id,sn.ordinal,si.review_status,si.id'''
            + page + ' OFFSET :offset'), params).mappings()]

    @app.post('/images/search', dependencies=[auth])
    def search_endpoint(body: SearchBody, s=Depends(db.get_session)):
        try:
            return search(s, body.sense_id, body.qid)
        except (ValueError, KeyError, OSError) as e:
            raise HTTPException(400, str(e))

    @app.post('/images/candidates/{candidate_id}/import', dependencies=[auth])
    def import_endpoint(candidate_id: int, s=Depends(db.get_session)):
        c = s.get(m.ImageCandidate, candidate_id)
        ingest_fn = IMAGE_SOURCES.get(c.source, (None, None))[1] if c else None
        if ingest_fn is None:
            raise HTTPException(404 if not c else 400,
                                '找不到圖片候選' if not c else f'{c.source} 不支援匯入')
        try:
            return ingest_fn(s, candidate_id)
        except (ValueError, KeyError, OSError) as e:
            raise HTTPException(400, str(e))

    @app.post('/images/{image_id}/review', dependencies=[auth])
    def review(image_id: int, body: ReviewBody, s=Depends(db.get_session)):
        binding = s.get(m.SenseImage, image_id)
        if not binding or body.decision not in ('approved', 'rejected'):
            raise HTTPException(400, '圖片或審核結果無效')
        asset = s.get(m.ImageAsset, binding.image_asset_id)
        if body.decision == 'approved' and (asset.status != 'ready' or not allowed_license(asset.license_code) or not (config.MEDIA / asset.path).is_file()):
            raise HTTPException(400, '檔案或授權尚未就緒')
        if body.decision == 'approved' and asset.safety_status != 'safe':
            raise HTTPException(400, '圖片尚未通過成人內容安全檢查')
        binding.review_status = body.decision
        if body.decision == 'approved':
            asset.safety_status = 'safe'
        s.add(m.ImageReview(sense_image_id=binding.id, decision=body.decision, note=body.note))
        return {'id': binding.id, 'status': binding.review_status}

    @app.post('/images/{asset_id}/tag', dependencies=[auth])
    def tag_endpoint(asset_id: int, s=Depends(db.get_session)):
        try:
            return {'tags': tag_asset(s, asset_id)}
        except (ValueError, OSError) as e:
            s.commit()  # preserve failure diagnostics before the HTTP error rolls back
            raise HTTPException(400, str(e))

    @app.get('/images/{asset_id}/file')
    def image_file(asset_id: int, s=Depends(db.get_session)):
        asset = s.get(m.ImageAsset, asset_id)
        if not asset or asset.status != 'ready' or asset.safety_status != 'safe' or not asset.path:
            raise HTTPException(404, '找不到圖片')
        path = (config.MEDIA / asset.path).resolve()
        if not path.is_relative_to(config.MEDIA.resolve()) or not path.is_file():
            raise HTTPException(404, '找不到圖片檔案')
        return FileResponse(path, media_type=asset.mime)
