"""Records why the API stops answering (card #990, 問題回報 #1509).

The API hung three times on 11/04 with its process alive and port 8770 open, and the
watchdog's restart left nothing to read. Two checks run here:
- an asyncio task beats every second and, every 5 s, runs a no-op on the worker thread
  pool that serves every `def` route (/health too);
- a plain thread watches both. Event loop silent > LOOP_STALL_S, or the pool probe not
  back within POOL_STALL_S → one file in lexicon/logs/api_hang/ with every thread's
  stack, the requests in flight, the thread pool and the DB pool.
Requests slower than SLOW_S get one line in lexicon/logs/api_slow.log.
"""
from __future__ import annotations

import asyncio
import itertools
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
DUMP_DIR = LOG_DIR / "api_hang"
SLOW_LOG = LOG_DIR / "api_slow.log"
LOOP_STALL_S = 15.0
POOL_STALL_S = 30.0
PROBE_EVERY_S = 5.0
SLOW_S = 10.0
DUMP_GAP_S = 600.0   # one dump per stall episode, at most every 10 minutes
KEEP_DUMPS = 30
SLOW_LOG_MAX = 2_000_000

_beat = time.monotonic()
_probe_sent: float | None = None   # a pool probe is waiting for a thread since then
_last_dump = 0.0
_inflight: dict[int, tuple[str, str, float, str]] = {}
_ids = itertools.count(1)
_limiter = None


def install(app) -> None:
    @app.middleware("http")
    async def _track(request, call_next):
        rid = next(_ids)
        start = time.monotonic()
        client = request.client.host if request.client else "?"
        _inflight[rid] = (request.method, request.url.path + (f"?{request.url.query}" if request.url.query else ""),
                          start, client)
        try:
            return await call_next(request)
        finally:
            _inflight.pop(rid, None)
            took = time.monotonic() - start
            if took >= SLOW_S:
                _slow_line(request.method, request.url.path, took, client)

    @app.on_event("startup")
    async def _start():
        global _limiter
        try:
            import anyio.to_thread
            _limiter = anyio.to_thread.current_default_thread_limiter()
        except Exception:  # noqa: BLE001 — the numbers are a bonus
            _limiter = None
        asyncio.get_running_loop().create_task(_heartbeat())
        threading.Thread(target=_monitor, daemon=True, name="hang-monitor").start()


async def _heartbeat():
    global _beat, _probe_sent
    last_probe = 0.0
    while True:
        _beat = time.monotonic()
        if _probe_sent is None and _beat - last_probe >= PROBE_EVERY_S:
            last_probe = _beat
            _probe_sent = _beat
            asyncio.get_running_loop().create_task(_probe())
        await asyncio.sleep(1.0)


async def _probe():
    global _probe_sent
    import anyio.to_thread
    await anyio.to_thread.run_sync(lambda: None)
    _probe_sent = None


def _monitor():
    while True:
        time.sleep(2.0)
        try:
            now = time.monotonic()
            reasons = []
            if now - _beat > LOOP_STALL_S:
                reasons.append(f"event loop silent {now - _beat:.0f}s")
            sent = _probe_sent
            if sent is not None and now - sent > POOL_STALL_S:
                reasons.append(f"thread pool probe waiting {now - sent:.0f}s")
            if reasons and now - _last_dump > DUMP_GAP_S:
                write_dump("; ".join(reasons))
        except Exception:  # noqa: BLE001 — the monitor must never die
            pass


def snapshot(reason: str) -> str:
    now = time.monotonic()
    lines = [f"{datetime.now():%Y-%m-%d %H:%M:%S} API stall: {reason}"]
    if _limiter is not None:
        try:
            lines.append(f"thread pool: {_limiter.borrowed_tokens}/{_limiter.total_tokens} busy, "
                         f"{_limiter.statistics().tasks_waiting} waiting")
        except Exception as e:  # noqa: BLE001
            lines.append(f"thread pool: ? ({e})")
    try:
        from . import db
        lines.append(f"db pool: {db.engine.pool.status()}")
    except Exception as e:  # noqa: BLE001
        lines.append(f"db pool: ? ({e})")
    reqs = sorted(_inflight.values(), key=lambda r: r[2])
    lines.append(f"requests in flight: {len(reqs)}")
    for method, path, start, client in reqs[:200]:
        lines.append(f"  {now - start:7.1f}s {method} {path} from {client}")
    names = {t.ident: t.name for t in threading.enumerate()}
    frames = sys._current_frames()
    lines.append(f"threads: {len(frames)}")
    # Group identical stacks: forty pool threads waiting on the same line read as one entry.
    groups: dict[str, list[str]] = {}
    for ident, frame in frames.items():
        stack = "".join(traceback.format_stack(frame)[-25:])
        groups.setdefault(stack, []).append(names.get(ident, str(ident)))
    for stack, who in sorted(groups.items(), key=lambda g: -len(g[1])):
        lines.append(f"\n── {len(who)} thread(s): {', '.join(who[:8])}{' …' if len(who) > 8 else ''}")
        lines.append(stack.rstrip())
    return "\n".join(lines) + "\n"


def write_dump(reason: str) -> Path | None:
    global _last_dump
    _last_dump = time.monotonic()
    try:
        DUMP_DIR.mkdir(parents=True, exist_ok=True)
        path = DUMP_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.txt"
        path.write_text(snapshot(reason), encoding="utf-8")
        for old in sorted(DUMP_DIR.glob("*.txt"))[:-KEEP_DUMPS]:
            old.unlink(missing_ok=True)
        return path
    except OSError:
        return None


def _slow_line(method: str, path: str, took: float, client: str) -> None:
    try:
        if SLOW_LOG.exists() and SLOW_LOG.stat().st_size > SLOW_LOG_MAX:
            SLOW_LOG.replace(SLOW_LOG.with_suffix(".log.1"))
        with SLOW_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {took:6.1f}s {method} {path} from {client} "
                    f"(in flight {len(_inflight)})\n")
    except OSError:
        pass
