"""Read-only image failure/retry fixture for the real Flutter App. No DB access."""
import json
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
ROOT = Path(__file__).resolve().parents[2]
FLAGS = ROOT / "card_preview/data/app-photo-fixture-flags.json"
PACK = {"target_language": "en", "native_language": "zh-TW", "created_at": "photo-fixture-20261014",
        "catalog_version": 1, "lexemes": [{"id": 1, "lemma": "apple", "normalized": "apple",
        "pos": "noun", "status": "full", "cefr": "A1", "senses": [{"id": 11, "definition": "fruit", "native": "蘋果"}]}],
        "catalog_images": [{"id": 1, "url": "/fixture-photo.jpg", "status": "ready", "width": 600, "height": 400,
         "tags": [{"lexeme_id": 1, "sense_id": 11, "review_status": "approved"}],
         "labels": [{"lexeme_id": 1, "word": "apple", "point": [.5, .5]}]}]}
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "app/build/web"), **kwargs)
    def respond(self, body, kind, status=200):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/lexicon":
            return self.respond(json.dumps(PACK, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        if path == "/fixture-photo.jpg":
            flags = json.loads(FLAGS.read_text())
            time.sleep(flags.get("delay_ms", 0) / 1000)
            if flags.get("mode") == "fail":
                return self.respond(b"test image unavailable", "text/plain", 503)
            return self.respond((ROOT / "app/assets/sample/photo_kitchen.jpg").read_bytes(), "image/jpeg")
        super().do_GET()
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.respond(b"{}", "application/json")
if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8131), Handler).serve_forever()
