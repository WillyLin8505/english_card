"""問題回報 #380: Openverse client credentials -> bearer token on api.openverse.org."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from app import config, images, openverse_auth

OV = "https://api.openverse.org/v1/images/?q=cat"
PIC = "https://live.staticflickr.com/1/2.jpg"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(config, "OPENVERSE_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "OPENVERSE_CLIENT_SECRET", "secret")
    asked = []

    def urlopen(request, timeout):
        asked.append(request)
        return _Resp(json.dumps({"access_token": f"tok{len(asked)}", "expires_in": 43200}).encode())

    monkeypatch.setattr(openverse_auth.urllib.request, "urlopen", urlopen)
    return asked


def _opener(monkeypatch, replies=None):
    seen = []
    replies = list(replies or [])

    class Opener:
        def open(self, request, timeout):
            seen.append((request.full_url, request.get_header("Authorization"),
                         request.unredirected_hdrs.get("Authorization")))
            if replies:
                code = replies.pop(0)
                raise urllib.error.HTTPError(request.full_url, code, "x", {}, io.BytesIO(b""))
            return _Resp(b"{}")

    monkeypatch.setattr(images.urllib.request, "build_opener", lambda *a, **k: Opener())
    return seen


def test_no_credentials_stays_anonymous(monkeypatch):
    seen = _opener(monkeypatch)
    images.fetch(OV, validate=images.check_openverse_api_url)
    assert openverse_auth.token() is None
    assert seen[0][1] is None


def test_token_is_requested_once_and_cached(keyed, monkeypatch):
    seen = _opener(monkeypatch)
    images.fetch(OV, validate=images.check_openverse_api_url)
    images.fetch(OV, validate=images.check_openverse_api_url)
    assert len(keyed) == 1
    req = keyed[0]
    assert req.full_url == openverse_auth.TOKEN_URL and req.get_method() == "POST"
    body = dict(p.split("=") for p in req.data.decode().split("&"))
    assert body == {"grant_type": "client_credentials", "client_id": "cid", "client_secret": "secret"}
    # Sent as an unredirected header: never forwarded to a redirect target.
    assert [s[1:] for s in seen] == [("Bearer tok1", "Bearer tok1")] * 2


def test_token_renewed_before_it_expires(keyed, monkeypatch):
    assert openverse_auth.token() == "tok1"
    openverse_auth._cache["expires_at"] = openverse_auth.time.time() + 60  # inside the margin
    assert openverse_auth.token() == "tok2"


def test_picture_downloads_never_get_the_token(keyed, monkeypatch):
    seen = _opener(monkeypatch)
    images.fetch(PIC, validate=images.check_public_image_url)
    assert seen[0][1] is None and keyed == []


def test_token_failure_falls_back_to_anonymous_with_cooldown(monkeypatch):
    monkeypatch.setattr(config, "OPENVERSE_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "OPENVERSE_CLIENT_SECRET", "bad")
    calls = []

    def urlopen(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 401, "bad client", {}, io.BytesIO(b""))

    monkeypatch.setattr(openverse_auth.urllib.request, "urlopen", urlopen)
    seen = _opener(monkeypatch)
    images.fetch(OV, validate=images.check_openverse_api_url)
    images.fetch(OV, validate=images.check_openverse_api_url)
    assert len(calls) == 1, "no token request storm during the cooldown"
    assert [s[1] for s in seen] == [None, None]


def test_401_on_a_request_renews_the_token_once(keyed, monkeypatch):
    seen = _opener(monkeypatch, replies=[401])
    images.fetch(OV, validate=images.check_openverse_api_url)
    assert [s[1] for s in seen] == ["Bearer tok1", "Bearer tok2"]

    seen = _opener(monkeypatch, replies=[401, 401])
    with pytest.raises(urllib.error.HTTPError):
        images.fetch(OV, validate=images.check_openverse_api_url)
    assert len(seen) == 2, "only one renewal per request"
