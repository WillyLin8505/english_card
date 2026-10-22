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
    subprocess.Popen(["cmd.exe", "/k", f"title {title} & {command}"], cwd=cwd, creationflags=NEW_CONSOLE)


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
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'tagging_server.py' }"
                        " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                       capture_output=True, timeout=60, creationflags=NO_WINDOW)
        console("tagger", r"tagger\start_tagger.bat", ROOT)
        started.append("tagger + llama-server (llama-server had stopped)")
    if started:
        log(f"watchdog: started {', '.join(started)}")
    return started


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(ensure_all() or "all up")
