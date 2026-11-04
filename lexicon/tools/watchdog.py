"""Brings back the local services the public site and the dispatcher need (owner 10/22:
「保持網路 不要斷掉了」). dispatch_tick runs ensure_all() at the start of every tick, before it
reads the board, so a crashed API no longer stops dispatching for hours.

Each service is started the same way the owner starts it, and only when it is down and its
starter is not already running (a starter still warming up is left alone):
  keep_awake.py · cloudflared tunnel english-card · lexicon API (run_api.bat) · admin UI (vite)
  · App + studio (start_services.py) · tagger + llama-server (tagger/start_tagger.bat, only when
  neither runs — never a second llama-server).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEX = ROOT / "lexicon"
CLOUDFLARED = Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe")
TUNNEL_CFG = Path.home() / ".cloudflared" / "english-card.yml"
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def port_up(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def cmdlines() -> list[str]:
    """Command lines of every process (lower-case); [] if they can't be read."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process | ForEach-Object { $_.Name + ' ' + $_.CommandLine }"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=60, creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.lower() for line in out.splitlines() if line.strip()]


def running(procs: list[str], *needles: str) -> bool:
    return any(all(n in p for n in needles) for p in procs)


def console(title: str, command: str, cwd: Path):
    # one raw command line: a list would escape the inner quotes as \" and cmd can't run them
    # (10/23: the worker windows opened but never started a worker)
    subprocess.Popen(f'cmd.exe /k "title {title} & {command}"', cwd=cwd, creationflags=NEW_CONSOLE)


def ensure_all(log=print) -> list[str]:
    procs = cmdlines()
    if not procs:
        log("watchdog: process list unavailable → skip")
        return []
    started = []
    if not running(procs, "keep_awake.py"):
        subprocess.Popen([sys.executable.replace("python.exe", "pythonw.exe"), str(Path(__file__).with_name("keep_awake.py"))],
                         cwd=ROOT, creationflags=DETACHED)
        started.append("keep_awake")
    if not running(procs, "cloudflared", "english-card") and CLOUDFLARED.exists():
        subprocess.Popen([str(CLOUDFLARED), "tunnel", "--config", str(TUNNEL_CFG), "run", "english-card"],
                         cwd=ROOT, creationflags=DETACHED | NO_WINDOW)
        started.append("cloudflared tunnel")
    if not port_up(8770) and not running(procs, "uvicorn", "app.main:app") and not running(procs, "run_api.bat"):
        console("lexicon API", f'"{LEX / "run_api.bat"}"', LEX)
        started.append("lexicon API")
    # the 9 lexicon workers (start_lexicon.bat's lanes): 4 text, 2 images, 3 picture labels
    for lane, want in (("text", 4), ("images", 2), ("tags", 3)):
        have = sum(1 for p in procs if p.startswith("cmd.exe") and "run_worker.bat" in p and p.rstrip().rstrip('"').endswith(" " + lane))
        for n in range(have, want):
            console(f"lexicon {lane} {n + 1}", rf'"{LEX / "worker" / "run_worker.bat"}" {lane}', LEX)
            started.append(f"worker {lane}")
    if not port_up(5173) and not running(procs, "vite", "5173"):
        console("lexicon UI", "npm --prefix frontend run dev", LEX)
        started.append("admin UI")
    if not (port_up(8123) and port_up(8772)) and not running(procs, "start_services.py"):
        subprocess.Popen([sys.executable, str(ROOT / "start_services.py")], cwd=ROOT,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=NO_WINDOW)
        started.append("App + studio")
    if (not port_up(8765) and not running(procs, "tagging_server.py")
            and not running(procs, "llama-server") and not running(procs, "start_llm.py")):
        console("tagger", r"tagger\start_tagger.bat", ROOT)
        started.append("tagger + llama-server")
    elif port_up(8765) and not port_up(8790) and not running(procs, "llama-server") and not running(procs, "start_llm.py"):
        # llama-server died under a live tagger (#445): restart the pair the one allowed way
        kill_matching(r"tagging_server\.py")
        console("tagger", r"tagger\start_tagger.bat", ROOT)
        started.append("tagger + llama-server (llama-server had stopped)")
    if started:
        log(f"watchdog: started {', '.join(started)}")
    return started


def http_ok(url: str, timeout: float = 15) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def kill_matching(pattern: str):
    """Stops every process whose command line matches `pattern` (PowerShell -match), and its cmd /k window."""
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    # $PID: this PowerShell's own command line contains the pattern too
                    f"Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -ne $PID -and $_.CommandLine -match '{pattern}' }}"
                    " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW)


def restart_hung(log=print) -> list[str]:
    """Owner 11/04: the API sat hung from 09:17 to 22:00 (port open, nothing answered), so ensure_all,
    which only restarts stopped services, never acted and dispatch stood still for 12 hours.
    dispatch_tick calls this after the board has failed several ticks in a row: a service whose port
    is open but whose HTTP check fails is stopped and started again the usual way."""
    restarted = []
    if port_up(8770) and not http_ok("http://127.0.0.1:8770/health"):
        kill_matching(r"uvicorn app\.main:app|run_api\.bat")
        console("lexicon API", f'"{LEX / "run_api.bat"}"', LEX)
        restarted.append("lexicon API (8770 hung)")
    if port_up(5173) and not http_ok("http://127.0.0.1:5173/"):
        # only lexicon's UI: other projects run their own vite / npm run dev (photo_tidy_up on 5180)
        kill_matching(r"english_card\\lexicon\\frontend.*vite|--port 5173 --strictPort|--prefix frontend run dev")
        console("lexicon UI", "npm --prefix frontend run dev", LEX)
        restarted.append("admin UI (5173 hung)")
    if restarted:
        log(f"watchdog: restarted {', '.join(restarted)}")
    return restarted


OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_LOG = Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "server.log"


def ollama_resident() -> list[str]:
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=5) as r:
            return [m.get("name") or m.get("model") for m in json.loads(r.read()).get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def ollama_idle_minutes(log_path: Path = OLLAMA_LOG) -> float:
    """Minutes since Ollama last answered a POST (its server.log); inf when unknown."""
    import re
    from datetime import datetime
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
    except OSError:
        return float("inf")
    for line in reversed(lines):
        m = re.match(r"\[GIN\] (\d{4}/\d\d/\d\d - \d\d:\d\d:\d\d) .*POST", line)
        if m:
            at = datetime.strptime(m.group(1), "%Y/%m/%d - %H:%M:%S")
            return (datetime.now() - at).total_seconds() / 60
    return float("inf")


def ollama_unload(name: str):
    import json
    import urllib.request
    req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps({"model": name, "keep_alive": 0}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).close()
    except Exception:  # noqa: BLE001
        pass


def restart_llama_server():
    """Restarts only our llama-server (child of tagger/start_llm.py, port 8790) — never Ollama's own runner,
    also named llama-server.exe — and starts start_llm.py again (it refuses if one already answers)."""
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "$py = Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'start_llm\\.py' };"
                    " $ids = @($py.ProcessId) + @($py.ParentProcessId) + @(Get-CimInstance Win32_Process -Filter \"Name='llama-server.exe'\""
                    " | Where-Object { $py.ProcessId -contains $_.ParentProcessId } | ForEach-Object { $_.ProcessId });"
                    " $ids | Where-Object { $_ } | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW)
    console("LLM server", f'python "{ROOT / "tagger" / "start_llm.py"}"', ROOT / "tagger")


def free_gpu_for_qwen(fails: int, log=print, idle_min: float = 5) -> list[str]:
    """Owner 11/05 (「好，卸載它」): photo_tidy_up's Ollama keeps qwen3-vl in the 8 GB GPU forever
    (OLLAMA_KEEP_ALIVE=-1); with it loaded our llama-server stalled from 23:11 to 04:46 and the
    fill cards filled nothing. Called with the number of failed Qwen health checks in a row:
    at 2, an Ollama model idle ≥ idle_min minutes is unloaded (it reloads when photo_tidy_up asks
    again); at 4, still stuck, our llama-server is restarted the start_llm.py way."""
    done = []
    if fails == 2:
        names = ollama_resident()
        if names and ollama_idle_minutes() >= idle_min:
            for n in names:
                ollama_unload(n)
            done.append(f"unloaded Ollama {', '.join(names)}")
    elif fails == 4 and port_up(8790):
        restart_llama_server()
        done.append("restarted llama-server")
    if done:
        log(f"watchdog: Qwen stuck ({fails} checks): {'; '.join(done)}")
    return done


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(ensure_all() or "all up")
