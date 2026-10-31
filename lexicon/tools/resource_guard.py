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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proc_identity  # noqa: E402

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


PROTECTED = ("serve_app", "start_services", "tagger", "llama-server", "uvicorn", "postgres", "worker",
             "dispatch_tick", "resource_guard", "launch_agent")
KILL_PCT, KILL_AFTER_S = 90.0, 120.0
LOGS = ROOT / "lexicon" / "logs" / "agents"


def process_table() -> list[dict]:
    ps = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,WorkingSetSize,"
          "CommandLine | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60,
                           creationflags=NO_WINDOW)
        rows = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
        return [{"pid": x["ProcessId"], "ppid": x["ParentProcessId"], "name": x["Name"] or "",
                 "ws": int(x["WorkingSetSize"] or 0), "cmd": x["CommandLine"] or ""} for x in rows]
    except Exception:  # noqa: BLE001
        return []


def cli_roots() -> dict[int, int]:
    """pid of every dispatched CLI -> its card id (logs/agents/card<id>.pid.json)."""
    out = {}
    for f in LOGS.glob("card*.pid.json"):
        info = proc_identity.read_run(f)
        if proc_identity.run_alive(info):  # a reused pid is someone else's process (card #919)
            out[int(info["pid"])] = int(f.name[4:].split(".")[0])
    return out


def pick_victim(table: list[dict], roots: dict[int, int], min_mb: int = 300) -> tuple[dict, int] | None:
    """Pure: the biggest descendant (newest pid on a tie) of a dispatched CLI that is not a service and not
    the CLI itself -> (process, card id). Services started by a CLI are skipped by name."""
    kids: dict[int, list[dict]] = {}
    for p in table:
        kids.setdefault(p["ppid"], []).append(p)
    best = None
    for root, card in roots.items():
        stack = list(kids.get(root, []))
        while stack:
            p = stack.pop()
            stack.extend(kids.get(p["pid"], []))
            if p["pid"] in roots or any(k in (p["name"] + " " + p["cmd"]).lower() for k in PROTECTED):
                continue
            if p["ws"] >= min_mb * 1024 * 1024 and (best is None or (p["ws"], p["pid"]) > (best[0]["ws"], best[0]["pid"])):
                best = (p, card)
    return best


def kill_due(mem: float | None, ts: float, prev_since: float | None) -> tuple[bool, float | None]:
    """Pure: memory > 90 % for 2 minutes -> (kill now, new over-since)."""
    if mem is None or mem <= KILL_PCT:
        return False, None
    since = prev_since or ts
    return ts - since >= KILL_AFTER_S, since


def kill_heavy_child(dry: bool = False) -> str | None:
    v = pick_victim(process_table(), cli_roots())
    if not v:
        return None
    p, card = v
    msg = f"資源不足，稍後重跑：結束 {p['name']} pid {p['pid']} ({p['ws'] // 2**20} MB)"
    if dry:
        return msg
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p["pid"])], capture_output=True, timeout=30,
                   creationflags=NO_WINDOW)
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:5173/api/tasks/{card}", method="PUT",
                                     data=json.dumps({"progress": msg}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:  # noqa: BLE001
        pass
    return f"卡 #{card} {msg}"


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
    due, state_since = kill_due(m["mem"], m["ts"], prev.get("mem90_since"))
    if due:
        k = kill_heavy_child(dry)
        if k:
            notes.append(k)
            state_since = m["ts"]  # give it another 2 minutes before the next victim
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
             "top": top_processes() if act["over"] else [], "notes": notes,
             "mem90_since": state_since}
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
