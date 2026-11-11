"""#1076 / 問題回報 #1591: picture and audio requests must not stall /health or the App.

Runs the real serve_app Handler on a local port. Photo resizes are slowed down
to 1.5 s each and the tagger is 'busy'; /health and audio must still answer
within a second, and no photo request may hold a DB connection while it works.
"""

import threading
import time
import types
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from PIL import Image

import serve_app
from app import config


@contextmanager
def running_server():
    server = serve_app.AppServer(("127.0.0.1", 0), serve_app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def fetch(url):
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, b""
    return status, body, time.monotonic() - started


def test_listen_backlog_is_larger_than_the_default():
    assert serve_app.AppServer.request_queue_size >= 64


def test_photo_request_gives_the_db_connection_back_before_resizing(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "p.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    open_sessions = []
    seen_during_resize = []

    class FakeSession:
        def __init__(self):
            open_sessions.append(1)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            open_sessions.pop()
            return False

        def get(self, model, asset_id):
            return types.SimpleNamespace(path="images/p.jpg", status="ready")

    def spy_thumbnail(asset_id, source, width):
        seen_during_resize.append(len(open_sessions))
        return None

    monkeypatch.setattr(serve_app.db, "SessionLocal", FakeSession)
    monkeypatch.setattr(serve_app.Handler, "thumbnail_path", staticmethod(spy_thumbnail))
    with running_server() as base:
        status, body, _ = fetch(f"{base}/api/image?id=7&w=1024")
    assert status == 200 and body == b"\xff\xd8\xff\xd9"
    assert seen_during_resize == [0]


def test_health_and_audio_answer_within_a_second_while_photos_resize(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    (tmp_path / "audio" / "en").mkdir(parents=True)
    (tmp_path / "audio" / "en" / "a.mp3").write_bytes(b"ID3" + b"0" * 1000)
    for asset_id in range(1, 11):
        (tmp_path / "images" / f"p{asset_id}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    monkeypatch.setattr(config, "MEDIA", tmp_path)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, model, asset_id):
            return types.SimpleNamespace(path=f"images/p{asset_id}.jpg", status="ready")

    def slow_resize(*args, **kwargs):
        # Stand-in for a 1.5 s photo decode/resize (PIL raises -> original file served).
        time.sleep(1.5)
        raise OSError("slow resize")

    def busy_tagger(request, timeout):
        # The tagger holds the connection; the proxy must give up at its own timeout.
        time.sleep(timeout)
        raise TimeoutError("tagger busy")

    monkeypatch.setattr(serve_app.db, "SessionLocal", FakeSession)
    monkeypatch.setattr(Image, "open", slow_resize)
    monkeypatch.setattr(serve_app, "urlopen", busy_tagger)
    with running_server() as base:
        with ThreadPoolExecutor(max_workers=10) as pool:
            photos = [pool.submit(fetch, f"{base}/api/image?id={i}&w=1024") for i in range(1, 11)]
            time.sleep(0.3)  # let the photo requests reach the resize step first
            health_status, _, health_s = fetch(f"{base}/health")
            audio_status, audio_body, audio_s = fetch(f"{base}/api/audio?path=audio/en/a.mp3")
            photo_results = [f.result() for f in photos]
    assert health_s < 1.0, health_s
    assert audio_status == 200 and len(audio_body) == 1003 and audio_s < 1.0, audio_s
    assert all(status == 200 for status, _, _ in photo_results)
