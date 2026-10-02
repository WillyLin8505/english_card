"""Independent localhost preview server. Run: python card_preview/server.py"""
import argparse
import json
import mimetypes
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from repository import Repository
from domain import KINDS, SECTIONS, RELATIONS, LIMITS, quality, prepare_exercise, validate_layout
from state import State

BASE = Path(__file__).resolve().parent


class PreviewService:
    def __init__(self, repo=None, state=None):
        self.repo = repo or Repository()
        self.state = state or State(BASE / 'data/preview.sqlite')
        self.token = secrets.token_urlsafe(32)

    def templates(self, target, native, template_id='default'):
        upstream = self.repo.templates(target, native)
        for item in upstream:
            try:
                validate_layout(item['draft'])
            except (ValueError, TypeError, KeyError):
                item['draft'] = None
            for version in item['versions']:
                try:
                    validate_layout(version['layout'])
                except (ValueError, TypeError, KeyError):
                    version['layout'] = None
        return {**self.state.templates(target, native, template_id), 'upstream': upstream}

    def card(self, id, target, native):
        word = self.repo.entry(id, target, native)
        word['missing'] = quality(word)
        word['issues'] = sorted((i for u in word['usages'] for i in self.state.issues(u['lexeme_id'], target, native)),
                                key=lambda i: i['id'], reverse=True)
        word['ready_for_export'] = False
        word['export_note'] = '預覽不核發匯出資格；交由正式匯出流程驗證'
        return word

    def exercise(self, word, kind, sense):
        if kind not in [k['id'] for k in KINDS]:
            raise ValueError('不支援的模板')
        bundle = None
        # Deterministic filename: never allow a user-supplied path to escape this folder.
        name = f'{word["id"]}-{sense}-{kind}-{word["native_language"]}.json'
        candidate = BASE / 'exercise-input' / name
        if candidate.exists() and candidate.stat().st_size <= 100_000:
            bundle = json.loads(candidate.read_text(encoding='utf-8'))
        if not bundle and kind in ('cloze', 'similar', 'photo_choice'):
            from domain import live_exercise
            return live_exercise(word, kind, sense)
        if not bundle and kind == 'drag':
            return self.repo.drag_exercise(word, sense)
        option_cards = {word['id']: word}
        if bundle:
            if not isinstance(bundle, dict) or not isinstance(bundle.get('options', []), list) or len(bundle.get('options', [])) > 5:
                raise ValueError('題目資料格式無效')
            for o in bundle.get('options', []):
                if not isinstance(o, dict) or type(o.get('lexeme_id')) is not int:
                    raise ValueError('題目選項需包含有效 lexeme_id')
                if o['lexeme_id'] not in option_cards:
                    try:
                        option_cards[o['lexeme_id']] = self.repo.card(o['lexeme_id'], word['language'], word['native_language'])
                    except LookupError:
                        pass
        return prepare_exercise(word, kind, sense, bundle, option_cards)


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send_json(self, body, code=200):
            data = json.dumps(body, ensure_ascii=False, default=str).encode('utf-8')
            self.send_bytes(data, 'application/json; charset=utf-8', code)

        def send_bytes(self, data, mime, code=200):
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'self' http://127.0.0.1:5173 http://localhost:5173 http://127.0.0.1:8770 http://localhost:8770; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.handle_request(False)

        def do_POST(self):
            self.handle_request(True)

        def handle_request(self, post):
            try:
                host = self.headers.get('Host', '')
                if host not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                    self.send_json({'error': '僅接受本機存取'}, 403)
                    return
                url = urlsplit(self.path)
                path = url.path
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                target, native = q.get('target', 'en'), q.get('native', 'zh-TW')
                import re
                if not all(re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?', v) for v in (target, native)):
                    raise ValueError('語言代碼無效')
                if post:
                    origin = self.headers.get('Origin')
                    if self.headers.get('X-Preview-Token') != service.token or (origin and origin != 'http://' + host):
                        self.send_json({'error': '請重新整理頁面後再操作'}, 403)
                        return
                    length = int(self.headers.get('Content-Length', 0))
                    if not 0 < length <= 100_000 or not self.headers.get('Content-Type', '').startswith('application/json'):
                        raise ValueError('請求內容過大或格式錯誤')
                    body = json.loads(self.rfile.read(length))
                    if path == '/api/templates/create':
                        result = service.state.create(target, native, body.get('name'), body.get('layout'))
                    elif path == '/api/templates/save':
                        result = service.state.save(target, native, body['layout'], False, q.get('template_id', 'default'))
                    elif path == '/api/templates/publish':
                        result = service.state.save(target, native, body['layout'], True, q.get('template_id', 'default'))
                    elif path == '/api/issues':
                        word = service.repo.entry(int(body['lexeme_id']), target, native)
                        valid_fields = {'layout', 'pos', 'senses', 'examples', 'pronunciation', 'sources', 'etymology'}
                        for group, prefix in [('senses', 'sense'), ('examples', 'example'), ('relations', 'relation'), ('forms', 'form'), ('audio', 'audio')]:
                            valid_fields.update(f'{prefix}:{x["id"]}' for x in word[group])
                        valid_fields.update(f'image:{i["sense_image_id"]}' for i in word['images'])
                        if body.get('field') not in valid_fields:
                            raise ValueError('問題欄位不屬於目前詞條')
                        if body.get('sense_id') is not None and body['sense_id'] not in [s['id'] for s in word['senses']]:
                            raise ValueError('義項不屬於目前詞條')
                        body.update(target_language=target, native_language=native)
                        result = service.state.add_issue(body)
                    else:
                        raise LookupError('找不到此操作')
                elif path == '/api/catalog':
                    result = {**service.repo.catalog(), 'token': service.token, 'kinds': KINDS, 'sections': SECTIONS, 'relations': RELATIONS, 'limits': LIMITS}
                elif path == '/api/words':
                    result = service.repo.words(target, native, q.get('q', '')[:200], max(0, int(q.get('offset', 0))), min(100, max(1, int(q.get('limit', 40)))), q.get('scope', 'all'))
                elif path == '/api/templates':
                    result = service.templates(target, native, q.get('template_id', 'default'))
                elif path.startswith('/api/card/'):
                    result = service.card(int(path.rsplit('/', 1)[1]), target, native)
                elif path.startswith('/api/exercise/'):
                    # Exercises must use the same merged, validated card as the
                    # preview.  Reading a raw POS lexeme here bypasses
                    # merge_usages(), including rejected-example filtering.
                    word = service.repo.entry(int(path.rsplit('/', 1)[1]), target, native)
                    result = service.exercise(word, q.get('kind', KINDS[0]['id']), int(q.get('sense', 0)))
                elif path.startswith('/api/media/'):
                    _, _, _, kind, id = path.split('/')
                    file = service.repo.media(kind, int(id))
                    self.send_bytes(file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                    return
                elif path in ('/', '/admin.html', '/app.js', '/style.css'):
                    file = BASE / 'static' / ('index.html' if path == '/' else path[1:])
                    self.send_bytes(file.read_bytes(), {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}[file.suffix])
                    return
                else:
                    raise LookupError('找不到頁面')
                self.send_json(result)
            except (ValueError, KeyError, TypeError) as error:
                self.send_json({'error': str(error)}, 400)
            except LookupError as error:
                self.send_json({'error': str(error)}, 404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                # Connection exceptions can contain DSNs. Never expose their message.
                print('Preview request failed:', type(error).__name__, file=sys.stderr)
                self.send_json({'error': '資料讀取暫時失敗，請確認 PostgreSQL 已啟動及資料表可用，再重新整理。'}, 503)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8772)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(PreviewService()))
    print(f'Card preview: http://127.0.0.1:{args.port}/ (lexicon read-only)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
