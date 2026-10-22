"""Local app + read-only live dictionary. Run: python serve_app.py --port 8123.

Database credentials stay in the Python process. The browser receives only
dictionary content, never admin credentials. Personal learning stays local.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import ipaddress
import json
import logging
import mimetypes
import os
import re
import secrets
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'lexicon' / 'backend'))
from app import accounts, app_pack, catalog, config, db, decks, exporter
from app.meaning_labels import add_meaning_tags, meaning_index  # noqa: F401 (meaning_index: tools use serve_app.meaning_index)
try:
    import brotli as _brotli
except ImportError:
    _brotli = None
from lexicon_transport import SnapshotStore, Warming, accepts_gzip, matches_etag

_lock = threading.Lock()
_cache = {}


# Requests per minute per client on the public name (the app polls every ~30 s
# and downloads a pack's images/audio in bursts).
RATE_LIMITS = {'/api/lexicon': 30, '/api/image': 600, '/api/audio': 600,
               '/api/decks': 60,
               '/api/account': 30, '/api/shares': 60}   # accounts + sharing (card #324)   # 卡片集: the list and one deck's content (card #323)
RATE_HITS: dict = {}
RATE_LOCK = threading.Lock()


def snapshot_directory():
    # Code/quality changes must not reuse a snapshot built with old rules.
    revision = hashlib.sha256()
    sources = [Path(__file__), ROOT / 'lexicon_transport.py']
    sources += sorted((ROOT / 'lexicon' / 'backend' / 'app').rglob('*.py'))
    sources += sorted((ROOT / 'lexicon' / 'quality').rglob('*.json'))
    for source in sources:
        revision.update(source.relative_to(ROOT).as_posix().encode())
        revision.update(source.read_bytes())
    return ROOT / '.runtime' / 'dictionary-snapshots' / revision.hexdigest()[:20]


_http_snapshots = None
_http_snapshots_lock = threading.Lock()


def http_snapshot(target, native, wait=False):
    if target not in catalog.LANGUAGES or native not in catalog.LANGUAGES or target == native:
        raise ValueError('Unsupported language pair')
    global _http_snapshots
    with _http_snapshots_lock:
        if _http_snapshots is None:
            # Card #380: a restart after a code change answers from the last
            # revision's snapshot while this revision's pack builds (5+ min).
            directory = snapshot_directory()
            _http_snapshots = SnapshotStore(live_pack, directory, stale_root=directory.parent,
                                            wait_first=wait)
    return _http_snapshots.get(target, native)


# The packs the app and website ask for; built right after a restart, not on
# the first request.
WARM_PAIRS = (('en', 'zh-TW'), ('fr', 'en'))


def warm_snapshots():
    for pair in WARM_PAIRS:
        try:
            http_snapshot(*pair)
        except Warming:
            pass
        except Exception:
            logging.exception('Could not warm dictionary %s', pair)


def english_form_lemmas(session) -> dict[str, list[str]]:
    """Every stored English form (lower-cased) → the full entries it belongs
    to (trees → tree, children → child, lit → light), one query for the whole
    pack build (card #510). Mirrors the forms step of images.resolve_full_lexeme."""
    from sqlalchemy import select
    from app import models as m
    out: dict[str, list[str]] = {}
    rows = session.execute(select(m.Form.form, m.Form.normalized, m.Lexeme.normalized).join(
        m.Lexeme, m.Lexeme.id == m.Form.lexeme_id).where(
        m.Lexeme.language == 'en', m.Lexeme.status == 'full').order_by(m.Lexeme.id)).all()
    for form, normalized, lemma in rows:
        for spelling in {str(form or '').strip().lower(), str(normalized or '').strip().lower()}:
            if spelling and spelling != lemma:
                bucket = out.setdefault(spelling, [])
                if lemma not in bucket:
                    bucket.append(lemma)
    return out


def tag_aliases(item, form_lemmas) -> list[str]:
    """The entry spellings a vision tag may stand for, the tag's own word
    first: its recorded lemma, the dictionary's stored forms and the regular
    inflection stems (holding → hold, glasses → glass, clouds → cloud) — the
    same candidates binding uses (images.resolve_full_lexeme, #197). The
    stems are not verified here; they only match an entry that is already
    approved for the picture."""
    from app.images import _morphology_lemmas
    word = ' '.join(str(item.get('word') or '').strip().lower().split())
    if not word:
        return []
    out = [word]
    lemma = ' '.join(str(item.get('lemma') or '').strip().lower().split())
    if lemma:
        out.append(lemma)
    out.extend(form_lemmas.get(word, ()))
    out.extend(_morphology_lemmas(word))
    return list(dict.fromkeys(out))


def catalog_snapshot(session, target):
    """Publish only reviewed pictures and their approved dictionary labels.

    Model tags are suggestions for the review workflow.  They must not leak into
    the learner-facing album until a reviewer has approved the corresponding
    sense/image binding, and the label must resolve to a complete target-language
    lexeme.
    """
    from sqlalchemy import select
    from app import models as m
    words = list(session.scalars(select(m.Lexeme).where(m.Lexeme.language == target).order_by(m.Lexeme.id)))
    full_words = {word.id: word for word in words if word.status == 'full'}
    sense_words = dict(session.execute(select(m.Sense.id, m.Sense.lexeme_id)).all())
    levels = {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'}
    # Levels outside the CEFR-J / Octanove lists are frequency estimates and
    # say so (問題回報 #139 decision, #132: noodle C1 is an estimate).
    from app.adapters.local import cefr_list
    listed = cefr_list()

    def cefr_source(word, band):
        # French levels are frequency estimates (docs/french_sources.md); the
        # English CEFR-J list would match a French word spelled like an English
        # one (pain → pain), so it is not consulted (問題回報 #362).
        if target != 'en':
            return 'estimate'
        hit = listed.get(word.normalized)
        return 'cefr-j' if hit and band in hit[1].values() else 'estimate'
    tags = {}
    for binding in session.scalars(select(m.SenseImage).order_by(m.SenseImage.id)):
        word_id = sense_words.get(binding.sense_id)
        if binding.review_status == 'approved' and word_id in full_words:
            tags.setdefault(binding.image_asset_id, []).append({
                'lexeme_id': word_id, 'sense_id': binding.sense_id,
                'review_status': binding.review_status, 'origin': 'binding'})
    # Vision labels are English words (#331). In another language's pack a
    # picture shared by meaning (#336) is bound to one word only, so it also
    # names the target words whose main sense means one of the picture's
    # approved English words (#347: chat → cat, table → table).
    sense_label, by_meaning, rivals = ({}, {}, {}) if target == 'en' else meaning_index(session, target, True)
    add_meaning_tags(session, target, tags, full_words, by_meaning, rivals)
    # Card #510 (問題回報 #524): the tagger names what it sees in the form it
    # sees it (holding, trees, clouds, glasses) while the binding hangs on the
    # entry (hold, tree, cloud, glass). Matching the entry's spelling alone left
    # 13% of approved labels without a position, so the app drew no pin.
    form_lemmas = english_form_lemmas(session)
    # The vision model supplies positions, but only approved bindings decide
    # which labels are visible. This prevents foreign, rejected and unrelated
    # suggestions from appearing in the app.
    images = []
    for asset in session.scalars(select(m.ImageAsset).order_by(m.ImageAsset.id)):
        if asset.id not in tags:
            continue
        positioned = {}
        positioned_dropped = {}
        positioned_alias = {}
        model_cefr = {}
        # Card #408 (問題回報 #407): the tagger sets aside a tag it will not
        # offer for review (no CEFR level, over the per-picture cap) but keeps
        # its spot. A reviewer-approved binding still has that spot to draw.
        for item in asset.dropped_tags or []:
            name = str(item.get('word', '')).strip().lower()
            if name and item.get('point') and name not in positioned_dropped:
                positioned_dropped[name] = item
        for item in asset.tags or []:
            name = str(item.get('word', '')).strip().lower()
            if not name:
                continue
            if item.get('point') and name not in positioned:
                positioned[name] = item
            band = str(item.get('cefr') or item.get('modelLevel') or '').strip().upper()
            if band in levels:
                model_cefr[name] = band
        # The entries a positioned tag also places (#510): its tags first, then
        # the set-aside ones; the first tag naming an entry keeps it.
        for item in list(positioned.values()) + list(positioned_dropped.values()):
            for alias in tag_aliases(item, form_lemmas):
                positioned_alias.setdefault(alias, item)
        enriched_tags = []
        labels = []
        seen_words = set()
        for binding in tags[asset.id]:
            word = full_words[binding['lexeme_id']]
            if word.id in seen_words:
                continue
            # An explicit approved sense/image binding is sufficient to
            # publish the label. Vision coordinates improve the overlay but
            # must not erase a human-approved label when tagging is pending.
            names = sense_label.get(binding['sense_id'], [word.normalized])
            item = next((positioned[name] for name in names if name in positioned), None)
            if item is None:
                item = next((positioned_dropped[name] for name in names
                             if name in positioned_dropped), None)
            if item is None:  # #510: the tag names the entry in another form
                item = next((positioned_alias[name] for name in names
                             if name in positioned_alias), {})
            seen_words.add(word.id)
            # Decision 2 / P2: the photo tag's level is the card's level
            # (lexicon), never the vision model's guess.
            band = str(word.cefr or '').strip().upper()
            tag_out = dict(binding)
            if band in levels:
                tag_out['cefr'] = band
                tag_out['cefr_source'] = cefr_source(word, band)
            enriched_tags.append(tag_out)
            label = {'word': word.lemma, 'pos': word.pos, 'point': item.get('point'),
                     'box': item.get('box'), 'lexeme_id': word.id}
            if band in levels:
                label['cefr'] = band
                label['cefr_source'] = tag_out['cefr_source']
            labels.append(label)
        images.append({'id': asset.id, 'url': f'/api/image?id={asset.id}',
                       'width': asset.width, 'height': asset.height,
                       'status': asset.status, 'tags': enriched_tags, 'labels': labels,
                       'author': asset.author, 'attribution': asset.attribution,
                       'license': asset.license_code, 'source': asset.source})
    return words, images


_gzip_cache: dict[str, bytes] = {}


def gzipped(etag: str, body: bytes) -> bytes:
    """The pack body gzipped once per version."""
    if etag not in _gzip_cache:
        import gzip
        _gzip_cache.clear()
        _gzip_cache[etag] = gzip.compress(body, compresslevel=6)
    return _gzip_cache[etag]


def merge_catalog(exported: dict, word_metadata: list[dict]) -> list[dict]:
    """Every catalog word with this direction's exported data. The catalog
    says which words are complete in the dictionary, not in this language
    direction: a word the direction's export lacks (never imported for fr,
    say) is a stub here, not a 'full' word with no meaning."""
    out = []
    for w in word_metadata:
        data = exported.get(w['id'], {})
        out.append({**data, **w, **({} if 'senses' in data else {'status': 'stub'})})
    return out


def live_pack(target: str, native: str):
    if target not in catalog.LANGUAGES or native not in catalog.LANGUAGES or target == native:
        raise ValueError('Unsupported language pair')
    with _lock:
        cached = _cache.get((target, native))
        if cached and time.monotonic() - cached[0] < 120:
            return cached[1:3]
        with tempfile.TemporaryDirectory(prefix='dictionary-live-') as folder:
            path = Path(folder) / 'dictionary.sqlite'
            with db.SessionLocal() as session:
                # One consistent, read-only database snapshot; no release/job is created.
                session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
                from sqlalchemy import text
                session.execute(text('SET TRANSACTION READ ONLY'))
                # Check the actual exported tables, including deletions and
                # direct corrections, without rebuilding an unchanged pack.
                from app import models as m
                signatures = []
                for model in (m.FieldValue, m.Lexeme, m.LexemeRedirect,
                              m.Sense, m.Example, m.LexemeRelation, m.AudioAsset,
                              m.ImageAsset, m.SenseImage, m.ImageCandidate,
                              m.CardTemplate, m.CardTemplateVersion):
                    table = model.__tablename__
                    # Order-free sum of row hashes: no sort of 500,000 rows
                    # (card #380: 43 s -> 9 s per check, every 2 minutes).
                    signatures.append(tuple(session.execute(text(
                        f"SELECT count(*), coalesce(sum(('x' || left(md5(t::text), 15))"
                        f"::bit(60)::bigint), 0) FROM {table} t"
                    )).one()))
                fingerprint = tuple(signatures)
                if cached and cached[3] == fingerprint:
                    _cache[(target, native)] = (time.monotonic(), cached[1], cached[2], fingerprint)
                    return cached[1:3]
                exporter._build(session, path, target, native, None, False, Path(folder),
                                copy_media=False)
                from app.card_templates import published
                card_template = published(session)
                catalog_words, catalog_images = catalog_snapshot(session, target)
                word_metadata = [dict(id=w.id, lemma=w.lemma, normalized=w.normalized,
                                      pos=w.pos, status=w.status, cefr=w.cefr) for w in catalog_words]
            pack = app_pack.build(path)
            pack['card_template'] = card_template
            exported = {w['id']: w for w in pack['lexemes']}
            pack['lexemes'] = merge_catalog(exported, word_metadata)
            # The catalog's CEFR replaced the pack's; rank the usages again.
            app_pack.rank_usages(pack['lexemes'], language=target)
            # After the catalog merge: a form's card must be a full word here.
            app_pack.assign_cards(pack['lexemes'], target)
            # Owner decision #191 (redirects, CEFR) after the cards are reassigned.
            from app import quality
            quality.apply_decisions(pack)
            pack['catalog_images'] = catalog_images
            # #195: a photo tag shows a main sense with Chinese.
            quality.fix_catalog_senses(pack)
            # Decision 1 / P2: stubs leave the pack; pointers stay only when
            # they resolve to a full entry.
            from app import qc as pack_qc
            pack_qc.strip_stubs(pack)
            from app.picture_need import assign_picture_ids
            assign_picture_ids(pack['lexemes'])
            # QUALITY P3: every pack build records validators + metrics.
            from app import qc_hook
            qc_hook.record_pack_metrics(pack)
            pack['catalog_version'] = 1
        # Export time is not content. Stable versions avoid needless local writes.
        pack.pop('created_at', None)
        pack['media_base'] = '/api/audio'
        content = json.dumps(pack, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        version = hashlib.sha256(content.encode()).hexdigest()
        pack['created_at'] = version
        body = json.dumps(pack, ensure_ascii=False, separators=(',', ':')).encode()
        etag = '"' + version + '"'
        _cache[(target, native)] = (time.monotonic(), body, etag, fingerprint)
        return body, etag


class Handler(SimpleHTTPRequestHandler):
    def send_header(self, keyword, value):
        if keyword.lower() == 'cache-control':
            self._cache_header_sent = True
        super().send_header(keyword, value)

    def end_headers(self):
        self._send_cors()
        # The web build (main.dart.js …) is revalidated on every load, so a
        # plain reload picks up a rebuilt app instead of a heuristically
        # cached old one. API responses set their own Cache-Control.
        if not getattr(self, '_cache_header_sent', False):
            super().send_header('Cache-Control', 'no-cache')
        self._cache_header_sent = False
        super().end_headers()

    # Static web build (問題回報 #357): compressed once per file version,
    # revalidated by ETag, and fonts / canvaskit kept for a week so a warm
    # visit downloads nothing big. index.html and the bootstrap stay no-cache.
    STATIC_ZIP = {'.js', '.json', '.wasm', '.ttf', '.otf', '.html', '.css', '.svg', '.map', '.txt'}
    STATIC_LONG = ('/fonts/', '/canvaskit/', '/icons/')
    _static_cache: dict = {}

    def send_static(self, url_path: str) -> bool:
        if self.command not in ('GET', 'HEAD'):
            return False
        path = Path(self.translate_path(url_path))
        if path.is_dir():
            path = path / 'index.html'
        if not path.is_file():
            return False
        stat = path.stat()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if path.suffix == '.wasm':
            ctype = 'application/wasm'
        accept = self.headers.get('Accept-Encoding', '')
        encoding = None
        if path.suffix in self.STATIC_ZIP and stat.st_size > 1024:
            if 'br' in accept and _brotli is not None:
                encoding = 'br'
            elif accepts_gzip(accept):
                encoding = 'gzip'
        long_cache = url_path.startswith(self.STATIC_LONG) and path.name not in ('index.html',)
        self.send_response(304 if matches_etag(self.headers.get('If-None-Match', ''), etag) else 200)
        self.send_header('ETag', etag)
        self.send_header('Cache-Control', 'public, max-age=604800' if long_cache else 'no-cache')
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('Content-Type', ctype)
        self.send_header('X-Content-Type-Options', 'nosniff')
        if self._response_status() == 304:
            self.end_headers()
            return True
        body = None
        if encoding:
            key = (str(path), etag, encoding)
            body = self._static_cache.get(key)
            if body is None:
                raw = path.read_bytes()
                if encoding == 'br':
                    body = _brotli.compress(raw, quality=9)
                else:
                    import gzip
                    body = gzip.compress(raw, compresslevel=9)
                self._static_cache.clear() if len(self._static_cache) > 12 else None
                self._static_cache[key] = body
            self.send_header('Content-Encoding', encoding)
        self.send_header('Content-Length', str(len(body) if body is not None else stat.st_size))
        self.end_headers()
        if self.command == 'GET':
            if body is not None:
                self.wfile.write(body)
            else:
                with path.open('rb') as f:
                    self.copyfile(f, self.wfile)
        return True

    def _response_status(self) -> int:
        return self._last_status

    def send_response(self, code, message=None):
        self._last_status = code
        super().send_response(code, message)

    def do_OPTIONS(self):
        if not self.allowed_request():
            return
        self.send_response(204)
        self.end_headers()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'app' / 'build' / 'web'), **kwargs)

    def from_loopback(self):
        return ipaddress.ip_address(self.client_address[0]).is_loopback

    def lan_host(self, host: str) -> bool:
        """--lan: a home-network or Tailscale address (192.168.x.x,
        name.local, name.ts.net), never a public name (DNS rebinding)."""
        name = urlsplit('//' + host).hostname or ''
        if name.endswith(('.local', '.ts.net')):
            return True
        try:
            ip = ipaddress.ip_address(name)
        except ValueError:
            return False
        return ip.is_private or ip.is_loopback or ip in ipaddress.ip_network('100.64.0.0/10')

    def public_request(self) -> bool:
        """--public-host: a request for the internet name (e.g. a Cloudflare
        Tunnel to api.willylinai.com). The tunnel connects from loopback, so
        these are never trusted as local."""
        name = (urlsplit('//' + self.headers.get('Host', '')).hostname or '').lower()
        return name in getattr(self.server, 'public_hosts', set())

    def within_rate(self, path: str) -> bool:
        """The read-only dictionary (/api/lexicon, images, audio) needs no key so a
        store build can update its word list; a per-client limit stops bulk
        downloads. Only the public name is limited (the LAN and loopback aren't)."""
        if path.startswith('/api/decks/'):
            path = '/api/decks'
        for prefix in ('/api/account', '/api/shares'):
            if path.startswith(prefix + '/'):
                path = prefix
        if not self.public_request() or path not in RATE_LIMITS:
            return True
        # The Cloudflare tunnel connects from loopback; the real client is in this header.
        client = self.headers.get('CF-Connecting-IP') or self.client_address[0]
        limit = RATE_LIMITS[path]
        now = time.monotonic()
        with RATE_LOCK:
            hits = RATE_HITS.setdefault((path, client), collections.deque())
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= limit:
                self.send_response(429)
                self.send_header('Retry-After', '30')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return False
            hits.append(now)
        return True

    def key_ok(self) -> bool:
        """--lan / --public-host: photo recognition, missing-word reports and the
        health check from another device need the tagger's X-API-Key, so the LAN
        or the internet can't use the GPU freely. The dictionary is public read-only."""
        if not self.public_request() and (
                not getattr(self.server, 'lan', False) or self.from_loopback()):
            return True
        try:
            key = os.environ.get('TAGGER_API_KEY', '').strip() or                 (ROOT / 'tagger' / '.api_key').read_text().strip()
        except OSError:
            return False
        return bool(key) and secrets.compare_digest(self.headers.get('X-API-Key', ''), key)

    def allowed_request(self):
        # Loopback binding plus Host/Origin checks prevent DNS rebinding and
        # unrelated websites from reading the local database through this server.
        # --lan (testing on a Mac / iPhone at home): also home-network peers
        # and hosts; everything else is still refused.
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        lan = getattr(self.server, 'lan', False)
        if lan:
            peer = ipaddress.ip_address(self.client_address[0])
            if not (peer.is_private or peer.is_loopback
                    or peer in ipaddress.ip_network('100.64.0.0/10')):
                self.send_error(403)
                return False
        if host not in allowed and not (lan and self.lan_host(host)) and not self.public_request():
            self.send_error(403)
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://{host}', f'https://{host}'):
            # flutter run -d chrome uses a random localhost port; allow that
            # loopback origin so DictionarySync can call this server directly.
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'}:
                self.send_error(403)
                return False
            self._cors_origin = origin
        else:
            self._cors_origin = None
        return True

    def _send_cors(self):
        origin = getattr(self, '_cors_origin', None)
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, If-None-Match, Authorization')
            self.send_header('Access-Control-Expose-Headers', 'ETag')
            self.send_header('Access-Control-Allow-Private-Network', 'true')

    def proxy_tagger(self, body=None):
        try:
            key = os.environ.get('TAGGER_API_KEY', '').strip()
            if not key:
                key = (ROOT / 'tagger' / '.api_key').read_text().strip()
            request = Request('http://127.0.0.1:8765' + self.path, data=body,
                              headers={'X-API-Key': key,
                                       'Content-Type': self.headers.get('Content-Type', 'image/jpeg')})
            try:
                upstream = urlopen(request, timeout=115)
            except HTTPError as error:
                upstream = error
            with upstream:
                status = upstream.code
                data = upstream.read()
        except (OSError, URLError) as error:
            reason = getattr(error, 'reason', error)
            timed_out = isinstance(reason, TimeoutError)
            status = 504 if timed_out else 502
            data = json.dumps({
                'error': ('照片辨識逾時，請稍後重試' if timed_out else
                          '照片辨識服務尚未啟動，請稍後重試'),
                'code': 'tagger_timeout' if timed_out else 'tagger_unavailable',
            }, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def record_missing(self, body: bytes):
        """Words the app's dictionary pack lacks (spec section 7: 缺詞條) or
        has without native text, saved for the admin to fill. Only these two
        request tables are written; personal learning data never leaves the
        browser."""
        try:
            items = json.loads(body.decode('utf-8')).get('requests', [])
            if not isinstance(items, list) or len(items) > 500:
                raise ValueError
        except (ValueError, AttributeError, UnicodeDecodeError):
            self.send_error(400)
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app import models as m
        from app.text import normalize_lemma
        saved = 0
        with db.session_scope() as session:
            for it in items:
                if not isinstance(it, dict):
                    continue
                target = str(it.get('target') or 'en')
                if target not in catalog.LANGUAGES:
                    continue
                if it.get('kind') == 'missing_lexeme' and str(it.get('lemma') or '').strip():
                    session.execute(pg_insert(m.MissingLexemeRequest).values(
                        target_language=target,
                        lemma=normalize_lemma(str(it['lemma'])[:128], target),
                        pos=(str(it.get('pos') or '') or None) and str(it['pos'])[:16],
                    ).on_conflict_do_nothing())
                    saved += 1
                elif it.get('kind') == 'missing_localization' and isinstance(it.get('lexeme_id'), int):
                    native = str(it.get('native') or 'zh-TW')
                    if native not in catalog.LANGUAGES or session.get(m.Lexeme, it['lexeme_id']) is None:
                        continue
                    session.execute(pg_insert(m.MissingLocalizationRequest).values(
                        lexeme_id=it['lexeme_id'], native_language=native,
                        field=str(it.get('field') or 'native_definition')[:48],
                    ).on_conflict_do_nothing())
                    saved += 1
        data = json.dumps({'saved': saved}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    ISSUES_PATH = re.compile(r'^/api/issues(/\d+)?$')

    def proxy_issues(self, method: str):
        """問題回報 for the Mac / iPhone session (owner, 2026-10-18): GET/POST/PUT
        /api/issues[/id] go to the admin API through the board proxy (5173,
        which adds the admin key). From the internet the tagger's X-API-Key
        is required, like tagging."""
        if not self.key_ok():
            self.send_error(401, 'X-API-Key required from another device')
            return
        try:
            length = int(self.headers.get('Content-Length', '0') or 0)
        except ValueError:
            self.send_error(400)
            return
        if length > 256 * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else None
        request = Request('http://127.0.0.1:5173' + self.path, data=body, method=method,
                          headers={'Content-Type': 'application/json'})
        try:
            upstream = urlopen(request, timeout=30)
        except HTTPError as error:
            upstream = error
        except (OSError, URLError):
            self.send_error(502, 'Issue list unavailable')
            return
        with upstream:
            status, data = upstream.code, upstream.read()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_PUT(self):
        if not self.allowed_request():
            return
        if not self.ISSUES_PATH.match(urlsplit(self.path).path):
            self.send_error(404)
            return
        self.proxy_issues('PUT')

    def do_POST(self):
        if not self.allowed_request():
            return
        path = urlsplit(self.path).path
        if self.ISSUES_PATH.match(path):
            self.proxy_issues('POST')
            return
        if path.startswith(('/api/account/', '/api/shares')):
            self.handle_account('POST', path)
            return
        if path not in ('/tag', '/api/missing'):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self.send_error(400)
            return
        if not 0 < length <= 20 * 1024 * 1024:
            self.send_error(413)
            return
        if not self.key_ok():
            self.send_error(401, 'X-API-Key required from another device')
            return
        if path == '/api/missing':
            if length > 256 * 1024:
                self.send_error(413)
                return
            self.record_missing(self.rfile.read(length))
            return
        self.proxy_tagger(self.rfile.read(length))

    def send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_account(self, method: str, path: str) -> None:
        """Accounts and sharing (card #324): bearer token from the app's Keychain,
        JSON bodies (photos: raw bytes). All logic lives in app/accounts.py."""
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = -1
        if not 0 <= length <= accounts.PHOTO_MAX_BYTES + 1:
            self.send_json(413, {'detail': 'too large'})
            return
        raw = self.rfile.read(length) if length else b''
        token = (self.headers.get('Authorization') or '').removeprefix('Bearer ').strip() or None
        parts = path.strip('/').split('/')[1:]   # after "api"
        try:
            with db.session_scope() as s:
                result = self.run_account(s, method, parts, raw, token)
        except accounts.AccountError as e:
            self.send_json(e.status, {'detail': e.message})
            return
        except (ValueError, KeyError, TypeError):
            self.send_json(400, {'detail': 'bad request'})
            return
        self.send_json(200, result)

    @staticmethod
    def run_account(s, method, parts, raw, token) -> dict:
        body = {} if parts[-1:] == ['photo'] or not raw else json.loads(raw)
        area, rest = parts[0], parts[1:]
        if area == 'account':
            if method == 'POST' and rest == ['register']:
                user, tok = accounts.register_email(s, body['email'], body['password'], body.get('nickname'),
                                                    body.get('native_lang'), body.get('level'))
                return {'token': tok, 'user': accounts.profile(user)}
            if method == 'POST' and rest == ['login']:
                user, tok = accounts.login_email(s, body['email'], body['password'])
                return {'token': tok, 'user': accounts.profile(user)}
            if method == 'POST' and rest == ['apple']:
                user, tok = accounts.login_apple(s, body['identity_token'], body.get('nickname'),
                                                 body.get('native_lang'), body.get('level'))
                return {'token': tok, 'user': accounts.profile(user)}
            user = accounts.user_from_token(s, token)
            if method == 'GET' and rest == ['me']:
                return accounts.profile(user)
            if method == 'POST' and rest == ['profile']:
                return accounts.update_profile(s, user, body.get('nickname'), body.get('native_lang'), body.get('level'))
            if method == 'POST' and rest == ['logout']:
                accounts.logout(s, token)
                return {'ok': True}
            if method == 'POST' and rest == ['delete']:
                accounts.delete_account(s, user)
                return {'ok': True}
        elif area == 'shares':
            user = accounts.user_from_token(s, token)
            if method == 'GET' and rest == ['mine']:
                return accounts.my_shares(s, user)
            if method == 'POST' and rest == []:
                return accounts.share_deck(s, user, kind=body['kind'], title=body.get('title'), cefr=body.get('cefr'),
                                           topic=body.get('topic'), description=body.get('description'),
                                           words=body.get('words'), photos=body.get('photos'),
                                           acknowledged_privacy=bool(body.get('acknowledged_privacy')))
            if method == 'POST' and rest == ['photo']:
                return {'asset_id': accounts.upload_photo(s, user, raw)}
            if method == 'POST' and len(rest) == 2:
                slug, action = rest
                if action == 'withdraw':
                    accounts.withdraw(s, user, slug)
                    return {'ok': True}
                if action == 'report':
                    accounts.report_deck(s, user, slug, body.get('reason'))
                    return {'ok': True}
                if action == 'block':
                    accounts.block_author(s, user, slug)
                    return {'ok': True}
        raise accounts.AccountError(404, 'not found')

    def send_decks(self, slug: str, target: str | None = None, native: str | None = None) -> None:
        """卡片集 (card #323): the published decks, read-only and keyless like
        the dictionary; one deck carries everything the app downloads."""
        token = (self.headers.get('Authorization') or '').removeprefix('Bearer ').strip() or None
        with db.session_scope() as session:
            viewer = None
            if token:
                try:
                    viewer = accounts.user_from_token(session, token)
                except accounts.AccountError:
                    pass
            data = decks.public_deck(session, slug) if slug else accounts.public_list(session, viewer, target, native)
            if data is not None and slug:
                accounts.count_download(session, slug)
        if data is None:
            self.send_error(404)
            return
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'private, no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_audio(self, path, head_only=False):
        """Serve a recording with byte ranges: iOS AVPlayer refuses sources that answer 200 to Range."""
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers.get('Range', '').strip())
        if match and (match[1] or match[2]):
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]), size - 1) if match[2] else size - 1
            else:  # suffix range: last N bytes
                start, end = max(size - int(match[2]), 0), size - 1
            if start >= size or start > end:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.send_header('Accept-Ranges', 'bytes')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        if head_only:
            return
        with path.open('rb') as audio:
            audio.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = audio.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_HEAD(self):
        url = urlsplit(self.path)
        if url.path == '/api/audio':
            self.do_GET(head_only=True)
        else:
            super().do_HEAD()

    def do_GET(self, head_only=False):
        if not self.allowed_request():
            return
        url = urlsplit(self.path)
        if self.ISSUES_PATH.match(url.path):
            self.proxy_issues('GET')
            return
        if not self.within_rate(url.path):
            return
        if url.path == '/api/image':
            from app import models as m
            try:
                asset_id = int(parse_qs(url.query).get('id', [''])[0])
            except ValueError:
                self.send_error(400)
                return
            with db.SessionLocal() as session:
                asset = session.get(m.ImageAsset, asset_id)
                path = (config.MEDIA / (asset.path or '')).resolve() if asset else None
                if (not asset or asset.status != 'ready' or not path
                        or not path.is_relative_to(config.MEDIA.resolve() / 'images')
                        or not path.is_file()
                        or path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'}):
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(path.stat().st_size))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                with path.open('rb') as image_file:
                    self.copyfile(image_file, self.wfile)
            return
        if url.path.startswith(('/api/account/', '/api/shares/')):
            self.handle_account('GET', url.path)
            return
        if url.path == '/api/decks' or url.path.startswith('/api/decks/'):
            self.send_decks(url.path[len('/api/decks'):].strip('/'),
                            (parse_qs(url.query).get('target', [''])[0] or None),
                            (parse_qs(url.query).get('native', [''])[0] or None))
            return
        if url.path in ('/privacy', '/privacy.html'):
            body = (ROOT / 'docs' / 'privacy.html').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if url.path == '/health' and not self.key_ok():
            self.send_error(401, 'X-API-Key required from another device')
            return
        if url.path == '/health':
            self.proxy_tagger()
            return
        if url.path == '/api/audio':
            relative = parse_qs(url.query).get('path', [''])[0]
            media = config.MEDIA.resolve()
            path = (media / relative).resolve()
            if (not path.is_relative_to(media / 'audio') or not path.is_file()
                    or path.suffix.lower() not in {'.mp3', '.wav', '.ogg', '.opus', '.m4a', '.flac'}):
                self.send_error(404)
                return
            self.send_audio(path, head_only)
            return
        if url.path != '/api/lexicon':
            if not self.send_static(url.path):
                return super().do_GET()
            return
        query = parse_qs(url.query)
        try:
            snapshot = http_snapshot(query.get('target', ['en'])[0], query.get('native', ['zh-TW'])[0])
        except ValueError:
            self.send_error(400, 'Unsupported language pair')
            return
        except Warming:
            # No pack on disk at all: answer at once rather than after 100 s (524).
            self.send_response(503)
            self.send_header('Retry-After', '60')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        except Exception:
            logging.exception('Dictionary snapshot unavailable')
            self.send_error(503, 'Dictionary temporarily unavailable')
            return
        unchanged = matches_etag(self.headers.get('If-None-Match', ''), snapshot.etag)
        # format=sqlite (card #428): phones take the slim pack as one SQLite
        # file, or a JSON delta when they hold the previous version.
        fmt = 'sqlite' if query.get('format', ['json'])[0] == 'sqlite' else 'json'
        body, ctype, gz = b'', 'application/json; charset=utf-8', False
        status = 304 if unchanged else 200
        if not unchanged:
            try:
                body, ctype, gz = snapshot.respond(
                    query.get('since', [None])[0],
                    accepts_gzip(self.headers.get('Accept-Encoding', '')), fmt)
            except Exception:
                logging.exception('Dictionary representation unavailable')
                self.send_error(503, 'Dictionary temporarily unavailable')
                return
        self.send_response(status)
        self.send_header('ETag', snapshot.etag)
        self.send_header('Cache-Control', 'private, no-cache')
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('Content-Type', ctype)
        self.send_header('X-Content-Type-Options', 'nosniff')
        if not unchanged:
            if gz:
                self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if not unchanged:
            self.wfile.write(body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8123)
    parser.add_argument('--warm-only', action='store_true',
                        help='prepare the default durable snapshot without starting any service')
    parser.add_argument('--lan', action='store_true',
                        help='also serve devices on the home network / Tailscale '
                             '(testing on a Mac or iPhone); photo recognition then needs X-API-Key')
    parser.add_argument('--public-host', action='append', default=[],
                        help='internet name served through a tunnel (e.g. api.willylinai.com); '
                             'repeatable, or PUBLIC_HOSTS=a,b. Tagging needs X-API-Key; the read-only dictionary is open but rate-limited')
    args = parser.parse_args()
    if args.warm_only:
        snapshot = http_snapshot('en', 'zh-TW', wait=True)
        print(f'Dictionary ready: {len(snapshot.body)} bytes, gzip {len(snapshot.gzip)} bytes')
        sys.exit(0)
    from start_services import ensure_studio
    try:
        ensure_studio()
    except (OSError, RuntimeError) as error:
        logging.warning('Card studio could not start: %s', error)
    server = ThreadingHTTPServer(('0.0.0.0' if args.lan else '127.0.0.1', args.port), Handler)
    server.lan = args.lan
    # The owner's internet name is always served (card #477: a restart without the flag answers 403).
    server.public_hosts = {'api.willylinai.com'} | {h.strip().lower() for h in
                           args.public_host + os.environ.get('PUBLIC_HOSTS', '').split(',') if h.strip()}
    threading.Thread(target=warm_snapshots, daemon=True, name='dictionary-warm').start()
    server.serve_forever()
