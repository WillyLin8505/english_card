"""連線 QR code 端點 (card #758): local only, key never in the body, fake key."""

import json

import pytest
from fastapi.testclient import TestClient

from app import connect_qr
from app.main import app

H = {"X-API-Key": "test-key"}
FAKE = "fake-tagger-key-123"


@pytest.fixture
def client(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "API_KEY", "test-key")
    monkeypatch.setattr(connect_qr, "read_tagger_key", lambda: FAKE)
    return TestClient(app, client=("127.0.0.1", 50000))


def test_local_gets_png_no_store(client):
    r = client.get("/api/admin/connect-qr.png", headers=H)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n" and FAKE.encode() not in r.content


def test_payload_format():
    assert json.loads(connect_qr_payload()) == {"v": 1, "taggingUrl": "https://x/tag", "apiKey": FAKE}


def connect_qr_payload():
    import sys
    sys.path.insert(0, str(connect_qr.REPO / "lexicon" / "tools"))
    from make_connect_qr import build_payload
    return build_payload("https://x/tag", FAKE)


@pytest.mark.parametrize("headers", [
    {"X-Forwarded-For": "203.0.113.9"},
    {"X-Forwarded-For": "127.0.0.1, 203.0.113.9"},
    {"Cf-Connecting-Ip": "127.0.0.1"},
    {"Cf-Ray": "abc"},
    {"X-Real-Ip": "198.51.100.2"},
])
def test_external_forwarded_refused(client, headers):
    for path in ("/api/admin/connect-qr.png", "/api/admin/connect-qr/info"):
        r = client.get(path, headers={**H, **headers})
        assert r.status_code == 403 and FAKE not in r.text


def test_proxy_local_forward_ok(client):
    assert client.get("/api/admin/connect-qr.png", headers={**H, "X-Forwarded-For": "::1"}).status_code == 200


def test_remote_peer_refused(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "API_KEY", "test-key")
    monkeypatch.setattr(connect_qr, "read_tagger_key", lambda: FAKE)
    remote = TestClient(app, client=("203.0.113.9", 1234))
    assert remote.get("/api/admin/connect-qr.png", headers=H).status_code == 403


def test_info_has_no_key_and_bad_url(client):
    r = client.get("/api/admin/connect-qr/info", headers=H)
    assert r.status_code == 200 and FAKE not in r.text and r.json()["has_key"] is True
    assert client.get("/api/admin/connect-qr.png?url=ftp://x", headers=H).status_code == 400
