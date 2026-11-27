"""Shared entry for tools that call llama-server (:8790) directly (card #1465, issue #1890).

Drop-in for ``urllib.request.urlopen``: ``model_gate.urlopen(req, timeout=300, source="card1048")``.
Across every tool process on the machine it
  * runs one model call at a time (file lock),
  * keeps the GPU idle part of the time like tagger ``GpuDuty`` (TAGGER_GPU_DUTY, default 0.6),
  * waits while the tagger is serving a learner's photo (``state/gpu_foreground.json``, written by
    tagger/inference_control.GpuDuty; ignored when older than FOREGROUND_FRESH_S or after FOREGROUND_HOLD_S),
  * appends one line per call to ``logs/model_gate.jsonl`` (ts, source, pid, secs, ok) so the load is traceable.
The response is read fully inside the lock and returned as a BytesIO (``read()`` / ``json.load`` / ``with`` work).
Streaming callers must not use it."""
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

LEX = Path(__file__).resolve().parents[1]
LOCK = LEX / "state" / "model_gate.lock"
STATE = LEX / "state" / "model_gate.json"
FOREGROUND = LEX / "state" / "gpu_foreground.json"
LOG = LEX / "logs" / "model_gate.jsonl"
FOREGROUND_FRESH_S = 30.0
FOREGROUND_HOLD_S = 120.0


def duty():
    try:
        return min(1.0, max(0.05, float(os.environ.get("TAGGER_GPU_DUTY", "0.6"))))
    except ValueError:
        return 0.6


def slots():
    """MODEL_GATE_SLOTS (default 1): calls allowed at once machine-wide; llama-server has 4 (-np 4).
    Each slot is one lock file; 1 keeps the original one-call-at-a-time behaviour."""
    try:
        return min(4, max(1, int(os.environ.get("MODEL_GATE_SLOTS", "1"))))
    except ValueError:
        return 1


def _try_lock(f):
    try:
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _lock(f):
    if os.name == "nt":
        import msvcrt
        while True:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.2)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX)


def _unlock(f):
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)


def _foreground_active():
    try:
        return time.time() - float(json.loads(FOREGROUND.read_text())["at"]) < FOREGROUND_FRESH_S
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _quiet_until():
    try:
        return float(json.loads(STATE.read_text())["quiet_until"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


def _log(source, secs, ok):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": round(time.time()), "source": source, "pid": os.getpid(),
                                "secs": round(secs, 2), "ok": ok}) + "\n")
    except OSError:
        pass


def urlopen(req, timeout=None, source=None):
    source = source or Path(sys.argv[0] or "python").stem
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    n = slots()
    if n == 1:
        lf = open(LOCK, "a+b")
        _lock(lf)
    else:  # first free slot lock (slot 0 is the shared LOCK, so 1-slot callers still wait for it)
        files = [LOCK] + [LOCK.with_name(f"model_gate.{i}.lock") for i in range(1, n)]
        lf = None
        while lf is None:
            for p in files:
                f = open(p, "a+b")
                if _try_lock(f):
                    lf = f
                    break
                f.close()
            else:
                time.sleep(0.2)
    with lf:
        try:
            held = time.time()
            while _foreground_active() and time.time() - held < FOREGROUND_HOLD_S:
                time.sleep(0.5)
            while (d := _quiet_until() - time.time()) > 0:
                time.sleep(min(d, 1.0))
            started, ok = time.time(), False
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read()
                ok = True
                return io.BytesIO(data)
            finally:
                ran = time.time() - started
                if duty() < 1:
                    STATE.write_text(json.dumps({"quiet_until": time.time() + ran * (1 - duty()) / duty()}))
                _log(source, ran, ok)
        finally:
            _unlock(lf)
