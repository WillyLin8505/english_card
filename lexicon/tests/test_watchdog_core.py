"""Card #1013 / issue #1534: ensure_core starts a closed core port at once and restarts cloudflared."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import watchdog as wd  # noqa: E402

TUNNEL = "cloudflared.exe tunnel --config x run english-card"


def setup(monkeypatch, procs, open_ports, public=True):
    calls = []
    monkeypatch.setattr(wd, "cmdlines", lambda: procs)
    monkeypatch.setattr(wd, "port_up", lambda p: p in open_ports)
    monkeypatch.setattr(wd, "public_ok", lambda *a, **k: public)
    monkeypatch.setattr(wd, "console", lambda title, cmd, cwd: calls.append(("console", title, cmd)))
    monkeypatch.setattr(wd.subprocess, "Popen", lambda *a, **k: calls.append(("popen", str(a[0]))))
    monkeypatch.setattr(wd, "restart_cloudflared", lambda: calls.append(("cloudflared",)))
    monkeypatch.setattr(wd, "CLOUDFLARED", type("P", (), {"exists": lambda self: True})())
    return calls


def test_all_up_does_nothing(monkeypatch):
    calls = setup(monkeypatch, [TUNNEL], {8123, 8770, 5173, 8765})
    assert wd.ensure_core(lambda m: None, 0) == ([], 0)
    assert calls == []


def test_closed_ports_start_one_service_per_tick(monkeypatch):
    calls = setup(monkeypatch, [TUNNEL], set())
    started, _ = wd.ensure_core(lambda m: None, 0)
    assert len(started) == 1 and started[0].startswith("serve_app")
    assert len(calls) == 1


def test_tagger_only_through_start_tagger_bat(monkeypatch):
    calls = setup(monkeypatch, [TUNNEL], {8123, 8770, 5173})
    started, _ = wd.ensure_core(lambda m: None, 0)
    assert started[0].startswith("tagger")
    assert calls == [("console", "tagger", r"tagger\start_tagger.bat")]


def test_tagger_not_started_while_llama_server_runs(monkeypatch):
    calls = setup(monkeypatch, [TUNNEL, "python start_llm.py"], {8123, 8770, 5173})
    assert wd.ensure_core(lambda m: None, 0)[0] == []
    assert calls == []


def test_missing_cloudflared_restarted_first(monkeypatch):
    calls = setup(monkeypatch, ["notepad.exe"], set())
    started, _ = wd.ensure_core(lambda m: None, 0)
    assert started == ["cloudflared tunnel"] and calls == [("cloudflared",)]


def test_public_failures_restart_cloudflared_on_second(monkeypatch):
    calls = setup(monkeypatch, [TUNNEL], {8123, 8770, 5173, 8765}, public=False)
    assert wd.ensure_core(lambda m: None, 0) == ([], 1)
    assert calls == []
    started, fails = wd.ensure_core(lambda m: None, 1)
    assert started == ["cloudflared tunnel (public URL down)"] and fails == 0
    assert calls == [("cloudflared",)]
