"""Card #730 / issue #867: keep the whole Windows PC under 80 % memory / CPU / GPU / disk.

Called by dispatch_tick every tick (no extra service). Measures, writes lexicon/state/resource_guard.json,
and returns the *temporary* actions: ``hold_launches`` (memory over the limit -> no new CLIs; lifts by
itself) and ``low_priority`` (CPU over -> BelowNormal for workers / llama-server / CLIs). Disk: removes
only this project's stale %TEMP%/dictionary-live-* folders. Never touches DB, media or backups.

    python lexicon/tools/resource_guard.py          # measure + act once, print summary
    python lexicon/tools/resource_guard.py --dry    # measure only
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "lexicon" / "state" / "resource_guard.json"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
LIMIT = 80.0
DEFAULTS = {"limit_pct": LIMIT, "release_pct": 75.0, "temp_max_age_min": 120,
            # owner 10/28 「硬碟不用管」: no disk checks, cleaning or alerts.
            "alert_after_min": 10, "disks": []}


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]


def memory_pct() -> float:
    if os.name != "nt":
        return 0.0
    m = _MemStatus()
    m.dwLength = ctypes.sizeof(_MemStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return float(m.dwMemoryLoad)


def _cpu_times() -> tuple[int, int, int] | None:
    if os.name != "nt":
        return None
    idle, kern, user = (ctypes.c_ulonglong() for _ in range(3))
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
    return idle.value, kern.value, user.value


def cpu_pct(prev: list | None) -> tuple[float | None, list | None]:
    """CPU % since the previous tick's sample (kept in the state file); None on the first run."""
    cur = _cpu_times()
    if cur is None:
        return None, None
    if not prev or len(prev) != 3:
        time.sleep(1.0)
        prev, cur = list(cur), _cpu_times()
    di, dk, du = (cur[i] - prev[i] for i in range(3))
    total = dk + du  # kernel time includes idle
    return (round(100.0 * (total - di) / total, 1) if total > 0 else None), list(cur)


def gpu_pct() -> dict:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15,
                           creationflags=NO_WINDOW)
        u, used, tot = (float(x) for x in r.stdout.strip().splitlines()[0].split(","))
        return {"util": u, "mem": round(100.0 * used / tot, 1)}
    except Exception:  # noqa: BLE001 — no GPU / no driver: nothing to guard
        return {"util": None, "mem": None}


def disk_pcts(disks: list[str]) -> dict:
    out = {}
    for d in disks:
        try:
            u = shutil.disk_usage(d)
            out[d[:2]] = round(100.0 * u.used / u.total, 1)
        except OSError:
            pass
    return out


def top_processes(n: int = 5) -> list[dict]:
    """Biggest working sets by image name (tasklist, read-only)."""
    try:
        r = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, timeout=30,
                           creationflags=NO_WINDOW)
        agg: dict[str, list] = {}
        for line in r.stdout.decode("mbcs", "replace").splitlines():
            p = [x.strip('"') for x in line.split('","')]
            if len(p) < 5:
                continue
            kb = int("".join(c for c in p[4].split()[0] if c.isdigit()) or 0)
            a = agg.setdefault(p[0], [0, 0])
            a[0] += kb
            a[1] += 1
        top = sorted(agg.items(), key=lambda kv: -kv[1][0])[:n]
        return [{"name": k, "mb": v[0] // 1024, "count": v[1]} for k, v in top]
    except Exception:  # noqa: BLE001
        return []


def clean_temp(max_age_min: float, dry: bool = False) -> dict:
    """Delete this project's dictionary-live-* temp folders (serve_app.live_pack) older than max_age_min."""
    tmp = Path(tempfile.gettempdir())
    freed = n = 0
    cutoff = time.time() - max_age_min * 60
    for p in tmp.glob("dictionary-live-*"):
        try:
            if not p.is_dir() or p.stat().st_mtime > cutoff:
                continue
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            if not dry:
                shutil.rmtree(p)  # fails while a process still holds files: left for the next tick
            freed += size
            n += 1
        except OSError:
            continue
    return {"folders": n, "freed_mb": freed // (1024 * 1024)}


def decide(m: dict, cfg: dict, prev: dict) -> dict:
    """Pure: measurements + previous guard state -> temporary actions (no side effects)."""
    lim, rel = cfg["limit_pct"], cfg["release_pct"]
    held = bool(prev.get("hold_launches"))
    mem = m.get("mem")
    hold = held if mem is None else (mem > lim or (held and mem > rel))
    cpu = m.get("cpu")
    low = bool(prev.get("low_priority")) if cpu is None else (cpu > lim or (prev.get("low_priority") and cpu > rel))
    over = []
    if mem is not None and mem > lim:
        over.append("memory")
    if cpu is not None and cpu > lim:
        over.append("cpu")
    if (m.get("gpu") or 0) > lim or (m.get("gpu_mem") or 0) > lim:
        over.append("gpu")
    for d, v in (m.get("disks") or {}).items():
        if v > lim:
            over.append("disk " + d)
    since = dict(prev.get("over_since") or {})
    now = m["ts"]
    for k in list(since):
        if k not in over:
            del since[k]
    for k in over:
        since.setdefault(k, now)
    alert = sorted(k for k, t in since.items() if now - t >= cfg["alert_after_min"] * 60)
    return {"hold_launches": hold, "low_priority": low, "over": over, "over_since": since, "alert": alert}


def lower_priority() -> int:
    """BelowNormal for python workers, llama-server and claude CLIs (PowerShell; idempotent)."""
    ps = ("$n=0; Get-Process python,pythonw,llama-server,claude,node -ErrorAction SilentlyContinue | "
          "Where-Object {$_.PriorityClass -eq 'Normal'} | ForEach-Object {try{$_.PriorityClass='BelowNormal';$n++}catch{}}; $n")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                           timeout=60, creationflags=NO_WINDOW)
        return int((r.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0


def run(dry: bool = False, cfg: dict | None = None) -> dict:
    cfg = {**DEFAULTS, **(cfg or {})}
    try:
        prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    cpu, cpu_sample = cpu_pct(prev.get("cpu_sample"))
    g = gpu_pct()
    m = {"ts": time.time(), "mem": memory_pct(), "cpu": cpu, "gpu": g["util"], "gpu_mem": g["mem"],
         "disks": disk_pcts(cfg["disks"])}
    act = decide(m, cfg, prev)
    notes = []
    if any(k.startswith("disk C") for k in act["over"]) and not dry:
        c = clean_temp(cfg["temp_max_age_min"])
        if c["folders"]:
            notes.append(f"temp cleaned {c['folders']} folders {c['freed_mb']} MB")
            m["disks"] = disk_pcts(cfg["disks"])
    if act["low_priority"] and not dry:
        k = lower_priority()
        if k:
            notes.append(f"BelowNormal x{k}")
    peak = prev.get("peak") or {}
    for key, val in (("mem", m["mem"]), ("cpu", cpu), ("gpu", m["gpu"]), ("gpu_mem", m["gpu_mem"])):
        if val is not None:
            peak[key] = max(peak.get(key, 0), val)
    for d, v in m["disks"].items():
        peak["disk " + d] = max(peak.get("disk " + d, 0), v)
    state = {**m, **act, "cpu_sample": cpu_sample, "peak": peak, "peak_since": prev.get("peak_since", m["ts"]),
             "top": top_processes() if act["over"] else [], "notes": notes}
    if not dry:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return state


def summary(s: dict) -> str:
    d = " ".join(f"{k}{v:.0f}%" for k, v in (s.get("disks") or {}).items())
    f = lambda v: "-" if v is None else f"{v:.0f}%"  # noqa: E731
    return (f"資源 記憶體{f(s.get('mem'))} CPU{f(s.get('cpu'))} GPU{f(s.get('gpu'))} {d}"
            + (f"｜超標:{','.join(s['over'])}" if s.get("over") else "｜皆<80%")
            + ("｜暫停派新CLI" if s.get("hold_launches") else ""))


if __name__ == "__main__":
    st = run(dry="--dry" in sys.argv)
    print(summary(st), st.get("notes"), st.get("top"))
