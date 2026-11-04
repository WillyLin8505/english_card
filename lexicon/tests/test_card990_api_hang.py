"""Card #990 (問題回報 #1509): the API hung with its port open; hang_dump records why.
Also: dispatch_tick's resource alert was refused with 422 (area "backend" is not an issue area)."""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import hang_dump, issues

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _wait(cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_starved_thread_pool_writes_one_dump_with_stacks_and_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(hang_dump, "DUMP_DIR", tmp_path / "hang")
    monkeypatch.setattr(hang_dump, "SLOW_LOG", tmp_path / "slow.log")
    monkeypatch.setattr(hang_dump, "POOL_STALL_S", 1.0)
    monkeypatch.setattr(hang_dump, "PROBE_EVERY_S", 0.2)
    monkeypatch.setattr(hang_dump, "SLOW_S", 0.5)
    monkeypatch.setattr(hang_dump, "_last_dump", 0.0)
    monkeypatch.setattr(hang_dump, "_probe_sent", None)

    app = FastAPI()
    release = threading.Event()

    @app.get("/stuck")
    def stuck():   # a `def` route: runs on the worker thread pool, like every board route
        release.wait(20)
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    hang_dump.install(app)
    with TestClient(app) as client:
        client.portal.call(lambda: setattr(hang_dump._limiter, "total_tokens", 2))
        callers = [threading.Thread(target=client.get, args=("/stuck",)) for _ in range(2)]
        for t in callers:
            t.start()
        try:
            assert _wait(lambda: any((tmp_path / "hang").glob("*.txt"))), "no dump while the pool was full"
        finally:
            release.set()
            for t in callers:
                t.join(10)
        assert client.get("/health").json() == {"ok": True}
        client.portal.call(lambda: setattr(hang_dump._limiter, "total_tokens", 40))

    dumps = list((tmp_path / "hang").glob("*.txt"))
    assert len(dumps) == 1   # one per episode, not one every 2 s
    text = dumps[0].read_text(encoding="utf-8")
    assert "thread pool probe waiting" in text
    assert "thread pool: 2/2 busy" in text
    assert text.count("GET /stuck") == 2
    assert "release.wait(20)" in text   # the blocked line itself
    assert "GET /stuck" in (tmp_path / "slow.log").read_text(encoding="utf-8")


def test_snapshot_never_raises_without_a_running_app():
    out = hang_dump.snapshot("manual")
    assert "API stall: manual" in out and "threads:" in out


def test_tools_post_issues_only_with_known_areas():
    """dispatch_tick posted area "backend" → 422 on every tick, so the resource alert never reached the owner."""
    used = set()
    for path in TOOLS.glob("*.py"):
        used |= {(path.name, a) for a in re.findall(r'"area":\s*"([a-z_]+)"', path.read_text(encoding="utf-8"))}
    bad = sorted((f, a) for f, a in used if a not in issues.AREAS)
    assert not bad, bad
