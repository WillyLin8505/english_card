"""Is this process still the CLI we launched? (card #919)

Windows reuses pids: of 9 "alive" card*.pid.json on 10/31, 6 were other programs (NVIDIA Overlay…).
So a pid alone proves nothing. launch_agent records the process creation time next to the pid and
launch_agent, dispatch_tick, resource_guard and the admin API all ask this module. Records from before
#919 have no creation time; a process started well after the launch can't be the one we launched.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

LEGACY_SLACK_S = 30      # launch → recorded `at` in a pid file written by launch_agent
SAME_START_S = 1.0       # creation time is exact; this only absorbs float rounding


def process_started(pid) -> float | None:
    """Epoch creation time of a running process, None if it is gone (elsewhere than Windows: 0.0 if alive)."""
    if not pid:
        return None
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
            return 0.0
        except OSError:
            return None
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        code = ctypes.c_ulong()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return None
        t = [ctypes.c_ulonglong() for _ in range(4)]
        if not k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
            return 0.0
        return t[0].value / 1e7 - 11644473600
    finally:
        k.CloseHandle(h)


def same_process(pid, started: float | None = None, at: float | None = None,
                 slack_s: float = LEGACY_SLACK_S) -> bool:
    """True if `pid` runs and is the process recorded: same creation time, or (old records) not
    started after the launch at `at`. Neither known → only "something has this pid", so False."""
    now = process_started(pid)
    if now is None:
        return False
    if now == 0.0:          # no creation time on this platform or for this process
        return True
    if started:
        return abs(now - float(started)) <= SAME_START_S
    return bool(at) and now <= float(at) + slack_s


def run_alive(info: dict | None) -> bool:
    """One card*.pid.json record."""
    if not info:
        return False
    return same_process(info.get("pid"), info.get("started"), info.get("at"))


def read_run(path: Path) -> dict | None:
    try:
        info = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) else None


def kill_tree(info: dict | None) -> bool:
    """End a recorded CLI and its children. Only after the identity check: a reused pid is someone else."""
    if not run_alive(info):
        return False
    r = subprocess.run(["taskkill", "/PID", str(int(info["pid"])), "/T", "/F"], capture_output=True,
                       creationflags=0x08000000 if os.name == "nt" else 0)
    return r.returncode == 0
