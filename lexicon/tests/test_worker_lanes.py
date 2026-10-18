"""Worker lanes: network, model and picture work run in separate processes."""

from __future__ import annotations

import importlib.util

from conftest import HOME


def _worker_module():
    spec = importlib.util.spec_from_file_location("lexicon_worker", HOME / "worker" / "worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_picture_lanes_only_do_their_own_work(monkeypatch):
    worker = _worker_module()
    calls = []
    monkeypatch.setattr(worker, "_fetch_one_image", lambda wid: calls.append(("images", wid)) or True)
    monkeypatch.setattr(worker, "_tag_images", lambda wid: calls.append(("tags", wid)) or False)
    assert worker.work_once("w1", "images") is True
    assert worker.work_once("w2", "tags") is False
    assert calls == [("images", "w1"), ("tags", "w2")]


def test_image_heartbeat_refreshes_started_at_while_the_fetch_runs(monkeypatch):
    worker = _worker_module()
    sql = []

    class FakeSession:
        def execute(self, statement, params=None):
            sql.append((str(statement), params))

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(worker.db, "SessionLocal", lambda: FakeSession())
    state = {"n": 0}

    def wait(self, timeout=None):
        state["n"] += 1
        return state["n"] > 1

    monkeypatch.setattr(worker.threading.Event, "wait", wait)
    worker._beat_image(9, "host-1-images", worker.threading.Event())
    assert sql and sql[0][1]["id"] == 9 and sql[0][1]["worker"] == "host-1-images"
    assert "started_at" in sql[0][0]


def test_text_lane_never_takes_picture_work(session, monkeypatch):
    worker = _worker_module()  # the same app.db as the test session: lexicon_test

    def forbidden(*args, **kwargs):
        raise AssertionError("the text lane must not fetch or label pictures")

    monkeypatch.setattr(worker.images, "claim_fetch", forbidden)
    monkeypatch.setattr(worker.images, "tag_pending", forbidden)
    # Even after three text words (when the "all" lane interleaves pictures).
    worker._text_slices["w-text"] = 3
    assert worker.work_once("w-text", "text") is False


def test_worker_notices_backend_code_newer_than_its_start(tmp_path, monkeypatch):
    """問題回報 #285: a worker started before a backend edit mixed old and new
    modules; it now exits between units so run_worker.bat restarts it."""
    import os
    import time
    worker = _worker_module()
    code = tmp_path / "app"
    code.mkdir()
    module = code / "images.py"
    module.write_text("x = 1\n")
    monkeypatch.setattr(worker, "CODE_DIR", code)
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(worker, "_code_files", lambda: iter([module]))
    now = time.time()
    os.utime(module, (now - 100, now - 100))
    assert worker._code_changed(loaded_at=now - 50) is None
    os.utime(module, (now - 10, now - 10))
    assert worker._code_changed(loaded_at=now - 50) == os.path.join("app", "images.py")
    os.utime(module, (now + 3600, now + 3600))  # a future date must not loop restarts
    assert worker._code_changed(loaded_at=now - 50) is None
