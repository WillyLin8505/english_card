"""Local app + read-only live dictionary. Run: python serve_app.py --port 8123.

Database credentials stay in the Python process. The browser receives only
dictionary content, never admin credentials. Personal learning stays local.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import logging
import mimetypes
import os
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
from app import app_pack, catalog, config, db, exporter
from lexicon_transport import SnapshotStore, accepts_gzip, matches_etag

_lock = threading.Lock()
_cache = {}


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


def http_snapshot(target, native):
    if target not in catalog.LANGUAGES or native not in catalog.LANGUAGES or target == native:
        raise ValueError('Unsupported language pair')
    global _http_snapshots
    with _http_snapshots_lock:
        if _http_snapshots is None:
            _http_snapshots = SnapshotStore(live_pack, snapshot_directory())
    return _http_snapshots.get(target, native)


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
        hit = listed.get(word.normalized)
        return 'cefr-j' if hit and band in hit[1].values() else 'estimate'
    tags = {}
    for binding in session.scalars(select(m.SenseImage).order_by(m.SenseImage.id)):
        word_id = sense_words.get(binding.sense_id)
        if binding.review_status == 'approved' and word_id in full_words:
            tags.setdefault(binding.image_asset_id, []).append({
                'lexeme_id': word_id, 'sense_id': binding.sense_id,
                'review_status': binding.review_status, 'origin': 'binding'})
    # The vision model supplies positions, but only approved bindings decide
    # which labels are visible. This prevents foreign, rejected and unrelated
    # suggestions from appearing in the app.
    images = []
    for asset in session.scalars(select(m.ImageAsset).order_by(m.ImageAsset.id)):
        if asset.id not in tags:
            continue
        positioned = {}
        model_cefr = {}
        for item in asset.tags or []:
            name = str(item.get('word', '')).strip().lower()
            if not name:
                continue
            if item.get('point') and name not in positioned:
                positioned[name] = item
            band = str(item.get('cefr') or item.get('modelLevel') or '').strip().upper()
            if band in levels:
                model_cefr[name] = band
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
            item = positioned.get(word.normalized) or {}
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
                    signatures.append(session.execute(text(
                        f"SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' "
                        f"ORDER BY row_to_json(t)::text), '')) FROM {table} t"
                    )).scalar_one())
                fingerprint = tuple(signatures)
                if cached and cached[3] == fingerprint:
                    _cache[(target, native)] = (time.monotonic(), cached[1], cached[2], fingerprint)
                    return cached[1:3]
                exporter._build(session, path, target, native, None, False, Path(folder))
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
            app_pack.rank_usages(pack['lexemes'])
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

    def key_ok(self) -> bool:
        """--lan: photo recognition / missing-word reports from another device
        need the tagger's X-API-Key, so the LAN can't use the GPU freely."""
        if not getattr(self.server, 'lan', False) or self.from_loopback():
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
        if host not in allowed and not (lan and self.lan_host(host)):
            self.send_error(403)
            return False
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{host}':
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
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, If-None-Match')
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

    def do_POST(self):
        if not self.allowed_request():
            return
        path = urlsplit(self.path).path
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

    def do_GET(self):
        if not self.allowed_request():
            return
        url = urlsplit(self.path)
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
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(path.stat().st_size))
            self.end_headers()
            with path.open('rb') as audio:
                self.copyfile(audio, self.wfile)
            return
        if url.path != '/api/lexicon':
            return super().do_GET()
        query = parse_qs(url.query)
        try:
            snapshot = http_snapshot(query.get('target', ['en'])[0], query.get('native', ['zh-TW'])[0])
        except ValueError:
            self.send_error(400, 'Unsupported language pair')
            return
        except Exception:
            logging.exception('Dictionary snapshot unavailable')
            self.send_error(503, 'Dictionary temporarily unavailable')
            return
        unchanged = matches_etag(self.headers.get('If-None-Match', ''), snapshot.etag)
        self.send_response(304 if unchanged else 200)
        self.send_header('ETag', snapshot.etag)
        self.send_header('Cache-Control', 'private, no-cache')
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if not unchanged:
            gz = accepts_gzip(self.headers.get('Accept-Encoding', ''))
            body = snapshot.representation(query.get('since', [None])[0], gz)
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
    args = parser.parse_args()
    if args.warm_only:
        snapshot = http_snapshot('en', 'zh-TW')
        print(f'Dictionary ready: {len(snapshot.body)} bytes, gzip {len(snapshot.gzip)} bytes')
        sys.exit(0)
    from start_services import ensure_studio
    try:
        ensure_studio()
    except (OSError, RuntimeError) as error:
        logging.warning('Card studio could not start: %s', error)
    server = ThreadingHTTPServer(('0.0.0.0' if args.lan else '127.0.0.1', args.port), Handler)
    server.lan = args.lan
    server.serve_forever()
