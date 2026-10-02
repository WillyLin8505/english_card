"""Sense-bound Commons image acquisition and review. No automatic approval."""
import hashlib
import html
import io
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image
from sqlalchemy import func, select, text

from . import config, db, models as m

HOSTS = {'www.wikidata.org', 'commons.wikimedia.org', 'upload.wikimedia.org', 'thumb.wikimedia.org'}
MAX_BYTES = 15 * 1024 * 1024


def allowed_license(value):
    value = (value or '').upper().strip()
    return value in ('CC0', 'CC0 1.0', 'PUBLIC DOMAIN') or bool(re.fullmatch(r'CC BY(?: [1-4]\.0)?', value))


def check_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('只接受 Wikidata／Wikimedia 官方 HTTPS 網址')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_last_request = [0.0]
_throttle = threading.Lock()
MIN_INTERVAL = 1.0  # Wikimedia asks for gentle, serial requests


def enqueue_fetch(s, target: str, native: str, lemma: str, fields: list[str]):
    """Queue image acquisition after text materialization; idempotent per word."""
    wanted = sorted(set(fields) & {"sense_image", "context_image", "thumbnail"})
    if not wanted:
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


def claim_fetch(s, worker_id: str):
    """Claim one deferred image lookup without blocking other workers."""
    stale = datetime.now(timezone.utc) - timedelta(minutes=10)
    task = s.execute(select(m.ImageFetchTask).where(
        (m.ImageFetchTask.status == "queued")
        | ((m.ImageFetchTask.status == "running")
           & (m.ImageFetchTask.started_at < stale))
    ).order_by(m.ImageFetchTask.created_at).limit(1).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if task is None:
        return None
    task.status = "running"
    task.worker_id = worker_id
    task.started_at = datetime.now(timezone.utc)
    task.attempts = (task.attempts or 0) + 1
    s.flush()
    return task


def run_fetch(s, task_id: int):
    """Run a queued lookup. Downloaded assets remain pending human/AI review."""
    task = s.get(m.ImageFetchTask, task_id)
    if task is None:
        return None
    try:
        share_existing(s, task.target_language, task.lemma)
        got = auto_fetch(s, task.target_language, task.native_language, task.lemma)
        task.error = "；".join(got.get("errors", [])[:3]) or None
        task.status = "completed_with_errors" if task.error else "completed"
    except Exception as exc:  # noqa: BLE001 -- keep the independent queue moving
        got = {"senses": 0, "images": 0, "errors": [str(exc)]}
        task.status = "failed"
        task.error = f"{type(exc).__name__}: {exc}"[:2000]
    task.finished_at = datetime.now(timezone.utc)
    return got


def fetch(url, limit=MAX_BYTES):
    request = urllib.request.Request(check_url(url), headers={'User-Agent': config.USER_AGENT})
    for attempt in range(4):
        with _throttle:
            wait = _last_request[0] + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_request[0] = time.monotonic()
        try:
            with urllib.request.build_opener(Redirect).open(request, timeout=25) as response:
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


def search(s, sense_id, qid):
    if not s.get(m.Sense, sense_id):
        raise ValueError('找不到指定詞義')
    if not re.fullmatch(r'Q[1-9][0-9]*', qid):
        raise ValueError('請輸入有效 Wikidata 概念 ID，例如 Q89')
    entity = json.loads(fetch(f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json'))['entities'][qid]
    label = entity.get('labels', {}).get('en', {}).get('value')
    if not label:
        raise ValueError('概念沒有英文標籤')
    titles = ['File:' + c['mainsnak']['datavalue']['value'] for c in entity.get('claims', {}).get('P18', []) if 'datavalue' in c['mainsnak']]
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
        folder = config.MEDIA / 'images' / 'wikimedia_commons'; folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{digest}.{extension}'; thumbnail = folder / f'{digest}.thumb.webp'
        for file, data in [(path, raw), (thumbnail, thumb.getvalue())]:
            temp = file.with_name(uuid.uuid4().hex + '.part')
            try:
                temp.write_bytes(data); os.replace(temp, file)
            finally:
                temp.unlink(missing_ok=True)
        now = datetime.now(timezone.utc)
        asset = m.ImageAsset(source='wikimedia_commons', source_image_id=meta['title'], page_url=meta['page_url'], file_url=meta['file_url'],
                             author=meta['author'], attribution=meta['attribution'], license_code=license_now, license_url=meta['license_url'],
                             retrieved_at=now, verified_at=now, mime=mime, width=width, height=height, size_bytes=len(raw), sha256=digest,
                             path=str(path.relative_to(config.MEDIA)), thumbnail_path=str(thumbnail.relative_to(config.MEDIA)), status='ready', safety_status='unchecked')
        s.add(asset); s.flush()
    c.image_asset_id = asset.id
    binding = s.scalars(select(m.SenseImage).where(m.SenseImage.sense_id == c.sense_id, m.SenseImage.image_asset_id == asset.id)).first()
    if binding is None:
        binding = m.SenseImage(sense_id=c.sense_id, image_asset_id=asset.id, role='representative', review_status='pending', alt_native={})
        s.add(binding); s.flush()
    return {'id': binding.id, 'status': binding.review_status}


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


def auto_fetch(s, target, native, lemma, *, senses_per_lexeme=2, per_sense=3):
    """Find and download pictures for a word's first senses. Returns
    {"senses": n, "images": n, "errors": [...]}."""
    rows = s.execute(text('''SELECT sn.id, d.text AS gloss, l.pos, t.text AS native
        FROM senses sn JOIN lexemes l ON l.id = sn.lexeme_id
        LEFT JOIN definitions d ON d.sense_id = sn.id AND d.language = l.language
        LEFT JOIN sense_translations t ON t.sense_id = sn.id AND t.native_language = :native
        WHERE l.language = :target AND l.normalized = :lemma AND l.status = 'full'
          AND l.pos = 'noun' AND sn.ordinal < :k ORDER BY l.id, sn.ordinal'''),
        {'target': target, 'native': native, 'lemma': lemma, 'k': senses_per_lexeme}).all()
    out = {'senses': 0, 'images': 0, 'errors': []}
    # Two senses of one word matching one concept would get the same pictures:
    # a concept or a file already used for this word is not used again.
    used_concepts, used_assets = set(), set(s.scalars(select(m.SenseImage.image_asset_id).join(
        m.Sense, m.Sense.id == m.SenseImage.sense_id).join(m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id)
        .where(m.Lexeme.language == target, m.Lexeme.normalized == lemma)).all())
    for sense_id, gloss, pos, meaning in rows:
        have = s.scalar(select(func.count()).select_from(m.SenseImage).where(
            m.SenseImage.sense_id == sense_id, m.SenseImage.review_status != 'rejected'))
        if have >= per_sense:
            out['senses'] += 1
            continue
        try:
            concept = match_concept(lemma, gloss, meaning)
            if concept is None:
                continue
            qid, label, _ = concept
            if qid in used_concepts:
                continue  # the word's earlier sense already shows this concept
            used_concepts.add(qid)
            found = search(s, sense_id, qid)
            p18 = set(found.get('p18', []))
            ranked = sorted(found['candidates'], key=lambda c: c['title'] not in p18)
            got = have
            for c in ranked:
                if got >= per_sense:
                    break
                if c.get('imported'):
                    continue
                cand = s.get(m.ImageCandidate, c['id'])
                meta = {**cand.metadata_, 'p18': c['title'] in p18}
                cand.metadata_ = meta
                cand.score = semantic_score(meta, lemma, label)
                if cand.score < 0.7:
                    continue  # stays a candidate for manual review; not downloaded
                try:
                    bound = ingest(s, c['id'])
                except (ValueError, OSError) as e:
                    out['errors'].append(f"{c['title']}：{e}")
                    continue
                binding = s.get(m.SenseImage, bound['id'])
                if binding.image_asset_id in used_assets:
                    s.delete(binding)  # the same file under another sense of this word
                    continue
                used_assets.add(binding.image_asset_id)
                binding.semantic_score = cand.score
                # One representative picture a sense (the first, best one).
                binding.role = 'representative' if got == 0 else 'context'
                binding.ordinal = got
                got += 1
                out['images'] += 1
            out['senses'] += 1
        except (ValueError, KeyError, OSError) as e:
            out['errors'].append(f"詞義 #{sense_id}：{e}")
    return out


# ── AI labels ─────────────────────────────────────────────────────────
# Every downloaded picture goes through the local vision model, like a
# learner's photo: the labels and where they are. A label that is the
# sense's own word confirms the picture (the spec's semantic check).

TAGS_WANTED, TAGS_MAX = 8, 18  # was 12; CEFR enrich aims for ~3 x A1-C2 (~18)
# A label passes only when the vision model, checking it against the picture
# again, is at least this sure it is shown (the user: 辨識 ≥ 80 以上才通過).
TAG_PASS = 0.8
# Default import/tag path uses one CEFR-band call (~3 labels per A1–C2).
# Set LEXICON_TAG_MODE=legacy to restore the multi-focus TAG_LOOKS loop.
TAG_MODE = os.environ.get('LEXICON_TAG_MODE', 'cefr').strip().lower() or 'cefr'
CEFR_PER_LEVEL = int(os.environ.get('LEXICON_CEFR_PER_LEVEL', '3'))
# When 1/true: skip the second /score vision pass and assign provisional scores
# for grounded labels (point/box or CEFR band). Later tag_pending/rescore can refine.
DEFER_TAG_SCORE = os.environ.get('LEXICON_DEFER_TAG_SCORE', '0').strip().lower() in {
    '1', 'true', 'yes', 'on'}
# Legacy multi-look focuses (only when TAG_MODE=legacy).
TAG_LOOKS = ('', 'harder', 'descriptions')


def labelled(asset) -> bool:
    """Labels that count: done, or scored by the quick pass (still waiting
    for more looks, but every label it has passed 80%)."""
    return asset.tag_status == 'done' or bool(asset.tags) and all(
        t.get('score') is not None for t in asset.tags)


class TaggerUnavailable(ValueError):
    """The tagging service can't be reached; the picture stays pending."""


def tag_asset(s, asset_id):
    asset = s.get(m.ImageAsset, asset_id)
    if not asset or asset.status != 'ready' or not asset.path:
        raise ValueError('圖片尚未下載')
    data = (config.MEDIA / asset.path).read_bytes()

    def ask(extra=''):
        request = urllib.request.Request(
            config.AI_URL.rstrip('/') + '/tag?level=B1&lang=en&native=zh-TW' + extra, data=data,
            method='POST', headers={'X-API-Key': config.AI_KEY,
                                    'Content-Type': asset.mime or 'image/jpeg'})
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read())

    def ask_cefr(exclude: list[str]):
        qs = urllib.parse.urlencode({
            'mode': 'cefr', 'lang': 'en', 'native': 'zh-TW',
            'per_level': str(CEFR_PER_LEVEL),
            **({'exclude': ','.join(exclude[:60])} if exclude else {}),
        })
        request = urllib.request.Request(
            config.AI_URL.rstrip('/') + '/tag?' + qs, data=data, method='POST',
            headers={'X-API-Key': config.AI_KEY,
                     'Content-Type': asset.mime or 'image/jpeg'})
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read())

    passed, dropped, seen, model = [], [], [], ''
    try:
        if TAG_MODE in ('cefr', 'bands', 'cefr-bands'):
            out = ask_cefr(seen)
            model = model or str(out.get('model', ''))
            new = []
            for c in out.get('candidates', []):
                word = str(c.get('word', '')).strip()
                if word and word.lower() not in {w.lower() for w in seen}:
                    seen.append(word)
                    tag = {'word': word, 'pos': c.get('pos') or 'noun',
                           'point': c.get('point'), 'box': c.get('box')}
                    model_cefr = str(c.get('cefr') or c.get('modelLevel') or '').upper()
                    if model_cefr in {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'}:
                        tag['cefr'] = model_cefr
                        tag['modelLevel'] = model_cefr
                    if c.get('visualConfidence') is not None:
                        tag['visualConfidence'] = c.get('visualConfidence')
                    new.append(tag)
            score_tags(data, new, asset.mime, defer=DEFER_TAG_SCORE)
            for t in new:
                (passed if (t.get('score') or 0) >= TAG_PASS else dropped).append(t)
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
                score_tags(data, new, asset.mime, defer=DEFER_TAG_SCORE)
                for t in new:
                    (passed if (t.get('score') or 0) >= TAG_PASS else dropped).append(t)
                if len(passed) >= TAGS_WANTED:
                    break
    except urllib.error.HTTPError as e:
        asset.tag_status = 'failed'  # the model answered badly for this picture
        raise ValueError(f'AI 標籤失敗：{e}') from e
    except (urllib.error.URLError, OSError) as e:
        # The tagging service is down or busy: try this picture again later.
        raise TaggerUnavailable(f'標籤服務無法連線：{e}') from e
    except ValueError as e:
        asset.tag_status = 'failed'
        raise ValueError(f'AI 標籤失敗：{e}') from e
    _settle(s, asset, passed, dropped, model)
    return asset.tags



def _settle(s, asset, passed, dropped, model, done=True):
    """Passed labels (best first) on the picture, the others aside; a done
    picture then belongs to the words its labels name, and only those."""
    asset.tags = sorted(passed, key=lambda t: -t['score'])[:TAGS_MAX]
    asset.dropped_tags = sorted(dropped, key=lambda t: -(t.get('score') or 0))
    asset.tag_model = (model or asset.tag_model or '')[:64]
    asset.tagged_at = datetime.now(timezone.utc)
    if done:
        asset.tag_status = 'done'
    for binding, lemma in s.execute(select(m.SenseImage, m.Lexeme.normalized).join(
            m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
            m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
            m.SenseImage.image_asset_id == asset.id)).all():
        judge(s, binding, asset, lemma)
    share(s, asset)


def rescore(s, asset) -> None:
    """A picture labelled before the 80% rule: score the labels it already
    has (one quick check, no new look) so every picture shows its scores at
    once. Eight passing is enough; with fewer it stays pending for the full
    re-labelling (more looks)."""
    tags = [{k: t.get(k) for k in ('word', 'pos', 'point', 'box')}
            for t in asset.tags or [] if str(t.get('word', '')).strip()]
    try:
        score_tags((config.MEDIA / asset.path).read_bytes(), tags, asset.mime)
    except urllib.error.HTTPError as e:
        raise ValueError(f'評分失敗：{e}') from e
    except (urllib.error.URLError, OSError) as e:
        raise TaggerUnavailable(f'標籤服務無法連線：{e}') from e
    passed = [t for t in tags if (t.get('score') or 0) >= TAG_PASS]
    dropped = [t for t in tags if (t.get('score') or 0) < TAG_PASS]
    _settle(s, asset, passed, dropped, None, done=len(passed) >= TAGS_WANTED)


TAG_POS = {'adjective': 'adj', 'adverb': 'adv'}


def share(s, asset, only_lemma=None) -> int:
    """Put a picture under every word its AI labels name (a bench picture
    labelled gravel also shows gravel). A picture a reviewer already approved
    for another word is approved here too; otherwise it waits for review."""
    if not labelled(asset) or asset.status != 'ready':
        return 0
    reviewed = s.scalar(select(func.count()).select_from(m.SenseImage).where(
        m.SenseImage.image_asset_id == asset.id, m.SenseImage.review_status == 'approved')) > 0
    added = 0
    for tag in asset.tags or []:
        word = str(tag.get('word', '')).strip().lower()
        if not word or (only_lemma and word != only_lemma):
            continue
        lexemes = s.scalars(select(m.Lexeme).where(
            m.Lexeme.normalized == word, m.Lexeme.status == 'full').order_by(m.Lexeme.id)).all()
        if not lexemes:
            continue
        pos = TAG_POS.get(str(tag.get('pos', '')), str(tag.get('pos', '')))
        lexeme = next((lx for lx in lexemes if lx.pos == pos), lexemes[0])
        sense = s.scalars(select(m.Sense).where(m.Sense.lexeme_id == lexeme.id)
                          .order_by(m.Sense.ordinal)).first()
        if sense is None:
            continue
        # Once per word: not again under another sense of it.
        if s.scalar(select(func.count()).select_from(m.SenseImage).join(
                m.Sense, m.Sense.id == m.SenseImage.sense_id).join(
                m.Lexeme, m.Lexeme.id == m.Sense.lexeme_id).where(
                m.SenseImage.image_asset_id == asset.id, m.Lexeme.normalized == word)):
            continue
        has = s.scalar(select(func.count()).select_from(m.SenseImage).where(
            m.SenseImage.sense_id == sense.id, m.SenseImage.review_status != 'rejected'))
        binding = m.SenseImage(sense_id=sense.id, image_asset_id=asset.id,
                               role='context' if has else 'representative', ordinal=has,
                               semantic_score=0.95, alt_native={},
                               review_status='approved' if reviewed else 'pending')
        s.add(binding)
        s.flush()
        s.add(m.ImageReview(sense_image_id=binding.id, decision=binding.review_status,
                            note=f'共用圖片：AI 標籤認出「{word}」'
                                 + ('（原圖已由管理者核准）' if reviewed else '')))
        added += 1
    return added


def share_existing(s, target, lemma) -> int:
    """A word imported after pictures were labelled gets those that name it."""
    added = 0
    for asset in s.scalars(select(m.ImageAsset).where(
            m.ImageAsset.tag_status == 'done',
            text("EXISTS (SELECT 1 FROM jsonb_array_elements(image_assets.tags::jsonb) t"
                 " WHERE lower(t->>'word') = :w)").bindparams(w=lemma))).all():
        added += share(s, asset, only_lemma=lemma)
    return added


def shows_word(tags, lemma) -> bool:
    """The AI labels name the word (or its plural, or a phrase with it)."""
    from .adapters.local import regular_plural
    forms = {lemma.lower(), regular_plural(lemma.lower())}
    words = {str(t.get('word', '')).lower() for t in tags or []}
    return bool(forms & words) or any(f in w.split() for w in words for f in forms)


def judge(s, binding, asset, lemma) -> None:
    """A picture belongs to a word only when the vision model sees the word
    in it: confirmed pictures score 0.95; the others are taken off the word
    (the user: 沒有該單字的圖片不要放在該單字內)."""
    if not labelled(asset):
        return
    if shows_word(asset.tags, lemma):
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
    pending = [t for t in tags if t.get('score') is None]
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
        headers={'X-API-Key': config.AI_KEY, 'Content-Type': mime or 'image/jpeg'})
    with urllib.request.urlopen(request, timeout=300) as response:
        out = json.loads(response.read())
    scores = {str(x.get('word', '')).lower(): x.get('score') for x in out.get('scores', [])}
    for t in pending:
        t['score'] = scores.get(str(t['word']).strip().lower())



def tag_pending(s, limit=1, quick_only=False):
    """Label (and score) the next downloaded pictures still without AI labels,
    pictures waiting for review first: the reviewer reads their labels."""
    done = 0
    # First every picture still carrying unscored (or failing) labels gets
    # its scores and the 80% rule (quick), then the full re-labelling of
    # those still short of 8.
    for asset in s.scalars(select(m.ImageAsset).where(
            m.ImageAsset.status == 'ready', m.ImageAsset.tag_status == 'pending',
            text("EXISTS (SELECT 1 FROM json_array_elements(image_assets.tags::json) t"
                 " WHERE t->'score' IS NULL OR (t->>'score')::float < :pass)")
            .bindparams(**{'pass': TAG_PASS}))
            .order_by(m.ImageAsset.id).limit(limit)).all():
        try:
            rescore(s, asset)
        except TaggerUnavailable:
            return 0
        except ValueError:
            asset.tag_status = 'failed'
        done += 1
    if done:
        return done
    # Then the full labelling: pictures with no labels at all first (always,
    # every picture needs scored labels), the rest only when not quick_only.
    unlabelled = text("(image_assets.tags IS NULL OR image_assets.tags::text = '[]')")
    for asset in s.scalars(select(m.ImageAsset).where(
            m.ImageAsset.status == 'ready', m.ImageAsset.tag_status == 'pending',
            *([unlabelled] if quick_only else []))
            .order_by(text("(image_assets.tags IS NULL OR image_assets.tags::text = '[]') DESC"),
                      text("EXISTS (SELECT 1 FROM sense_images b WHERE b.image_asset_id ="
                           " image_assets.id AND b.review_status = 'pending') DESC"),
                      m.ImageAsset.id).limit(limit)).all():
        try:
            tag_asset(s, asset.id)
        except TaggerUnavailable:
            return 0  # the worker waits and tries again
        except ValueError:
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
                    or not (config.MEDIA / asset.path).is_file() \
                    or asset.tag_status != 'done' or not shows_word(asset.tags, lemma):
                continue
            binding.review_status = 'approved'
            asset.safety_status = 'safe'
            s.add(m.ImageReview(sense_image_id=binding.id, decision='approved', note=body.note))
            approved += 1
        return {'approved': approved}

    @app.get('/images', dependencies=[auth])
    def library(s=Depends(db.get_session)):
        # By word and sense; "shared" counts the other senses using the same file.
        return [dict(r) for r in s.execute(text('''SELECT si.id,si.sense_id,si.review_status,si.semantic_score,si.role,
            sn.ordinal,l.lemma,l.normalized,l.pos,l.language,d.text AS gloss,t.text AS native,
            a.id AS asset_id,a.author,a.license_code,a.page_url,a.size_bytes,a.width,a.height,a.status,
            a.tag_status,coalesce(jsonb_array_length(a.tags::jsonb),0) AS tag_count,
            coalesce((SELECT jsonb_agg(jsonb_build_object('word',x->>'word','pos',x->>'pos',
                'score',x->'score')) FROM jsonb_array_elements(a.tags::jsonb) x),'[]'::jsonb) AS tags,
            coalesce((SELECT jsonb_agg(jsonb_build_object('word',x->>'word','pos',x->>'pos',
                'score',x->'score')) FROM jsonb_array_elements(a.dropped_tags::jsonb) x),
                '[]'::jsonb) AS dropped_tags,
            (SELECT count(*) FROM sense_images o WHERE o.image_asset_id=a.id)-1 AS shared
            FROM sense_images si JOIN image_assets a ON a.id=si.image_asset_id
            JOIN senses sn ON sn.id=si.sense_id JOIN lexemes l ON l.id=sn.lexeme_id
            LEFT JOIN definitions d ON d.sense_id=sn.id AND d.language=l.language
            LEFT JOIN sense_translations t ON t.sense_id=sn.id AND t.native_language='zh-TW'
            ORDER BY l.normalized,l.id,sn.ordinal,si.review_status,si.id''')).mappings()]

    @app.post('/images/search', dependencies=[auth])
    def search_endpoint(body: SearchBody, s=Depends(db.get_session)):
        try:
            return search(s, body.sense_id, body.qid)
        except (ValueError, KeyError, OSError) as e:
            raise HTTPException(400, str(e))

    @app.post('/images/candidates/{candidate_id}/import', dependencies=[auth])
    def import_endpoint(candidate_id: int, s=Depends(db.get_session)):
        try:
            return ingest(s, candidate_id)
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
        binding.review_status = body.decision
        if body.decision == 'approved':
            asset.safety_status = 'safe'
        s.add(m.ImageReview(sense_image_id=binding.id, decision=body.decision, note=body.note))
        return {'id': binding.id, 'status': binding.review_status}

    @app.post('/images/{asset_id}/tag', dependencies=[auth])
    def tag_endpoint(asset_id: int, s=Depends(db.get_session)):
        try:
            return {'tags': tag_asset(s, asset_id)}
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get('/images/{asset_id}/file')
    def image_file(asset_id: int, s=Depends(db.get_session)):
        asset = s.get(m.ImageAsset, asset_id)
        if not asset or asset.status != 'ready' or not asset.path:
            raise HTTPException(404, '找不到圖片')
        path = (config.MEDIA / asset.path).resolve()
        if not path.is_relative_to(config.MEDIA.resolve()) or not path.is_file():
            raise HTTPException(404, '找不到圖片檔案')
        return FileResponse(path, media_type=asset.mime)
