"""Background worker: a separate process that takes import jobs and
snapshot downloads from PostgreSQL (FOR UPDATE SKIP LOCKED) and runs
them. Closing the browser doesn't matter; stopping the worker leaves the
job at its checkpoint for the next worker.

    python worker/worker.py            # run until Ctrl+C
    python worker/worker.py --once     # process what is queued, then exit
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text  # noqa: E402

from app import db, images, jobs, policies, snapshots  # noqa: E402

_stop = threading.Event()
_text_slices: dict[str, int] = {}


def _beat(job_id: int, worker_id: str, done: threading.Event):
    while not done.wait(30):
        try:
            jobs.heartbeat(db.SessionLocal, job_id, worker_id)
        except Exception as e:  # noqa: BLE001
            print(f"heartbeat failed: {e}", flush=True)


def work_once(worker_id: str) -> bool:
    """Run one snapshot or one job if any is waiting. True if it did."""
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
    if _text_slices.get(worker_id, 0) >= 3:
        with db.SessionLocal() as s:
            image_task = images.claim_fetch(s, worker_id)
            s.commit()
            image_task_id = image_task.id if image_task else None
        if image_task_id is not None:
            with db.SessionLocal() as s:
                result = images.run_fetch(s, image_task_id)
                s.commit()
            _text_slices[worker_id] = 0
            print(f"[{worker_id}] image #{image_task_id} → {result}", flush=True)
            return True
    with db.SessionLocal() as s:
        job = jobs.claim(s, worker_id)
        s.commit()
        job_id = job.id if job else None
    if job_id is None:
        with db.SessionLocal() as s:
            image_task = images.claim_fetch(s, worker_id)
            s.commit()
            image_task_id = image_task.id if image_task else None
        if image_task_id is not None:
            with db.SessionLocal() as s:
                result = images.run_fetch(s, image_task_id)
                s.commit()
            _text_slices[worker_id] = 0
            print(f"[{worker_id}] image #{image_task_id} → {result}", flush=True)
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


def main():
    ap = argparse.ArgumentParser(description="Lexicon import worker")
    ap.add_argument("--once", action="store_true", help="drain the queue, then exit")
    ap.add_argument("--poll", type=float, default=2.0)
    args = ap.parse_args()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    with db.session_scope() as s:
        policies.seed(s)
    print(f"Worker {worker_id} ready (Ctrl+C to stop; running jobs resume from their checkpoint)",
          flush=True)
    while not _stop.is_set():
        try:
            did = work_once(worker_id)
        except Exception as e:  # noqa: BLE001 — keep the worker alive
            print(f"[{worker_id}] error: {type(e).__name__}: {e}", flush=True)
            did = False
        if not did:
            if args.once:
                break
            _stop.wait(args.poll)


if __name__ == "__main__":
    main()
