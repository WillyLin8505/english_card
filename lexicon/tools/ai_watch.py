"""Owner 10/31 (the PC powered off under AI load): AI work stays under 80 % of this PC.

One long-running process (started by dispatch_tick, so nothing to install):
- keeps a Windows Job Object that every AI process joins within 10 s: CPU hard cap 80 %, memory
  limit JOB_MEMORY_GB, below-normal priority. Windows enforces these: over the memory limit an
  allocation fails and that AI process stops; the PC does not.
- Claude and Codex CLIs already sit in a job of their own and cannot join that one; each gets a
  job of its own instead (TREE_CPU_PCT, TREE_MEMORY_GB), which its child processes inherit.
- GPU has no such cap: when it stays over the limit or too hot, the model servers are suspended
  for GPU_REST_S at a time (they carry on afterwards; requests just wait).
- writes one line every 10 s to lexicon/logs/ai_watch.log, so the last line before a crash says
  what the PC was doing.

    pythonw lexicon/tools/ai_watch.py          # the watcher
    python lexicon/tools/ai_watch.py --once    # one sample and sweep, print it
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "lexicon" / "logs" / "ai_watch.log"
STATE = ROOT / "lexicon" / "state" / "ai_watch.json"
JOB_NAME = "Local\\EnglishCardAI"
MUTEX_NAME = "Local\\EnglishCardAIWatch"
NO_WINDOW = 0x08000000

CPU_PCT = 80
# 80 % of 63 GB less what stays outside the job: serve_app (~12 GB) and Windows' own use.
JOB_MEMORY_GB = 42
# With issue_swarm.max_parallel 6 these add up to 72 % CPU and 72 GB at the very worst; memory that
# high never happens together, and resource_guard stops new CLIs at 80 % whole-PC memory.
TREE_CPU_PCT = 12
TREE_MEMORY_GB = 12
GPU_PCT = 80
GPU_TEMP_C = 85
GPU_OVER_S = 60
GPU_REST_S = 20
TICK_S = 10
LOG_MAX = 5_000_000

AI_NAMES = {"claude.exe", "codex.exe", "cursor-agent.exe", "cursor.cmd", "llama-server.exe", "ollama.exe",
            "dart.exe", "dartaotruntime.exe", "flutter_tester.exe", "node.exe", "python.exe", "pythonw.exe"}
GPU_NAMES = {"llama-server.exe"}
# Services the App and board need, the desktop app itself, and this watcher.
OUTSIDE = ("serve_app", "uvicorn app.main", "keep_awake", "ai_watch", "vite", "dispatch_tick")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]


class _BasicLimit(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [("Basic", _BasicLimit), ("Io", _IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _CpuRate(ctypes.Structure):
    _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]


def _setup_api():
    k = kernel32
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    k.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
                                            wintypes.LPVOID]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenMutexW.restype = wintypes.HANDLE
    k.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]


def create_job(name: str | None, cpu_pct: int, memory_bytes: int):
    """A job with a hard CPU cap, a total memory limit and below-normal priority."""
    job = kernel32.CreateJobObjectW(None, name)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = _ExtendedLimit()
    limits.Basic.LimitFlags = 0x200 | 0x20  # JOB_MEMORY | PRIORITY_CLASS
    limits.Basic.PriorityClass = 0x4000  # BELOW_NORMAL
    limits.JobMemoryLimit = memory_bytes
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    rate = _CpuRate(1 | 4, cpu_pct * 100)  # ENABLE | HARD_CAP
    if not kernel32.SetInformationJobObject(job, 15, ctypes.byref(rate), ctypes.sizeof(rate)):
        raise ctypes.WinError(ctypes.get_last_error())
    return job


def assign(job, pid: int) -> bool:
    h = kernel32.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
    if not h:
        return False
    try:
        return bool(kernel32.AssignProcessToJobObject(job, h))
    finally:
        kernel32.CloseHandle(h)


def peak_job_gb(job) -> float:
    info = _ExtendedLimit()
    kernel32.QueryInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info), None)
    return info.PeakJobMemoryUsed / 2**30


def is_ai_process(name: str, exe: str, cmd: str) -> bool:
    """Pure: does this process belong in the job?"""
    name, low = name.lower(), f"{exe} {cmd}".lower().replace("\\", "/")
    if name not in AI_NAMES or any(w in low for w in OUTSIDE):
        return False
    if name == "claude.exe" and "/anthropicclaude/" in low:
        return False  # the desktop app window, not an AI worker
    return True


def gpu_should_rest(util: int | None, temp: int | None, over_since: float | None, now: float
                    ) -> tuple[bool, float | None]:
    """Pure: (rest now, new over-since). Too hot rests at once; busy only after GPU_OVER_S."""
    if temp is not None and temp >= GPU_TEMP_C:
        return True, over_since
    if util is None or util < GPU_PCT:
        return False, None
    since = over_since or now
    return now - since >= GPU_OVER_S, since


def gpu_sample() -> tuple[int | None, int | None, int | None]:
    """(utilisation %, temperature C, memory MB)."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,memory.used",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=8,
                           creationflags=NO_WINDOW)
        a, b, c = (int(x) for x in r.stdout.split("\n")[0].split(","))
        return a, b, c
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None, None


def disk_pct(path: str) -> float | None:
    try:
        return psutil.disk_usage(path).percent
    except OSError:
        return None


def sweep(job, done: set[int], trees: dict[int, object]) -> tuple[int, int, int]:
    """Puts AI processes that are not in a job yet into one; (shared job, own job, refused)."""
    added = own = refused = 0
    alive = set()
    for p in psutil.process_iter(["pid", "name"]):
        pid, name = p.info["pid"], p.info["name"] or ""
        alive.add(pid)
        if pid in done or name.lower() not in AI_NAMES:
            continue
        try:
            exe, cmd = p.exe(), " ".join(p.cmdline())
        except (psutil.Error, OSError):
            continue
        if not is_ai_process(name, exe, cmd):
            done.add(pid)
        elif assign(job, pid):
            done.add(pid)
            added += 1
        else:
            done.add(pid)
            tree = create_job(None, TREE_CPU_PCT, TREE_MEMORY_GB * 2**30)
            if assign(tree, pid):
                trees[pid] = tree
                own += 1
            else:
                kernel32.CloseHandle(tree)
                refused += 1
    done &= alive
    for pid in set(trees) - alive:
        kernel32.CloseHandle(trees.pop(pid))
    return added, own, refused


def gpu_processes() -> list[psutil.Process]:
    return [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() in GPU_NAMES]


def rest_gpu() -> int:
    procs = gpu_processes()
    STATE_REST = [p.pid for p in procs]
    _write_state({"resting": STATE_REST})
    for p in procs:
        try:
            p.suspend()
        except psutil.Error:
            pass
    try:
        time.sleep(GPU_REST_S)
    finally:
        for p in procs:
            try:
                p.resume()
            except psutil.Error:
                pass
        _write_state({"resting": []})
    return len(procs)


def resume_left_over() -> None:
    """A watcher that died mid-rest must not leave a model server frozen."""
    try:
        pids = json.loads(STATE.read_text(encoding="utf-8")).get("resting") or []
    except (OSError, ValueError):
        return
    for pid in pids:
        try:
            psutil.Process(pid).resume()
        except psutil.Error:
            pass


def _write_state(d: dict) -> None:
    try:
        STATE.write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def write_log(line: str) -> None:
    try:
        if LOG.exists() and LOG.stat().st_size > LOG_MAX:
            LOG.replace(LOG.with_suffix(".log.1"))
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def sample(job, done: set[int], trees: dict[int, object]) -> dict:
    util, temp, vram = gpu_sample()
    added, own, refused = sweep(job, done, trees)
    return {"cpu": round(psutil.cpu_percent(interval=1)), "mem": round(psutil.virtual_memory().percent),
            "gpu": util, "gpu_c": temp, "vram_mb": vram, "c_disk": disk_pct("C:\\"), "d_disk": disk_pct("D:\\"),
            "job_peak_gb": round(peak_job_gb(job), 1), "added": added, "own": own, "refused": refused}


def line(s: dict) -> str:
    return (f"{time.strftime('%Y-%m-%d %H:%M:%S')} cpu {s['cpu']}% mem {s['mem']}% gpu {s['gpu']}% {s['gpu_c']}C "
            f"vram {s['vram_mb']}MB C: {s['c_disk']}% D: {s['d_disk']}% job_peak {s['job_peak_gb']}GB "
            f"+{s['added']} own +{s['own']} refused {s['refused']}")


def running() -> bool:
    _setup_api()
    h = kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
    if h:
        kernel32.CloseHandle(h)
    return bool(h)


def ensure_running() -> bool:
    """dispatch_tick calls this; True when it had to start the watcher."""
    if running():
        return False
    exe = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(exe), str(Path(__file__).resolve())], cwd=str(ROOT),
                     creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | NEW_PROCESS_GROUP
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    _setup_api()
    if "--once" in argv:
        job = create_job(JOB_NAME, CPU_PCT, JOB_MEMORY_GB * 2**30)
        print(line(sample(job, set(), {})))
        return 0
    mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not mutex or ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return 0
    resume_left_over()
    job = create_job(JOB_NAME, CPU_PCT, JOB_MEMORY_GB * 2**30)
    write_log(f"{time.strftime('%Y-%m-%d %H:%M:%S')} start: job cpu {CPU_PCT}% memory {JOB_MEMORY_GB}GB")
    done: set[int] = set()
    trees: dict[int, object] = {}
    over_since = None
    while True:
        s = sample(job, done, trees)
        write_log(line(s))
        rest, over_since = gpu_should_rest(s["gpu"], s["gpu_c"], over_since, time.time())
        if rest:
            write_log(f"{time.strftime('%Y-%m-%d %H:%M:%S')} gpu rest: {rest_gpu()} server(s) for {GPU_REST_S}s")
            over_since = None
        time.sleep(TICK_S)


if __name__ == "__main__":
    sys.exit(main())
