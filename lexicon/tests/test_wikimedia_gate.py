"""問題回報 #339: one machine-wide request budget for Wikimedia hosts."""

from __future__ import annotations

import io
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

from app import wikimedia_gate as gate
from app.adapters import http

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def _http_error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://commons.wikimedia.org/x", code, "x", headers, io.BytesIO(b""))


def test_hosts():
    assert gate.is_wikimedia("https://commons.wikimedia.org/w/api.php?x")
    assert gate.is_wikimedia("https://upload.wikimedia.org/wikipedia/commons/a/ab/F.ogg")
    assert gate.is_wikimedia("https://www.wikidata.org/wiki/Special:EntityData/Q1.json")
    assert not gate.is_wikimedia("https://kaikki.org/dictionary/x.json")
    assert not gate.is_wikimedia("https://notwikimedia.org/")
    assert not gate.is_wikimedia("")


def test_slots_are_spaced(monkeypatch):
    monkeypatch.setattr(gate, "MIN_INTERVAL", 0.05)
    started = time.time()
    for _ in range(5):
        gate.wait_turn()
    assert time.time() - started >= 0.19


def test_slots_are_shared_across_processes(tmp_path):
    """Three processes, four requests each, 0.1 s interval: ≥ 1.1 s in total."""
    state = tmp_path / "gate.json"
    code = ("import os,time,sys; from app import wikimedia_gate as g; g.MIN_INTERVAL=0.1\n"
            "for _ in range(4): g.wait_turn(); print(time.time())")
    env = {**__import__("os").environ, "LEXICON_WIKIMEDIA_GATE": str(state)}
    procs = [subprocess.Popen([sys.executable, "-c", code], cwd=BACKEND, env=env,
                              stdout=subprocess.PIPE, text=True) for _ in range(3)]
    stamps = sorted(float(x) for p in procs for x in p.communicate(timeout=60)[0].split())
    assert len(stamps) == 12
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert min(gaps) >= 0.08, gaps


def test_429_pauses_everyone_and_widens_interval(monkeypatch):
    monkeypatch.setattr(gate, "BACKOFF_BASE", 10.0)
    pause = gate.penalize("3")
    assert 9 < pause <= 10  # backoff beats a shorter Retry-After
    st = gate.status()
    assert st["strikes"] == 1 and st["interval"] == 2 * gate.MIN_INTERVAL
    gate.penalize(None)  # a reply to a request sent before the pause: no escalation
    assert gate.status()["strikes"] == 1
    assert gate.penalize("120") > 100  # a longer Retry-After is honoured


def test_strikes_decay_after_calm(monkeypatch):
    gate.penalize()
    gate.succeeded()
    assert gate.status()["strikes"] == 1  # too soon
    monkeypatch.setattr(gate, "CALM_S", -1.0)
    gate.succeeded()
    assert gate.status()["strikes"] == 0


def test_http_429_retries_after_shared_pause_without_breaker(monkeypatch):
    calls = []

    class Resp(io.BytesIO):
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) <= 3:
            raise _http_error(429)
        return Resp(b'{"ok": 1}')

    monkeypatch.setattr(http.urllib.request, "urlopen", urlopen)
    data, status = http.get("wikimedia_commons", "chat", "https://commons.wikimedia.org/w/api.php?t=1",
                            retries=0, cache=False)
    assert data == {"ok": 1} and len(calls) == 4
    assert http._failures["wikimedia_commons"] == 0
    assert "wikimedia_commons" not in http._open_until or http._open_until["wikimedia_commons"] < time.time()
    assert gate.status()["limited_total"] == 3


def test_user_agent_has_contact():
    from app import config
    assert "(" in config.USER_AGENT and ("http" in config.USER_AGENT or "@" in config.USER_AGENT)
