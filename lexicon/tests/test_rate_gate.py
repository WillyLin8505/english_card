"""問題回報 #360: shared gates for Smithsonian / Openverse that skip a paused source."""

from __future__ import annotations

import io
import time
import urllib.error

import pytest

from app import images, rate_gate, wikimedia_gate


def _http_error(url, code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError(url, code, "Too Many Requests", headers, io.BytesIO(b""))


SI = "https://api.si.edu/openaccess/api/v1.0/search?q=cat&api_key=DEMO_KEY"
OV = "https://api.openverse.org/v1/images/?q=cat"


def test_gate_for_picks_the_right_budget():
    assert rate_gate.gate_for(SI) is rate_gate.SMITHSONIAN
    assert rate_gate.gate_for(OV) is rate_gate.OPENVERSE
    assert rate_gate.gate_for("https://commons.wikimedia.org/w/api.php") is wikimedia_gate.GATE
    assert rate_gate.gate_for("https://ids.si.edu/ids/deliveryService?id=x") is None  # downloads: not metered
    assert rate_gate.gate_for("https://storage.googleapis.com/openimages/x.jpg") is None


def test_wikimedia_module_api_still_reads_module_constants(monkeypatch, tmp_path):
    monkeypatch.setattr(wikimedia_gate, "STATE", tmp_path / "w.json")
    monkeypatch.setattr(wikimedia_gate, "BACKOFF_BASE", 10.0)
    assert 9 < wikimedia_gate.penalize("3") <= 10
    assert wikimedia_gate.status()["strikes"] == 1
    assert wikimedia_gate.GATE.backoff_base == 10.0 and wikimedia_gate.GATE.state == tmp_path / "w.json"


def test_skip_when_paused_raises_at_once_instead_of_sleeping(monkeypatch):
    gate = rate_gate.SMITHSONIAN
    monkeypatch.setattr(gate, "backoff_base", 600.0)
    pause = gate.penalize("41133")  # what api.data.gov's DEMO_KEY really answers
    assert 41000 < pause <= 41133
    started = time.time()
    with pytest.raises(rate_gate.Paused) as e:
        gate.wait_turn()
    assert time.time() - started < 0.5
    assert "smithsonian" in str(e.value) and "小時" in str(e.value)
    assert gate.status()["skipped_total"] == 1
    assert gate.paused_for() > 40000


def test_long_retry_after_is_capped_at_a_day(monkeypatch):
    gate = rate_gate.OPENVERSE
    assert gate.penalize(str(5 * 86400)) <= 86400 + 1


def test_fetch_on_429_pauses_the_shared_gate_and_moves_on_without_retrying(monkeypatch):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise _http_error(request.full_url, 429, "41133")

    monkeypatch.setattr(images.urllib.request, "build_opener", lambda *a, **k: Opener())
    sleeps = []
    monkeypatch.setattr(images.time, "sleep", lambda s: sleeps.append(s))
    with pytest.raises(rate_gate.Paused) as e:
        images.fetch(SI, validate=images.check_smithsonian_url)
    assert len(calls) == 1, "no in-process retry against a paused source"
    assert sleeps == [], "no Retry-After sleep either"
    assert e.value.http_code == 429 and "429" in str(e.value)
    # Every later call (any process) skips without touching the network.
    with pytest.raises(rate_gate.Paused):
        images.fetch(SI, validate=images.check_smithsonian_url)
    assert len(calls) == 1
    assert rate_gate.SMITHSONIAN.status()["limited_total"] == 1


def test_wikimedia_still_waits_the_pause_out(monkeypatch):
    """The primary source keeps #339's behaviour (retry after a short shared
    pause) — once; a second 429 raises so the task is requeued (問題回報 #376,
    covered by test_card378_wikimedia_cap)."""
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            if len(calls) < 2:
                raise _http_error(request.full_url, 429)
            return Resp(b"ok")

    monkeypatch.setattr(images.urllib.request, "build_opener", lambda *a, **k: Opener())
    assert images.fetch("https://commons.wikimedia.org/w/api.php?x=1") == b"ok"
    assert len(calls) == 2


def test_auto_fetch_treats_a_paused_source_as_skipped_not_rate_limited(session, monkeypatch):
    """A task must not be requeued every hour for a source that allows ten
    requests a day: the paused source is logged and the task completes on the
    others (問題回報 #360)."""
    from app import models as m
    lx = m.Lexeme(language="en", lemma="kiwi", normalized="kiwi", pos="noun", status="full")
    session.add(lx)
    session.flush()
    sense = m.Sense(lexeme_id=lx.id, sense_key="kiwi", ordinal=0)
    session.add(sense)
    session.flush()
    tried = []

    def paused(s, sense_id, lemma, gloss, native, ctx):
        tried.append("smithsonian")
        raise rate_gate.Paused(rate_gate.SMITHSONIAN, 40000.0)

    def empty(name):
        def search(s, sense_id, lemma, gloss, native, ctx):
            tried.append(name)
            return []
        return search

    monkeypatch.setitem(images.IMAGE_SOURCES, "wikimedia_commons", (empty("wikimedia_commons"), None))
    monkeypatch.setitem(images.IMAGE_SOURCES, "open_images", (empty("open_images"), None))
    monkeypatch.setitem(images.IMAGE_SOURCES, "smithsonian", (paused, None))
    monkeypatch.setitem(images.IMAGE_SOURCES, "openverse", (empty("openverse"), None))
    out = images.auto_fetch(session, "en", "zh-TW", "kiwi", sources=list(images.IMAGE_SOURCE_CHAIN))
    assert tried == ["wikimedia_commons", "open_images", "openverse", "smithsonian"]
    assert out["source_paused"] is True
    assert not out["rate_limited"] and not out["transient"] and not out["timed_out"]
    assert any("smithsonian" in e and "暫停" in e for e in out["errors"])

    task = m.ImageFetchTask(target_language="en", native_language="zh-TW", lemma="kiwi",
                            fields=["sense_image"], status="queued")
    session.add(task)
    session.flush()
    images.run_fetch(session, task.id)
    assert task.status == "completed_with_errors", "not requeued: the other sources ran"
    assert task.retry_at is None and task.finished_at is not None
