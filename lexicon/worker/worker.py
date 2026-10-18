"""Background worker: a separate process that takes import jobs and
snapshot downloads from PostgreSQL (FOR UPDATE SKIP LOCKED) and runs
them. Closing the browser doesn't matter; stopping the worker leaves the
job at its checkpoint for the next worker.

    python worker/worker.py            # run until Ctrl+C
    python worker/worker.py --once     # process what is queued, then exit

Lanes keep network work, model work and picture labelling from waiting on
each other (start_lexicon.bat starts several of each):
    --lane all      everything, interleaved (the default)
    --lane text     snapshots and import jobs (dictionary sources + AI text)
    --lane images   Wikimedia picture searches and downloads (network only)
    --lane tags     AI labels for downloaded pictures, even while imports run
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

_LOADED_AT = time.time()  # before app.* is imported (#285)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text  # noqa: E402

from app import db, images, jobs, policies, snapshots  # noqa: E402

_stop = threading.Event()
_text_slices: dict[str, int] = {}
INTERLEAVE_IMAGE_TAGS = os.environ.get('LEXICON_INTERLEAVE_IMAGE_TAGS', '0').strip().lower() in {
    '1', 'true', 'yes', 'on'}


def _beat(job_id: int, worker_id: str, done: threading.Event):
    while not done.wait(30):
        try:
            jobs.heartbeat(db.SessionLocal, job_id, worker_id)
        except Exception as e:  # noqa: BLE001
            print(f"heartbeat failed: {e}", flush=True)


def _beat_image(task_id: int, worker_id: str, done: threading.Event):
    """Refresh started_at while a fetch runs. claim_fetch treats a start
    older than 10 minutes as a missed heartbeat (#236)."""
    while not done.wait(30):
        try:
            with db.SessionLocal() as s:
                s.execute(text(
                    "UPDATE image_fetch_tasks SET started_at = CURRENT_TIMESTAMP "
                    "WHERE id = :id AND worker_id = :worker AND status = 'running'"
                ), {"id": task_id, "worker": worker_id})
                s.commit()
        except Exception as e:  # noqa: BLE001
            print(f"image heartbeat failed: {e}", flush=True)


def _fetch_one_image(worker_id: str) -> bool:
    with db.SessionLocal() as s:
        image_task = images.claim_fetch(s, worker_id)
        s.commit()
        image_task_id = image_task.id if image_task else None
    if image_task_id is None:
        return False
    done = threading.Event()
    beat = threading.Thread(target=_beat_image, args=(image_task_id, worker_id, done), daemon=True)
    beat.start()
    try:
        with db.SessionLocal() as s:
            result = images.run_fetch(s, image_task_id)
            s.commit()
    finally:
        done.set()
        beat.join(timeout=1)
    _text_slices[worker_id] = 0
    print(f"[{worker_id}] image #{image_task_id} → {result}", flush=True)
    return True


def _tag_images(worker_id: str) -> bool:
    # Several labelling workers may run together (the model server has
    # several slots); tag_pending locks each picture it takes.
    with db.SessionLocal() as s:
        tagged = images.tag_pending(s, quick_only=False)
        s.commit()
    if tagged:
        print(f"[{worker_id}] 圖片 AI 標籤 +{tagged}", flush=True)
        return True
    # Card #167: relevance checks wait until this pass found nothing to tag.
    # drain itself also returns immediately while any picture is still pending.
    try:
        from app import relevance_queue
        with db.SessionLocal() as s:
            checked = relevance_queue.drain(s, limit=1)
            s.commit()
        if checked:
            print(f"[{worker_id}] 相關性檢查 +{checked}", flush=True)
            return True
    except Exception as exc:  # noqa: BLE001 — a check must not stop labelling
        print(f"[{worker_id}] 相關性檢查略過：{type(exc).__name__}", flush=True)
    return False


ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = Path(__file__).resolve().parents[1] / "backend" / "app"
CODE_CHANGED_EXIT = 3  # run_worker.bat starts the worker again on this code
CODE_CHECK_S = 15
_code = {"checked": 0.0}


def _code_files():
    yield Path(__file__)
    yield from CODE_DIR.rglob("*.py")


def _code_changed(loaded_at: float | None = None) -> str | None:
    """A code file edited after this process loaded app.* (checked at most
    every CODE_CHECK_S s), else None. Modules load once, some lazily, so an
    old worker mixes old and new code after an edit and every word fails
    (#285). A file dated in the future does not count, or the worker would
    restart forever."""
    now = time.monotonic()
    if loaded_at is None and now - _code["checked"] < CODE_CHECK_S:
        return None
    _code["checked"] = now
    loaded_at = _LOADED_AT if loaded_at is None else loaded_at
    wall = time.time()
    for path in _code_files():
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if loaded_at < mtime <= wall:
            return str(path.relative_to(ROOT))
    return None


def _qwen_paused() -> bool:
    """Owner paused Qwen on the board: tags lane must not call the model."""
    try:
        from app import agent_pause
        return agent_pause.is_paused("Qwen")
    except Exception:
        return False


def _quality_holds_gpu() -> bool:
    """Decision 5 / P2: when the quality pipeline claims the GPU (idle
    window), the tags lane waits instead of saturating Ollama."""
    claim = ROOT.parent / ".runtime" / "qc_gpu_claim"
    try:
        age = time.time() - claim.stat().st_mtime
    except OSError:
        return False
    return age < 600  # claim fresher than 10 minutes


def work_once(worker_id: str, lane: str = "all") -> bool:
    """Run one snapshot or one job if any is waiting. True if it did."""
    if lane == "images":
        return _fetch_one_image(worker_id)
    if lane == "tags":
        if _qwen_paused() or _quality_holds_gpu():
            time.sleep(5)
            return False
        return _tag_images(worker_id)
    with db.SessionLocal() as s:
        snap = snapshots.claim(s)
        s.commit()
    if snap is not None:
        print(f"[{worker_id}] snapshot #{snap.id} {snap.source} {snap.language}", flush=True)
        with db.SessionLocal() as s:
            r = snapshots.run(s, snap.id)
            s.commit()
            print(f"[{worker_id}] snapshot #{snap.id} → {r.status} {r.error or ''}", flush=True)
        return True
    # One image batch after every three text words. This keeps pictures moving
    # in parallel without allowing them to starve dictionary data.
    if lane == "all" and _text_slices.get(worker_id, 0) >= 3:
        if _fetch_one_image(worker_id):
            return True
        # Existing and newly downloaded pictures must each have three verified
        # labels in every CEFR band. Interleave one classification with text so
        # a large import queue cannot starve picture completion for hours.
        if INTERLEAVE_IMAGE_TAGS:
            with db.SessionLocal() as s:
                owns_image_slot = bool(s.scalar(text(
                    "SELECT pg_try_advisory_xact_lock(770000001)")))
                tagged = images.tag_pending(s, limit=1, quick_only=False) if owns_image_slot else 0
                s.commit()
            if tagged:
                _text_slices[worker_id] = 0
                print(f"[{worker_id}] 圖片 CEFR 標籤 +{tagged}", flush=True)
                return True
    with db.SessionLocal() as s:
        job = jobs.claim(s, worker_id)
        s.commit()
        job_id = job.id if job else None
    if job_id is None and lane == "text":
        return False
    if job_id is None:
        if _fetch_one_image(worker_id):
            return True
        # Nothing queued: give the next downloaded picture its AI labels.
        # While another worker's import runs (it needs the same vision model
        # for AI translations) only the quick label scoring goes on; the
        # full re-labelling waits for the import.
        with db.SessionLocal() as s:
            busy = s.execute(text("SELECT 1 FROM import_jobs WHERE status = 'running' LIMIT 1")).first()
        with db.SessionLocal() as s:
            s.execute(text("SELECT pg_advisory_xact_lock(770000001)"))
            tagged = images.tag_pending(s, quick_only=bool(busy))
            s.commit()
        if tagged:
            print(f"[{worker_id}] 圖片 AI 標籤 +{tagged}", flush=True)
        return bool(tagged)
    print(f"[{worker_id}] job #{job_id}", flush=True)
    done = threading.Event()
    beat = threading.Thread(target=_beat, args=(job_id, worker_id, done), daemon=True)
    beat.start()
    try:
        state = jobs.run(db.SessionLocal, job_id, worker_id, stop=_stop.is_set, max_words=1,
                         on_word=lambda w, sec: print(f"  {w} ({sec:.1f}s)", flush=True))
    finally:
        done.set()
    print(f"[{worker_id}] job #{job_id} → {state}", flush=True)
    _text_slices[worker_id] = _text_slices.get(worker_id, 0) + 1
    return True


# While a worker has work, Windows must not idle-sleep: after a sleep the
# model server's GPU state was garbage and ~1,000 pictures failed (#172). Held
# on mains power only, and let go after ten idle minutes. A closed lid or
# choosing Sleep still sleeps; the screen may still turn off.
AWAKE_IDLE_S = 600
_awake = {"on": None, "checked": 0.0}


def _on_battery() -> bool:
    import ctypes

    class Power(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_byte), ("flag", ctypes.c_byte), ("percent", ctypes.c_byte),
                    ("saver", ctypes.c_byte), ("left", ctypes.c_ulong), ("full", ctypes.c_ulong)]
    p = Power()
    return bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p))) and p.ac == 0


def _hold_awake(busy: bool) -> None:
    if sys.platform != "win32":
        return
    now = time.monotonic()
    if busy == _awake["on"] and now - _awake["checked"] < 60:
        return  # unchanged; the mains/battery state is checked once a minute
    on = busy and not _on_battery()
    import ctypes
    es_continuous, es_system_required = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(
        es_continuous | (es_system_required if on else 0))
    _awake["on"], _awake["checked"] = busy, now


def main():
    ap = argparse.ArgumentParser(description="Lexicon import worker")
    ap.add_argument("--once", action="store_true", help="drain the queue, then exit")
    ap.add_argument("--poll", type=float, default=2.0)
    ap.add_argument("--lane", choices=("all", "text", "images", "tags"), default="all")
    args = ap.parse_args()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    if args.lane != "all":
        worker_id += f"-{args.lane}"
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    with db.session_scope() as s:
        # Four workers start together. Serialize the idempotent policy seed so
        # two fresh processes cannot race on the same unique policy rows.
        if s.bind is not None and s.bind.dialect.name == "postgresql":
            s.execute(text("SELECT pg_advisory_xact_lock(770000000)"))
        policies.seed(s)
    print(f"Worker {worker_id} ready (Ctrl+C to stop; running jobs resume from their checkpoint)",
          flush=True)
    last_work = time.monotonic()
    while not _stop.is_set():
        changed = _code_changed()
        if changed:
            # Between work units, so no job is cut mid-word.
            print(f"[{worker_id}] 程式已更新（{changed}），結束讓 run_worker.bat 用新程式重開",
                  flush=True)
            sys.exit(CODE_CHANGED_EXIT)
        _hold_awake(time.monotonic() - last_work < AWAKE_IDLE_S)
        try:
            did = work_once(worker_id, args.lane)
        except Exception as e:  # noqa: BLE001 — keep the worker alive
            print(f"[{worker_id}] error: {type(e).__name__}: {e}", flush=True)
            did = False
        if did:
            last_work = time.monotonic()
        else:
            if args.once:
                break
            _stop.wait(args.poll)


if __name__ == "__main__":
    main()
