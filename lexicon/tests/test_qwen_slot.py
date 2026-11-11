"""Card #1071: Qwen scripts take the light qwen slot, not heavy_lock."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import heavy_lock  # noqa: E402
import qwen_slot  # noqa: E402


def test_routing():
    assert qwen_slot.is_qwen_command(["python", "lexicon/tools/card828_translate.py", "--n", "5"])
    assert qwen_slot.is_qwen_command(["python", "D:/x/card437_relation_native.py", "translate"])
    assert not qwen_slot.is_qwen_command(["flutter", "test"])
    assert not qwen_slot.is_qwen_command(["python", "lexicon/tools/qc.py", "check", "--live"])


def test_slots_are_independent_of_heavy_and_limited(tmp_path, monkeypatch):
    monkeypatch.setattr(qwen_slot, "DIR", tmp_path)
    monkeypatch.setattr(qwen_slot, "SLOTS", 2)
    monkeypatch.delenv(qwen_slot.ENV, raising=False)
    monkeypatch.setattr(qwen_slot, "_FH", None)
    assert qwen_slot.slot(1)
    held = qwen_slot._FH
    monkeypatch.setattr(qwen_slot, "_FH", None)
    monkeypatch.delenv(qwen_slot.ENV, raising=False)
    assert qwen_slot.slot(1)                      # second slot free
    second = qwen_slot._FH
    monkeypatch.setattr(qwen_slot, "_FH", None)
    monkeypatch.delenv(qwen_slot.ENV, raising=False)
    monkeypatch.setattr(qwen_slot.time, "sleep", lambda s: None)
    assert not qwen_slot.slot(0)                  # both taken -> gives up
    held.close(); second.close()
    assert heavy_lock.LOCK.name == "heavy.lock"   # the heavy lock file is a different one
    os.environ.pop(qwen_slot.ENV, None)
