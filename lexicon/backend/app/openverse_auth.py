"""Openverse bearer token (問題回報 #380).

With LEXICON_OPENVERSE_CLIENT_ID / _SECRET set, `token()` trades them for an
access token at POST /v1/auth_tokens/token/ (client_credentials) and keeps it
in this process until shortly before it expires; `images.fetch` sends it as
`Authorization: Bearer` on api.openverse.org requests only (never on the
provider-hosted picture downloads, and not across redirects).  Without the
pair, or while the token endpoint fails, requests stay anonymous.

The token lives in memory only: it is a credential, so it is never written to
the gate state files or logs.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

log = logging.getLogger(__name__)

TOKEN_URL = "https://api.openverse.org/v1/auth_tokens/token/"
REFRESH_MARGIN_S = 300.0   # renew this long before the token expires
FAILURE_COOLDOWN_S = 600.0  # after a failed token request, stay anonymous this long

_lock = threading.Lock()
_cache = {"token": None, "expires_at": 0.0, "retry_at": 0.0}


def configured() -> bool:
    return bool(config.OPENVERSE_CLIENT_ID and config.OPENVERSE_CLIENT_SECRET)


def _request_token() -> tuple[str, float]:
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": config.OPENVERSE_CLIENT_ID,
        "client_secret": config.OPENVERSE_CLIENT_SECRET,
    }).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={
        "User-Agent": config.USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read(65536))
    token = data.get("access_token")
    if not token:
        raise ValueError("Openverse token 回應沒有 access_token")
    return token, float(data.get("expires_in") or 3600)


def token() -> str | None:
    """A valid access token, or None (no credentials / token request failed)."""
    if not configured():
        return None
    now = time.time()
    with _lock:
        if _cache["token"] and now < _cache["expires_at"] - REFRESH_MARGIN_S:
            return _cache["token"]
        if now < _cache["retry_at"]:
            return None
        try:
            tok, expires_in = _request_token()
        except (OSError, ValueError) as exc:  # URLError/HTTPError are OSErrors
            code = getattr(exc, "code", None)
            log.warning("Openverse token request failed (%s); anonymous for %.0f s",
                        code or type(exc).__name__, FAILURE_COOLDOWN_S)
            _cache.update(token=None, expires_at=0.0, retry_at=now + FAILURE_COOLDOWN_S)
            return None
        _cache.update(token=tok, expires_at=now + expires_in, retry_at=0.0)
        return tok


def invalidate() -> None:
    """Drop the cached token (Openverse answered 401 to it)."""
    with _lock:
        _cache.update(token=None, expires_at=0.0)
