"""Card #730: resource_guard.decide is pure — hold/release hysteresis and the 10-minute alert."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import resource_guard as rg  # noqa: E402

CFG = dict(rg.DEFAULTS)


def m(**kw):
    base = {"ts": 1000.0, "mem": 50.0, "cpu": 10.0, "gpu": 5.0, "gpu_mem": 10.0, "disks": {"C:": 50.0}}
    base.update(kw)
    return base


def test_memory_over_holds_then_releases_with_hysteresis():
    a = rg.decide(m(mem=89), CFG, {})
    assert a["hold_launches"] and a["over"] == ["memory"]
    assert rg.decide(m(mem=78), CFG, a)["hold_launches"]       # between 75 and 80: still held
    assert not rg.decide(m(mem=70), CFG, a)["hold_launches"]


def test_alert_only_after_ten_minutes():
    a = rg.decide(m(ts=1000, disks={"C:": 95}), CFG, {})
    assert a["over"] == ["disk C:"] and a["alert"] == []
    b = rg.decide(m(ts=1000 + 601, disks={"C:": 95}), CFG, a)
    assert b["alert"] == ["disk C:"]
    c = rg.decide(m(ts=1700, disks={"C:": 40}), CFG, b)
    assert c["over"] == [] and c["over_since"] == {}


def test_cpu_over_lowers_priority():
    assert rg.decide(m(cpu=90), CFG, {})["low_priority"]


def _p(pid, ppid, name, mb, cmd=""):
    return {"pid": pid, "ppid": ppid, "name": name, "ws": mb * 2**20, "cmd": cmd}


def test_victim_is_biggest_non_service_descendant_of_a_cli():
    t = [_p(1, 0, "claude.exe", 900), _p(2, 1, "python.exe", 3400, "qc.py check --live"),
         _p(3, 2, "python.exe", 500), _p(4, 1, "python.exe", 4000, "serve_app.py"),
         _p(5, 9, "python.exe", 8000, "unrelated")]
    p, card = rg.pick_victim(t, {1: 731})
    assert (p["pid"], card) == (2, 731)
    assert rg.pick_victim([_p(1, 0, "claude.exe", 900)], {1: 731}) is None


def test_kill_only_after_two_minutes_over_90():
    due, since = rg.kill_due(95, 1000, None)
    assert not due and since == 1000
    assert rg.kill_due(95, 1121, since)[0]
    assert rg.kill_due(85, 1200, since) == (False, None)


def test_job_limit_struct_and_heavy_lock(tmp_path, monkeypatch):
    import job_limits, heavy_lock
    e = job_limits.build_limits(6)
    assert e.JobMemoryLimit == 6 * 1024 ** 3 and e.Basic.PriorityClass == 0x4000
    monkeypatch.setattr(heavy_lock, "LOCK", tmp_path / "h.lock")
    monkeypatch.setattr(heavy_lock, "_FH", None)
    monkeypatch.delenv(heavy_lock.ENV, raising=False)
    assert heavy_lock.slot(1)
