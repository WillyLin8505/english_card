"""Network access for adapters: disk cache, per-source rate limit,
timeout, exponential backoff with jitter, and a circuit breaker.

Responses are cached in raw-data/cache/<source>/ (the source's raw
records for this headword), so re-resolving under a new policy never has
to ask the source again. `refresh=True` bypasses the cache.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass

from .. import config

CACHE = config.RAW_DATA / "cache"

# Minimum seconds between requests per source (Datamuse asks for ≤ 100k/day;
# Kaikki and Tatoeba are volunteer-run — be gentle).
MIN_INTERVAL = defaultdict(lambda: 0.2, {"datamuse": 0.1, "kaikki": 0.25, "tatoeba": 0.5,
                                         "wikimedia": 0.3, "ai_translate": 0.0,
                                         # Commons answers 429 to quick anonymous API calls.
                                         "wikimedia_commons": 1.5})
BREAKER_FAILURES = 5
BREAKER_OPEN_S = 60


class SourceError(Exception):
    """A lookup failed. kind: timeout / http / network / parse / breaker / unavailable."""

    def __init__(self, kind: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


@dataclass
class Usage:
    requests: int = 0
    errors: int = 0
    cache_hits: int = 0
    ms_total: int = 0


_lock = threading.Lock()
_last: dict[str, float] = {}
_failures: dict[str, int] = defaultdict(int)
_open_until: dict[str, float] = {}
usage: dict[str, Usage] = defaultdict(Usage)


def take_usage() -> dict[str, Usage]:
    """Usage since the last call (flushed to api_usage by the caller)."""
    global usage
    with _lock:
        out, usage = usage, defaultdict(Usage)
    return out


def _safe(word: str) -> str:
    return re.sub(r"[^\w-]+", "_", word.lower(), flags=re.UNICODE).strip("_")[:60] or "_"


def cache_path(source: str, word: str, url: str):
    return CACHE / source / f"{_safe(word)}__{hashlib.sha1(url.encode()).hexdigest()[:12]}.json"


def _wait_turn(source: str):
    with _lock:
        until = _open_until.get(source, 0)
        if until > time.time():
            raise SourceError("breaker", f"{source} 暫停使用（連續失敗，{int(until - time.time())} 秒後再試）")
        wait = _last.get(source, 0) + MIN_INTERVAL[source] - time.time()
        _last[source] = max(time.time(), _last.get(source, 0) + MIN_INTERVAL[source])
    if wait > 0:
        time.sleep(wait)


def _result(source: str, ok: bool):
    with _lock:
        if ok:
            _failures[source] = 0
        else:
            _failures[source] += 1
            if _failures[source] >= BREAKER_FAILURES:
                _open_until[source] = time.time() + BREAKER_OPEN_S
                _failures[source] = 0


def get(source: str, word: str, url: str, *, timeout: float = 20, retries: int = 2,
        refresh: bool = False, lines: bool = False, headers: dict | None = None,
        cache: bool = True):
    """GET JSON (or JSON lines). Returns (data, status); 404 → (None, 404).
    Raises SourceError when the source can't be reached."""
    path = cache_path(source, word, url)
    if cache and path.exists() and not refresh:
        c = json.loads(path.read_text(encoding="utf-8"))
        with _lock:
            usage[source].cache_hits += 1
        return c["data"], c["status"]
    last_error: SourceError | None = None
    for attempt in range(retries + 1):
        _wait_turn(source)
        started = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT,
                                                       **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, body = r.status, r.read().decode("utf-8")
            data = ([json.loads(x) for x in body.splitlines() if x.strip()] if lines
                    else json.loads(body))
            _account(source, started, ok=True)
            if cache:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"url": url, "status": status, "data": data},
                                           ensure_ascii=False), encoding="utf-8")
            return data, status
        except urllib.error.HTTPError as e:
            if e.code == 404:
                _account(source, started, ok=True)
                if cache:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"url": url, "status": 404, "data": None}),
                                    encoding="utf-8")
                return None, 404
            _account(source, started, ok=False)
            last_error = SourceError("http", f"HTTP {e.code}", retryable=e.code in (429, 500, 502,
                                                                                    503, 504))
            if not last_error.retryable:
                raise last_error from e
            if e.code == 429 and attempt < retries:  # wait as long as the source asks
                try:
                    time.sleep(min(30.0, float(e.headers.get("Retry-After") or 5)))
                except ValueError:
                    time.sleep(5)
                continue
        except TimeoutError as e:
            _account(source, started, ok=False)
            last_error = SourceError("timeout", f"逾時（{timeout:g} 秒）")
        except urllib.error.URLError as e:
            _account(source, started, ok=False)
            kind = "timeout" if "timed out" in str(e.reason) else "network"
            last_error = SourceError(kind, f"{type(e.reason).__name__}: {e.reason}")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            _account(source, started, ok=False)
            raise SourceError("parse", f"回應不是 JSON：{e}", retryable=False) from e
        except OSError as e:
            _account(source, started, ok=False)
            last_error = SourceError("network", f"{type(e).__name__}: {e}")
        if attempt < retries:
            time.sleep(min(8.0, 0.8 * 2 ** attempt) + random.uniform(0, 0.5))  # backoff + jitter
    assert last_error is not None
    raise last_error


def _account(source: str, started: float, ok: bool):
    with _lock:
        u = usage[source]
        u.requests += 1
        u.ms_total += int((time.time() - started) * 1000)
        if not ok:
            u.errors += 1
    _result(source, ok)


def post_json(source: str, url: str, payload: dict, *, timeout: float = 60,
              headers: dict | None = None):
    _wait_turn(source)
    started = time.time()
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": config.USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        _account(source, started, ok=True)
        return data
    except urllib.error.HTTPError as e:
        _account(source, started, ok=False)
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", "")
        except (ValueError, OSError, AttributeError):
            pass
        if e.code in (404, 410):  # the endpoint is gone or switched off
            raise SourceError("unavailable", f"HTTP {e.code}：{detail or '服務不提供這個功能'}",
                              retryable=False) from e
        raise SourceError("http", f"HTTP {e.code}" + (f"：{detail}" if detail else "")) from e
    except TimeoutError as e:
        _account(source, started, ok=False)
        raise SourceError("timeout", f"逾時（{timeout:g} 秒）") from e
    except urllib.error.URLError as e:
        _account(source, started, ok=False)
        raise SourceError("unavailable", f"連不上：{e.reason}") from e


def download(source: str, url: str, dest, *, timeout: float = 60) -> tuple[int, str | None]:
    """Stream a file to [dest] (a temp path). Returns (bytes, content-type)."""
    _wait_turn(source)
    started = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as fh:
            size = 0
            while chunk := r.read(1 << 16):
                fh.write(chunk)
                size += len(chunk)
            ctype = r.headers.get("Content-Type")
        _account(source, started, ok=True)
        return size, ctype
    except urllib.error.HTTPError as e:
        _account(source, started, ok=False)
        raise SourceError("http", f"HTTP {e.code}", retryable=e.code >= 500) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _account(source, started, ok=False)
        raise SourceError("network", f"{type(e).__name__}: {e}") from e
