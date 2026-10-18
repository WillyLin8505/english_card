"""Isolated browser fixture for the real Flutter matching UI; no database writes."""
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
WORDS = [(1, "hot", "熱"), (2, "cold", "冷"), (3, "warm", "溫暖")]
PACK = {"target_language": "en", "native_language": "zh-TW",
        "catalog_version": 1, "created_at": "matching-fixture-20261014", "catalog_images": [], "lexemes": [
    {"id": ident, "lemma": word, "normalized": word, "pos": "adj", "status": "full", "cefr": "A1",
     "senses": [{"id": ident * 10, "definition": word, "native": meaning}],
     "relations": [{"relation": "related", "word": other, "lexeme_id": oid,
                    "native": native, "cefr": "A1"}
                   for oid, other, native in sorted(WORDS, key=lambda item: item[0] != ident)]}
    for ident, word, meaning in WORDS]}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "app/build/web"), **kwargs)
    def do_GET(self):
        if urlsplit(self.path).path == "/api/lexicon":
            body = json.dumps(PACK, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8130), Handler).serve_forever()
