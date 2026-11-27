"""model_gate slots (owner 11/27 「時間太長」): MODEL_GATE_SLOTS=1 keeps one call at a time; 2+ lets that many run."""
import io
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import model_gate  # noqa: E402


def _run(monkeypatch, tmp_path, n_slots):
    monkeypatch.setattr(model_gate, "LOCK", tmp_path / "model_gate.lock")
    monkeypatch.setattr(model_gate, "STATE", tmp_path / "model_gate.json")
    monkeypatch.setattr(model_gate, "FOREGROUND", tmp_path / "fg.json")
    monkeypatch.setattr(model_gate, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setenv("MODEL_GATE_SLOTS", str(n_slots))
    monkeypatch.setenv("TAGGER_GPU_DUTY", "1")
    live, peak, guard = [0], [0], threading.Lock()

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        with guard:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.3)
        with guard:
            live[0] -= 1
        return Resp(b"{}")

    monkeypatch.setattr(model_gate.urllib.request, "urlopen", fake)
    ts = [threading.Thread(target=model_gate.urlopen, args=("x",)) for _ in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return peak[0]


def test_one_slot_is_one_call_at_a_time(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, 1) == 1


def test_three_slots_run_together(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, 3) == 3
