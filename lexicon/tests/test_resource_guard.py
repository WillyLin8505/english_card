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
