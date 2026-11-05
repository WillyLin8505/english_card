"""Owner 10/31 (the PC powered off under AI load); 11/02: the whole PC stays under 80 % CPU and 80 % GPU
(11/01 tried 50 %: work crawled).

One long-running process (started by dispatch_tick, so nothing to install):
- 11/04 (the PC shut down again): the limits are set through Process Governor (procgov, PgJob) when it is
  installed; Process Lasso trims memory once RAM passes 80 %. Without procgov it falls back to its own jobs.
- keeps a Windows Job Object that every AI process joins within 10 s: CPU hard cap, memory limit
  JOB_MEMORY_GB, below-normal priority. Windows enforces these: over the memory limit an
  allocation fails and that AI process stops; the PC does not.
- Claude and Codex CLIs already sit in a job of their own and cannot join that one; each gets a
  job of its own instead (TREE_CPU_PCT, TREE_MEMORY_GB), which its child processes inherit.
- the caps add up to AI_BUDGET_PCT at most: half for the shared job, half split among the CLI jobs
  (tree_cap). Every 10 s all of them are scaled down while the whole PC is near CPU_PCT, and back up
  when it is well below (cpu_scale).
- GPU has no such cap: while it is busy the model servers run in short bursts, GPU_ON_S on and
  GPU_OFF_S suspended (gpu_pacing; the `--pace` process, owner 11/05). Too hot suspends them for GPU_REST_S. They carry on
  afterwards; requests just wait.
- writes one line every 10 s to lexicon/logs/ai_watch.log, so the last line before a crash says
  what the PC was doing.

    pythonw lexicon/tools/ai_watch.py          # the watcher
    python lexicon/tools/ai_watch.py --once    # one sample and sweep, print it
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "lexicon" / "logs" / "ai_watch.log"
STATE = ROOT / "lexicon" / "state" / "ai_watch.json"
HANDLED = ROOT / "lexicon" / "state" / "ai_watch_handled.json"
# owner 11/05: the bursts ran as a thread of this watcher and lost the GIL to its process sweeps (3 CLIs ??# hundreds of processes), so the GPU sat at 100 % while the log said gpu-bursts. They now run in their own
# process (`ai_watch.py --pace`): PACE lists the pids to pace and until when, PACE_BEAT is its heartbeat.
PACE = ROOT / "lexicon" / "state" / "ai_watch_pace.json"
PACE_BEAT = ROOT / "lexicon" / "state" / "ai_watch_pace.beat"
PACE_HOLD_S = 30  # a watcher that stops writing PACE stops the pacing within this time
JOB_NAME = "Local\\EnglishCardAI"
MUTEX_NAME = "Local\\EnglishCardAIWatch"
NO_WINDOW = 0x08000000

CPU_PCT = 80  # owner 11/02: the whole PC, not only the AI processes
AI_BUDGET_PCT = 76  # every AI cap together; the rest of CPU_PCT is for the owner's own programs
CPU_HIGH_PCT = 72
CPU_LOW_PCT = 60
MIN_SCALE = 0.1
# 80 % of 63 GB less what stays outside the job: serve_app (~12 GB) and Windows' own use.
JOB_MEMORY_GB = 42
# Per CLI at most; tree_cap splits half of AI_BUDGET_PCT among the CLIs running, but never below
# TREE_MIN_PCT: an even split among 49 jobs (0.45 % each) made a test run take 7 minutes instead of 24 s.
# Above the budget, cpu_scale pulls every cap down while the PC is actually busy.
TREE_CPU_PCT = 12
TREE_MIN_PCT = 2
TREE_MEMORY_GB = 12
GPU_HIGH_PCT = 70
GPU_IDLE_PCT = 25  # the desktop alone is about 15 %
# 11/04: the PC shut down at GPU 100 % with 0.7 s on / 0.3 s off; half the time off now.
# owner 11/05: the PC powered off again after 8 min at GPU 100 % ??bursts are now 40 % on
GPU_ON_S = 0.4
GPU_OFF_S = 0.6
# owner 11/05: all three power-offs were bug check 0x116 VIDEO_TDR_FAILURE (the NVIDIA driver timed out and could not
# recover), each while the bursts were suspending llama-server mid-GPU-work. Suspending a process with GPU work in
# flight is a known TDR trigger, so the model servers are no longer suspended (bursts and rests off).
GPU_SUSPEND = False
GPU_STUCK_PCT = 90  # this high for GPU_STUCK_SAMPLES samples while bursting = the bursts don't work
GPU_STUCK_SAMPLES = 3
GPU_TEMP_C = 85
GPU_REST_S = 20
TICK_S = 10
LOG_MAX = 5_000_000

# 11/02: no model servers. In a capped job llama-server stalled while loading and made about 1 token/s
# (card #931); outside one the same model loads in 15 s. GPU bursts keep the GPU in check instead.
AI_NAMES = {"claude.exe", "codex.exe", "cursor-agent.exe", "cursor.cmd",
            "dart.exe", "dartaotruntime.exe", "flutter_tester.exe", "node.exe", "python.exe", "pythonw.exe"}
GPU_NAMES = {"llama-server.exe"}
# Services the App and board need, the desktop app itself, and this watcher.
OUTSIDE = ("serve_app", "uvicorn app.main", "keep_awake", "ai_watch", "vite", "dispatch_tick")

PG_JOB_NAME = "EnglishCardAI-procgov"
_WINGET_PG = Path.home() / "AppData/Local/Microsoft/WinGet/Packages" / \
    "LowLevelDesign.ProcessGovernor_Microsoft.Winget.Source_8wekyb3d8bbwe" / "procgov.exe"
# owner 11/04: limits through Process Governor (winget LowLevelDesign.ProcessGovernor); without it, our own jobs.
# Never `procgov --install`: its service would take the name of Process Lasso's core service, ProcessGovernor.
PROCGOV = shutil.which("procgov") or (str(_WINGET_PG) if _WINGET_PG.exists() else None)
_jobs = 0

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None
scale = 1.0  # share of the CPU caps in force now
paced: list[psutil.Process] = []  # model servers the --pace process runs in bursts


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


class PgJob:
    """owner 11/04: Process Governor (procgov) sets the limits. Its first call starts a monitor process
    that keeps the job; a later call with the same --job-name adds a process or changes the cap."""

    def __init__(self, name: str, cpu_pct: float, memory_bytes: int):
        self.name, self.cpu, self.memory, self.pids = name, max(1, round(cpu_pct)), memory_bytes, []

    def _run(self, pid: int, *limits: str) -> bool:
        try:
            # No pipes: the monitor procgov leaves running would hold them open.
            return subprocess.run([PROCGOV, "--nowait", "-q", "--job-name", self.name, *limits, "-p", str(pid)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=30, creationflags=NO_WINDOW).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def add(self, pid: int) -> bool:
        ok = self._run(pid, "--cpurate", str(self.cpu), "--maxjobmem", f"{self.memory // 2**20}M",
                       "--priority", "BelowNormal")
        if ok:
            self.pids.append(pid)
        return ok

    def set_cpu(self, cpu_pct: float) -> None:
        cpu = max(1, round(cpu_pct))
        self.pids = [p for p in self.pids if psutil.pid_exists(p)]
        if cpu != self.cpu and self.pids and self._run(self.pids[0], "--cpurate", str(cpu)):
            self.cpu = cpu

    def memory_gb(self) -> float:
        total = 0
        for pid in self.pids:
            try:
                total += psutil.Process(pid).memory_info().private
            except psutil.Error:
                pass
        return total / 2**30


def close(job) -> None:
    if not isinstance(job, PgJob):
        kernel32.CloseHandle(job)


def create_job(name: str | None, cpu_pct: float, memory_bytes: int):
    """A job with a hard CPU cap, a total memory limit and below-normal priority."""
    if PROCGOV:
        global _jobs
        _jobs += 1
        return PgJob(f"{PG_JOB_NAME}-{os.getpid()}-{_jobs}" if name is None else PG_JOB_NAME, cpu_pct, memory_bytes)
    job = kernel32.CreateJobObjectW(None, name)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = _ExtendedLimit()
    limits.Basic.LimitFlags = 0x200 | 0x20  # JOB_MEMORY | PRIORITY_CLASS
    limits.Basic.PriorityClass = 0x4000  # BELOW_NORMAL
    limits.JobMemoryLimit = memory_bytes
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    set_cpu_cap(job, cpu_pct)
    return job


def set_cpu_cap(job, cpu_pct: float) -> None:
    if isinstance(job, PgJob):
        job.set_cpu(cpu_pct)
        return
    rate = _CpuRate(1 | 4, max(1, int(cpu_pct * 100)))  # ENABLE | HARD_CAP, in 1/100 of a percent
    if not kernel32.SetInformationJobObject(job, 15, ctypes.byref(rate), ctypes.sizeof(rate)):
        raise ctypes.WinError(ctypes.get_last_error())


def scaled(cpu_pct: float) -> float:
    return max(0.01, round(cpu_pct * scale, 2))


def shared_cap() -> float:
    return scaled(AI_BUDGET_PCT / 2)


def tree_cap(clis: int) -> float:
    """Pure but for scale: one CLI job's share, so that all of them together stay within half the budget.
    A CLI's processes that were running before this watcher each get a job of their own, so there are
    more jobs than CLIs."""
    return scaled(min(TREE_CPU_PCT, max(TREE_MIN_PCT, AI_BUDGET_PCT / 2 / max(1, clis))))


def assign(job, pid: int) -> bool:
    if isinstance(job, PgJob):
        return job.add(pid)
    h =kernel32.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
    if not h:
        return False
    try:
        return bool(kernel32.AssignProcessToJobObject(job, h))
    finally:
        kernel32.CloseHandle(h)


def peak_job_gb(job) -> float:
    if isinstance(job, PgJob):
        return job.memory_gb()  # now, not the peak: procgov keeps the job handle
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


def cpu_scale(cpu: int | None, current: float) -> float:
    """Pure: the share of the CPU caps for the next 10 s, from the whole PC's CPU %."""
    if cpu is None:
        return current
    if cpu >= CPU_HIGH_PCT:
        return max(MIN_SCALE, round(current * 0.7, 2))
    if cpu < CPU_LOW_PCT:
        return min(1.0, round(current + 0.1, 2))
    return current


def gpu_pacing(util: int | None, pacing: bool) -> bool:
    """Pure: run the model servers in bursts? Holds between the two limits, bursts keep util near them."""
    if util is None:
        return pacing
    if util >= GPU_HIGH_PCT:
        return True
    return False if util < GPU_IDLE_PCT else pacing


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


def dispatched_pids() -> set[int]:
    """The CLIs launch_agent started (card*.pid.json)."""
    pids = set()
    for f in (ROOT / "lexicon" / "logs" / "agents").glob("card*.pid.json"):
        try:
            pids.add(int(json.loads(f.read_text(encoding="utf-8"))["pid"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return pids


def in_session(p: psutil.Process, dispatched: set[int]) -> bool:
    """11/02: an interactive Claude session and what it runs are the owner's, never capped. Capping them
    left the manager session at 1 % CPU, a minute per command. Dispatched CLIs are capped as before."""
    try:
        chain = [p] + p.parents()
    except psutil.Error:
        return False
    for q in chain:
        if q.pid in dispatched:
            return False
        try:
            exe = q.exe().lower().replace("\\", "/")
        except (psutil.Error, OSError):
            continue
        if q.name().lower() == "claude.exe" and "/claude-code/" in exe:
            return True
    return False


def sweep(job, done: set[int], trees: dict[int, object]) -> tuple[int, int, int]:
    """Puts AI processes that are not in a job yet into one; (shared job, own job, refused)."""
    added = own = refused = 0
    alive = set()
    dispatched = dispatched_pids()
    for p in psutil.process_iter(["pid", "name"]):
        pid, name = p.info["pid"], p.info["name"] or ""
        alive.add(pid)
        if pid in done or name.lower() not in AI_NAMES:
            continue
        try:
            exe, cmd = p.exe(), " ".join(p.cmdline())
        except (psutil.Error, OSError):
            continue
        if not is_ai_process(name, exe, cmd) or in_session(p, dispatched):
            done.add(pid)
        elif assign(job, pid):
            done.add(pid)
            added += 1
        else:
            done.add(pid)
            tree = create_job(None, tree_cap(len(trees) + 1), TREE_MEMORY_GB * 2**30)
            if assign(tree, pid):
                trees[pid] = tree
                own += 1
            else:
                close(tree)
                refused += 1
    done &= alive
    for pid in set(trees) - alive:
        close(trees.pop(pid))
    save_handled(done)
    return added, own, refused


def save_handled(done: set[int]) -> None:
    """A restarted watcher must not put these into another job: limits of nested jobs only add up."""
    rows = {}
    for pid in done:
        try:
            rows[str(pid)] = psutil.Process(pid).create_time()
        except psutil.Error:
            pass
    try:
        HANDLED.write_text(json.dumps(rows), encoding="utf-8")
    except OSError:
        pass


def load_handled() -> set[int]:
    try:
        rows = json.loads(HANDLED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    kept = set()
    for pid, created in rows.items():
        try:
            if abs(psutil.Process(int(pid)).create_time() - created) < 1:  # pids get reused
                kept.add(int(pid))
        except (psutil.Error, ValueError):
            pass
    return kept


def gpu_users(top: int = 4) -> str:
    """Which processes use the GPU now (Windows GPU Engine counters), e.g. 'llama-server 88% dwm 12%'."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples"
                              " | Where-Object CookedValue -gt 1 | ForEach-Object { $_.InstanceName + '=' + [int]$_.CookedValue }"],
                             capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return "?"
    by_pid: dict[int, int] = {}
    for row in out.split():
        pid, _, pct = row.partition("=")
        if "pid_" in pid and pct.isdigit():
            n = int(pid.split("pid_")[1].split("_")[0])
            by_pid[n] = by_pid.get(n, 0) + int(pct)
    names = []
    for pid, pct in sorted(by_pid.items(), key=lambda kv: -kv[1])[:top]:
        try:
            names.append(f"{psutil.Process(pid).name().removesuffix('.exe')} {pct}%")
        except psutil.Error:
            names.append(f"pid{pid} {pct}%")
    return " ".join(names) or "-"


def gpu_processes() -> list[psutil.Process]:
    return [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() in GPU_NAMES]


def _suspend(procs: list[psutil.Process]) -> None:
    for p in procs:
        try:
            p.suspend()
        except psutil.Error:
            pass


def _resume(procs: list[psutil.Process]) -> None:
    for p in procs:
        try:
            p.resume()
        except psutil.Error:
            pass


def rest_gpu() -> int:
    procs = gpu_processes()
    _write_state({"resting": [p.pid for p in procs]})
    _suspend(procs)
    try:
        time.sleep(GPU_REST_S)
    finally:
        _resume(procs)
        _write_state({"resting": [p.pid for p in paced]})
    return len(procs)


def read_pace(now: float | None = None) -> list[int]:
    """Pids the watcher wants paced, [] when PACE is missing, unreadable or out of date."""
    try:
        d = json.loads(PACE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [int(p) for p in d.get("pids") or []] if (now or time.time()) < float(d.get("until") or 0) else []


def write_pace(pids: list[int]) -> None:
    try:
        PACE.write_text(json.dumps({"pids": pids, "until": time.time() + PACE_HOLD_S}), encoding="utf-8")
    except OSError:
        pass


def pace_main() -> int:
    """`ai_watch.py --pace`: its own process, so nothing else in the watcher can delay a burst.
    A second is short enough for GPU % to read as the average."""
    _setup_api()
    mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME + "-pace")
    if not mutex or ctypes.get_last_error() == 183:
        return 0
    procs: dict[int, psutil.Process] = {}
    while True:
        try:
            PACE_BEAT.write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass
        want = read_pace()
        for pid in [p for p in procs if p not in want]:
            del procs[pid]
        for pid in want:
            if pid not in procs:
                try:
                    procs[pid] = psutil.Process(pid)
                except psutil.Error:
                    pass
        if not procs:
            time.sleep(0.2)
            continue
        group = list(procs.values())
        _suspend(group)
        try:
            time.sleep(GPU_OFF_S)
        finally:
            _resume(group)
        time.sleep(GPU_ON_S)


def pace_alive() -> bool:
    try:
        return time.time() - float(PACE_BEAT.read_text(encoding="utf-8")) < 5
    except (OSError, ValueError):
        return False


def start_pacer() -> None:
    exe = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(exe), str(Path(__file__).resolve()), "--pace"], cwd=str(ROOT),
                     creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | NEW_PROCESS_GROUP
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def steer(job, trees: dict[int, object], s: dict) -> None:
    """Moves the CPU caps and the GPU bursts to what the last sample asks for."""
    global scale, paced
    scale = cpu_scale(s["cpu"], scale)
    set_cpu_cap(job, shared_cap())
    for tree in trees.values():  # the share changes with the number of CLIs too
        set_cpu_cap(tree, tree_cap(len(trees)))
    pacing = GPU_SUSPEND and gpu_pacing(s["gpu"], bool(paced))
    paced = gpu_processes() if pacing else []
    write_pace([p.pid for p in paced])
    if pacing != s["pacing"]:
        _write_state({"resting": [p.pid for p in paced]})


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
            "job_peak_gb": round(peak_job_gb(job), 1), "added": added, "own": own, "refused": refused,
            "cap": round(shared_cap() + tree_cap(len(trees)) * len(trees)), "pacing": bool(paced)}


def line(s: dict) -> str:
    return (f"{time.strftime('%Y-%m-%d %H:%M:%S')} cpu {s['cpu']}% mem {s['mem']}% gpu {s['gpu']}% {s['gpu_c']}C "
            f"vram {s['vram_mb']}MB C: {s['c_disk']}% D: {s['d_disk']}% job_peak {s['job_peak_gb']}GB "
            f"+{s['added']} own +{s['own']} refused {s['refused']} cap {s['cap']}%{' gpu-bursts' if s['pacing'] else ''}")


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
    if "--pace" in argv:
        return pace_main()
    if "--once" in argv:
        job = create_job(JOB_NAME, CPU_PCT, JOB_MEMORY_GB * 2**30)
        print(line(sample(job, set(), {})))
        return 0
    mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not mutex or ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return 0
    resume_left_over()
    job = create_job(JOB_NAME, shared_cap(), JOB_MEMORY_GB * 2**30)
    write_log(f"{time.strftime('%Y-%m-%d %H:%M:%S')} start: AI cpu {AI_BUDGET_PCT}% in all, memory {JOB_MEMORY_GB}GB")
    done: set[int] = load_handled()
    trees: dict[int, object] = {}
    write_pace([])
    stuck = 0
    while True:
        s = sample(job, done, trees)
        write_log(line(s) + (f" gpu-users {gpu_users()}" if (s["gpu"] or 0) >= 80 else ""))
        steer(job, trees, s)
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        # owner 11/05: on 11/04 08:00 and 11/05 21:40 the log said gpu-bursts while the GPU sat at 90-100 %
        # for minutes, then the PC powered off. Never trust the bursts: check the thread and the result.
        if not pace_alive():
            # a pacer that died mid-burst must not leave a model server frozen
            for p in gpu_processes():
                try:
                    p.resume()
                except psutil.Error:
                    pass
            write_log(f"{now} pacer not running ??started")
            start_pacer()
        stuck = stuck + 1 if paced and (s["gpu"] or 0) >= GPU_STUCK_PCT else 0
        if not GPU_SUSPEND:
            pass
        elif s["gpu_c"] is not None and s["gpu_c"] >= GPU_TEMP_C:
            write_log(f"{now} gpu rest: {rest_gpu()} server(s) for {GPU_REST_S}s")
        elif stuck >= GPU_STUCK_SAMPLES:
            write_log(f"{now} gpu still {s['gpu']}% with bursts ({stuck} samples) ??rest: "
                      f"{rest_gpu()} server(s) for {GPU_REST_S}s; gpu-users {gpu_users()}")
            stuck = 0
        time.sleep(TICK_S)


if __name__ == "__main__":
    sys.exit(main())
