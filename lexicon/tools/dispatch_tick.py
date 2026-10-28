"""Deterministic board dispatcher (zero LLM tokens). Run by Windows Task Scheduler every 20 min.

    python lexicon/tools/dispatch_tick.py              # one tick
    python lexicon/tools/dispatch_tick.py --dry-run    # show what it would do; changes nothing

Each tick (owner, 2026-10-18 — cut Grokbot's token use to <= 1/5):
 1. Grokbot paused on the board → do nothing.
 2. For every running card of Claude Code / Codex / Cursor CLI: finished (card<id>.result.md newer
    than the launch and the process gone / quiet for finish_grace_minutes) → done (once), next run
    (recurring) or back to queued (multi-round); result renamed card<id>.rN.result.md for repeat cards.
    Process gone without result.md → usage LIMIT (log) → card queued + agent rested until its reset;
    otherwise a failure (queued; blocked after max_failures).
 3. Cards in unblock_after whose blockers are done → queued.
 4. Quota from /api/schedule/agents-info (>=100 % with a future reset) → rested until the reset;
    exhausted agents are not re-checked before that time.
 5. Ungraded cards → grade_cards.py.
 6. Each idle agent with quota, not paused: pick_card.candidates (difficulty, night window, skip
    lists, never another AI's card) + reserved/prefer lists + 12 h cooldown for standing cards +
    no night card after night_last_launch → claim → prompt from dispatch_prompt_template.md →
    launch_agent.py.
 6b. Issue swarm (owner, 2026-10-18): every new 問題回報 card gets its own new Claude CLI
    ("Claude CLI <slot>", one card each, at most issue_swarm.max_parallel at once, sharing
    Claude Code's quota/limit). A finished issue card also marks its issues fixed.
 7. Heartbeats for the four bots; card #13 progress gets one line (only when it changes / every 2 h).
 8. serve_app (8123) running older code than lexicon/backend/app, lexicon/quality, serve_app.py or
    lexicon_transport.py → restarted once the change has settled (card #522, serve_app_reload).
 Notable events only → lexicon/state/dispatch_events.jsonl (read by dispatch_digest.py).
 State: lexicon/state/dispatch_state.json · log: lexicon/logs/dispatch_tick.log · lock: dispatch_tick.lock.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
ROOT = TOOLS.parents[1]
STATE_DIR = ROOT / "lexicon" / "state"
AG_LOGS = ROOT / "lexicon" / "logs" / "agents"
STATE_FILE = STATE_DIR / "dispatch_state.json"
EVENTS_FILE = STATE_DIR / "dispatch_events.jsonl"
LOCK_FILE = STATE_DIR / "dispatch_tick.lock"
LOG_FILE = ROOT / "lexicon" / "logs" / "dispatch_tick.log"
CONFIG_FILE = TOOLS / "dispatch_config.json"
TEMPLATE_FILE = TOOLS / "dispatch_prompt_template.md"
API = "http://127.0.0.1:5173/api"
TAIPEI = timezone(timedelta(hours=8))
AGENTS = ["Claude Code", "Codex", "Cursor CLI"]
SWARM_PREFIX = "Claude CLI "
CODEX_PREFIX = "Codex CLI "  # owner 10/23: Codex has plenty of tokens — its own parallel CLIs
MAC_PREFIX = "[給 Mac]"


def is_swarm(agent: str | None) -> bool:
    """An issue-swarm CLI: "Claude CLI 3" (Claude Code's quota) or "Codex CLI 2" (Codex's)."""
    return bool(agent) and any(agent.startswith(p) and agent[len(p):].isdigit()
                               for p in (SWARM_PREFIX, CODEX_PREFIX))


def is_card_alias(agent: str | None) -> bool:
    """A launched CLI that renamed itself on the board ("Claude · card385", via task.py) —
    still ours to collect, or its card would sit in_progress forever."""
    return bool(agent) and re.fullmatch(r"Claude · card\d+|Claude CLI", agent) is not None


def quota_agent(agent: str) -> str:
    if agent.startswith(CODEX_PREFIX):
        return "Codex"
    return "Claude Code" if is_swarm(agent) or is_card_alias(agent) else agent


def free_slot(used: set[str], limit: int, prefix: str = SWARM_PREFIX) -> str | None:
    for n in range(1, limit + 1):
        if f"{prefix}{n}" not in used:
            return f"{prefix}{n}"
    return None
NO_WINDOW = 0x08000000
BREAKAWAY = 0x01000000
LOG_CAP = 1_000_000
LOCK_STALE_S = 15 * 60
NO_DECISION_RE = re.compile(r"^[：:\s]*(無|沒有|none|n/?a)(?=[\s。.，,（(；;]|$)", re.I)


def real_decision(text: str) -> bool:
    """A 「需要你決定」 that actually asks something — cards sometimes write 「需要你決定：無。」
    (10/23: those opened empty [待決定] issues and parked finished cards)."""
    m = DECISION_RE.search(text[:800])
    return bool(m) and not NO_DECISION_RE.match(text[m.end():m.end() + 40])


OPTION_RE = re.compile(r"^\s*(?:選項\s*)?([A-Ca-c1-3])\s*[\.、：:．)）]\s*(.+)$")


def decision_options(block: str) -> list[str]:
    """owner 10/26: 問題回報頁上的決定要一眼看懂、最多三個選項可以點選，另有「其他」欄位。
    The card's lines 「A：…」／「1. …」 become at most 3 buttons; the one its 「建議：X」 names is
    marked （建議）."""
    opts, keys = [], []
    for line in block.splitlines():
        m = OPTION_RE.match(line)
        if m and len(opts) < 3:
            keys.append(m.group(1).upper())
            opts.append(m.group(2).strip()[:120])
    rec = re.search(r"建議[：:]\s*(?:選項\s*)?([A-Ca-c1-3])", block)
    if rec and rec.group(1).upper() in keys:
        k = keys.index(rec.group(1).upper())
        opts[k] = opts[k] + "（建議）"
    return [f"{n + 1}. {o}" for n, o in enumerate(opts)]


DECISION_RE = re.compile(r"需要你決定|待你決定|請你決定|需使用者決定|需要使用者決定|decision needed|needs owner", re.I)
ALL_DONE_RE = re.compile(r"^\s*(全部完成|ALL DONE)", re.I | re.M)
BLOCKER_RE = re.compile(r"^\s*(BLOCKED|卡住|無法完成)", re.I | re.M)

DEFAULT_CFG = {
    "agents_order": AGENTS, "prefer": {}, "reserved": {}, "multi_round_tasks": [],
    "unblock_after": {}, "cooldown_hours": 12, "night_last_launch": "06:15",
    "night_safe_stop": "06:45", "finish_grace_minutes": 10, "alive_log_minutes": 45,
    "finish_grace_alive_minutes": 45, "lingering_kill_minutes": 90,
    "limit_fallback_hours": {}, "max_failures": 2, "note_task": 13, "note_refresh_minutes": 120,
    "probe_cmd": {}, "probe_interval_minutes": 60,
}


# ── small helpers ────────────────────────────────────────────────────

def now_tp() -> datetime:
    return datetime.now(TAIPEI)


def parse_iso(s) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=TAIPEI)


def hm(d: datetime | None) -> str:
    if not d:
        return "?"
    d = d.astimezone(TAIPEI)
    return d.strftime("%H:%M") if d.date() == now_tp().date() else d.strftime("%m/%d %H:%M")


_log_lines: list[str] = []


def log(msg: str):
    line = f"{now_tp():%Y-%m-%d %H:%M:%S} {msg}"
    _log_lines.append(line)
    if sys.stdout is not None:
        try:
            print(line)
        except Exception:  # noqa: BLE001
            pass


def flush_log():
    if not _log_lines:
        return
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_CAP:
            old = LOG_FILE.with_suffix(".log.1")
            if old.exists():
                old.unlink()
            LOG_FILE.rename(old)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write("\n".join(_log_lines) + "\n")
    except OSError:
        pass
    _log_lines.clear()


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def load_config() -> dict:
    cfg = dict(DEFAULT_CFG)
    cfg.update({k: v for k, v in load_json(CONFIG_FILE, {}).items() if not k.startswith("_")})
    return cfg


# ── lock ─────────────────────────────────────────────────────────────

def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def acquire_lock(path: Path = LOCK_FILE, stale_s: int = LOCK_STALE_S) -> bool:
    """True if we hold the lock. A lock older than stale_s or whose pid is dead is taken over."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "at": time.time()}, f)
            return True
        except FileExistsError:
            info = load_json(path, {})
            age = time.time() - float(info.get("at") or 0)
            if age > stale_s or not pid_alive(info.get("pid")):
                try:
                    path.unlink()
                except OSError:
                    return False
                continue
            return False
    return False


def release_lock(path: Path = LOCK_FILE):
    info = load_json(path, {})
    if info.get("pid") == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass


# ── pure decision logic (tested) ─────────────────────────────────────

def classify_run(launched_at: float, result_mtime: float | None, alive: bool | None,
                 limit_line: str | None, now: float, grace_s: float = 600) -> str:
    """'finished' | 'running' | 'limit' | 'failed' | 'unknown'."""
    if result_mtime is not None and result_mtime >= launched_at - 60:
        if alive is False or now - result_mtime > grace_s:
            return "finished"
        return "running"
    if alive is None:
        return "unknown"
    if alive:
        return "running"
    return "limit" if limit_line else "failed"


def prior_cli_action(alive: bool, last_activity: float | None, now: float, kill_after_s: float) -> str:
    """'free' | 'wait' | 'kill' for a card whose previous CLI may still run (card #431): while it is
    alive the card is not launched again; quiet (log and result.md) for kill_after_s → it is hung."""
    if not alive:
        return "free"
    if last_activity is not None and now - last_activity > kill_after_s:
        return "kill"
    return "wait"


def in_cooldown(card: dict, now: datetime, hours: float, agent_names=()) -> bool:
    """A standing card that ran less than `hours` ago and nothing changed since (owner edits or a
    detail change count as a change) is skipped."""
    if card.get("kind") != "recurring":
        return False
    last = parse_iso(card.get("last_run_at"))
    if not last or now - last >= timedelta(hours=hours):
        return False
    for h in card.get("history") or []:
        at = parse_iso(h.get("at"))
        if not at or at <= last:
            continue
        if h.get("by") == "owner" or any(c.get("field") == "detail" for c in h.get("changes") or []):
            return False
    return True


def night_launch_ok(task_id, night_tasks, now: datetime, last_launch: str) -> bool:
    """Night-only cards are not started after `last_launch` (they must stop before ~06:45)."""
    if task_id not in set(night_tasks or []):
        return True
    return now.astimezone(TAIPEI).strftime("%H:%M") < last_launch


def rest_until(agent: str, usage: dict, now: datetime) -> datetime | None:
    """Latest future reset among windows at >= 100 %, from /schedule/agents-info usage."""
    a = (usage.get("agents") or {}).get(agent) or {}
    best = None
    for w in ("five_hour", "weekly"):
        win = a.get(w) or {}
        pct, reset = win.get("used_percent"), parse_iso(win.get("resets_at"))
        if pct is not None and pct >= 100 and reset and reset > now:
            best = reset if best is None or reset > best else best
    return best


def reset_from_line(line: str, now: datetime) -> datetime | None:
    """「You've hit your session limit · resets 6:10am (Asia/Taipei)」 → the next 6:10 Taipei
    (10/23: without this a limit that reset at 06:10 kept the CLIs resting until 11:13)."""
    m = re.search(r"(?:resets|try again at)\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)", line, re.I)
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
    at = now.astimezone(TAIPEI).replace(hour=h, minute=int(m.group(2) or 0), second=0, microsecond=0)
    if at > now:
        return at
    # a session limit resets within ~5 h: a reset time a few hours back has already happened
    return now if now - at < timedelta(hours=6) else at + timedelta(days=1)


def probe_due(last_at, now_ts: float, interval_min: float) -> bool:
    """A live probe may run when none ran yet or the last one is older than interval_min."""
    return not last_at or now_ts - float(last_at) >= float(interval_min) * 60


def probe_verdict(returncode: int, out: str) -> bool:
    """True when a tiny live CLI call answered (so a usage-panel limit is stale)."""
    from launch_agent import detect_limit
    return returncode == 0 and "OK" in (out or "").upper() and not detect_limit(out or "")


def run_probe(cmd: list) -> bool:
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=180,
                           cwd=os.environ.get("TEMP") or None,
                           creationflags=NO_WINDOW if os.name == "nt" else 0)
    except Exception as e:  # noqa: BLE001
        log(f"probe {cmd[:1]} failed: {e}")
        return False
    return probe_verdict(r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace"))


def serve_app_reload_action(newest_change: float | None, unsettled: list[int], busy: list[int],
                            stale_since: float, now: float, cfg: dict) -> tuple[str, str]:
    """Card #522 / owner decision #553 = A: serve_app (8123) loads code + quality rules only at start-up.
    'ok' (nothing changed) · 'wait' (still being edited, a CLI that may be editing is still running,
    or a card that uses 8123 is running) · 'restart'. Past max_wait_hours the unsettled CLIs no longer
    hold it back (busy cards still do)."""
    if newest_change is None:
        return "ok", ""
    quiet = float(cfg.get("quiet_minutes", 15)) * 60
    if now - newest_change < quiet:
        return "wait", f"程式 {int((now - newest_change) // 60)} 分鐘前還在改"
    if busy:
        return "wait", "用 8123 的卡還在跑：" + "、".join(f"#{c}" for c in busy)
    if unsettled and now - stale_since < float(cfg.get("max_wait_hours", 6)) * 3600:
        return "wait", "改程式時就在跑的 CLI 還沒做完：" + "、".join(f"#{c}" for c in unsettled[:5])
    return "restart", ""


def order_candidates(cands: list[dict], agent: str, cfg: dict, now: datetime, taken: set,
                     night_tasks, full_cards: dict) -> list[dict]:
    reserved = {int(k): v for k, v in (cfg.get("reserved") or {}).items()}
    prefer = [int(x) for x in (cfg.get("prefer") or {}).get(agent, [])]
    out = []
    for c in cands:
        tid = c.get("task_id")
        key = c["key"]
        if key in taken:
            continue
        if tid is not None:
            if reserved.get(tid) not in (None, agent):
                continue
            if not night_launch_ok(tid, night_tasks, now, cfg["night_last_launch"]):
                continue
            card = full_cards.get(tid) or {}
            if in_cooldown(card, now, cfg["cooldown_hours"]):
                continue
        out.append(c)
    out.sort(key=lambda c: prefer.index(c["task_id"]) if c.get("task_id") in prefer else len(prefer))
    return out


def outcome_line(text: str, limit: int = 200) -> str:
    """First meaningful lines of a result.md: skip headings/blank, prefer a line with numbers."""
    lines = []
    for raw in text.splitlines():
        s = raw.strip().strip("|").strip()
        if not s or s.startswith("#") or set(s) <= set("-|: =*"):
            continue
        s = re.sub(r"[*`_]{1,3}", "", s)
        lines.append(re.sub(r"\s*\|\s*", " · ", s))
        if len(lines) >= 6:
            break
    if not lines:
        return ""
    first = lines[0]
    if not re.search(r"\d", first):
        num = next((l for l in lines[1:] if re.search(r"\d", l)), None)
        if num:
            first = f"{first}；{num}"
    return first[:limit]


def next_round_path(card_id: int, logs: Path = AG_LOGS) -> Path:
    ns = [int(m.group(1)) for p in logs.glob(f"card{card_id}.r*.result.md")
          if (m := re.fullmatch(rf"card{card_id}\.r(\d+)\.result\.md", p.name))]
    return logs / f"card{card_id}.r{max(ns, default=0) + 1}.result.md"


def latest_round_path(card_id: int, logs: Path = AG_LOGS) -> Path | None:
    best = None
    for p in logs.glob(f"card{card_id}.r*.result.md"):
        m = re.fullmatch(rf"card{card_id}\.r(\d+)\.result\.md", p.name)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), p)
    return best[1] if best else None


def render_prompt(task: dict, cfg: dict, night_tasks, template: str, prev: Path | None) -> str:
    kind = "常態卡（定期檢查）" if task.get("kind") == "recurring" else "一次性卡"
    prev_line = (f"上一輪結果：`{prev.relative_to(ROOT).as_posix()}`（只讀這一份，沿用上一輪的腳本）。"
                 if prev else "")
    night = ""
    if task.get("id") in set(night_tasks or []):
        night = (f"- 【夜間卡】只在 01:00–07:00（台北）跑：{cfg['night_safe_stop']} 前停在安全點，"
                 f"把進度與下一夜從哪裡續做寫進 result.md 再結束。")
    vals = {"id": task.get("id"), "title": task.get("title") or "", "detail": (task.get("detail") or "").strip(),
            "kind_line": kind, "difficulty": task.get("difficulty") or "?",
            "issue_ids": ", ".join(f"#{i}" for i in task.get("issue_ids") or []) or "無",
            "prev_result_line": prev_line, "night_line": night}
    out = template
    for k, v in vals.items():
        out = out.replace("{" + k + "}", str(v))
    return re.sub(r"\n{3,}", "\n\n", out)


# ── I/O ──────────────────────────────────────────────────────────────

def http(method: str, path: str, body: dict | None = None, timeout: int = 30):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


def process_cmdlines() -> list[tuple[int, str]] | None:
    """(pid, command line) of every process (Windows CIM); None if the query failed."""
    if os.name != "nt":
        return None
    ps = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    cmd = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process | "
           "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    try:
        r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True,
                           timeout=60, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        pid, _, cl = line.partition("\t")
        if pid.strip().isdigit():
            out.append((int(pid), cl))
    return out


def python_exe() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


class Tick:
    def __init__(self, dry: bool):
        self.dry = dry
        self.now = now_tp()
        self.cfg = load_config()
        self.state = load_json(STATE_FILE, {})
        for k in ("runs", "limits", "failures", "seen_limits"):
            self.state.setdefault(k, {})
        self.events: list[dict] = []
        self.summary: list[str] = []
        self._procs = "unset"
        from card_difficulty import load_capabilities
        self.caps = load_capabilities()
        self.night_tasks = self.caps.get("night_only_tasks", [])

    # events / writes
    def event(self, kind: str, **kw):
        e = {"t": self.now.isoformat(timespec="seconds"), "type": kind, **kw}
        self.events.append(e)
        log(f"EVENT {json.dumps(e, ensure_ascii=False)}")

    def write(self, method, path, body, what):
        if self.dry:
            log(f"DRY {method} {path} {json.dumps(body, ensure_ascii=False)[:200]}  # {what}")
            return {}
        return http(method, path, body)

    def procs(self):
        if self._procs == "unset":
            self._procs = process_cmdlines()
        return self._procs

    # 2. running cards
    def is_alive(self, card_id: int, agent: str, run: dict) -> bool | None:
        if run.get("pid"):
            if pid_alive(run["pid"]):
                return True
        procs = self.procs()
        needles = (f"card #{card_id}.", f"card{card_id}.cursor.prompt", f"card{card_id}.prompt")
        if procs is not None and any(any(n in cl for n in needles) for _, cl in procs):
            return True
        from launch_agent import agent_kind
        kind = agent_kind(agent)
        lg = AG_LOGS / f"card{card_id}_{kind}.log"
        if kind != "cursor" and lg.exists() and time.time() - lg.stat().st_mtime < self.cfg["alive_log_minutes"] * 60:
            return True
        if run.get("pid"):
            return False
        return None if procs is None else False

    def check_running(self, board: dict) -> bool:
        from launch_agent import agent_kind, detect_limit
        changed = False
        running = {}
        for b in board.get("bots", []):
            if b.get("agent") in AGENTS or is_swarm(b.get("agent")) or is_card_alias(b.get("agent")):
                for t in b.get("doing", []):
                    if t.get("status") == "in_progress":
                        running[str(t["id"])] = (b["agent"], t)
        # forget runs whose card is no longer in progress with that agent (someone else closed it)
        for cid in list(self.state["runs"]):
            if cid not in running:
                run = self.state["runs"][cid]
                res = AG_LOGS / f"card{cid}.result.md"
                if res.exists() and res.stat().st_mtime >= run["launched_at"] - 60:
                    log(f"#{cid}: closed on the board by someone else; recording its result")
                    self.finish(int(cid), run["agent"], {}, res)
                    changed = True
                else:
                    log(f"#{cid}: no longer in_progress on the board; dropping run record")
                self.state["runs"].pop(cid, None)
        for cid, (agent, t) in running.items():
            run = self.state["runs"].get(cid)
            if not run:
                st = parse_iso(t.get("started_at")) or self.now
                run = {"agent": agent, "pid": None, "launched_at": st.timestamp(), "adopted": True}
                self.state["runs"][cid] = run
                log(f"#{cid}: adopted running card of {agent} (started {hm(st)})")
            card_id = int(cid)
            res = AG_LOGS / f"card{card_id}.result.md"
            rm = res.stat().st_mtime if res.exists() else None
            lg = AG_LOGS / f"card{card_id}_{agent_kind(agent)}.log"
            log_text = lg.read_text(encoding="utf-8", errors="replace") if lg.exists() else ""
            alive = self.is_alive(card_id, agent, run)
            # a limit line in an old log (an adopted card from hours ago) says nothing about now
            fresh_log = lg.exists() and time.time() - lg.stat().st_mtime < 5 * 3600
            limit_line = detect_limit(log_text) if alive is False and fresh_log else None
            if alive and fresh_log and not rm and detect_limit(log_text) and run.get("pid"):
                # 10/24 #604: Codex printed its usage limit and then sat there for half an hour,
                # holding the card — end it and treat it as a limit
                subprocess.run(["taskkill", "/PID", str(run["pid"]), "/T", "/F"], capture_output=True)
                alive, limit_line = False, detect_limit(log_text)
            # the CLI we launched is still running after writing result.md: it may be rewriting it
            # (card #431), so wait longer before collecting the card
            pid_up = bool(run.get("pid")) and pid_alive(run["pid"])
            grace = self.cfg["finish_grace_alive_minutes" if pid_up else "finish_grace_minutes"]
            verdict = classify_run(run["launched_at"], rm, alive, limit_line, time.time(), grace * 60)
            log(f"#{cid} {agent}: {verdict} (alive={alive}, result={'yes' if rm else 'no'})")
            if verdict == "finished":
                self.finish(card_id, agent, t, res)
                changed = True
            elif verdict == "limit":
                self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": "queued", "agent": None,
                           "progress": f"{agent} 額度用完（dispatch_tick {hm(self.now)}），卡片排回待辦"}, "limit → queued")
                self.set_limit(quota_agent(agent), None, limit_line)
                self.state["runs"].pop(cid, None)
                changed = True
            elif verdict == "failed":
                n = self.state["failures"].get(cid, 0) + 1
                status = "blocked" if n >= self.cfg["max_failures"] else "queued"
                self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": status, "agent": None,
                           "progress": f"{agent} 結束但沒寫 result.md（第 {n} 次，dispatch_tick {hm(self.now)}）"
                                       f"，log：{lg.relative_to(ROOT).as_posix()}"}, f"failed → {status}")
                if not self.dry:
                    self.state["failures"][cid] = n
                self.event("error" if status == "queued" else "decision", card=card_id, agent=agent,
                           title=t.get("title", "")[:60],
                           outcome=f"結束但沒有 result.md（第 {n} 次）→ {status}",
                           log=lg.relative_to(ROOT).as_posix())
                self.state["runs"].pop(cid, None)
                changed = True
        return changed

    def finish(self, card_id: int, agent: str, t: dict, res: Path):
        text = res.read_text(encoding="utf-8", errors="replace")
        self.hand_to_mac(card_id, t, text)
        outcome = outcome_line(text)
        fresh = http("GET", f"/tasks/{card_id}")
        repeat = fresh.get("kind") == "recurring" or card_id in set(self.cfg["multi_round_tasks"])
        path = res
        if repeat:
            path = next_round_path(card_id)
            if not self.dry:
                res.rename(path)
        rel = path.relative_to(ROOT).as_posix()
        progress = f"{outcome}（dispatch_tick {hm(self.now)} 收卡；{rel}）"[:600]
        if fresh.get("status") != "in_progress" or fresh.get("agent") != agent:
            action = f"已由 {fresh.get('agent') or 'owner'} 改成 {fresh.get('status')}"
        elif real_decision(text):
            action = "waiting"
            self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": "waiting", "progress": progress}, "decision")
            self.ask_owner(card_id, fresh, text, rel)
        elif BLOCKER_RE.search(text[:800]):
            action = "blocked"
            self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": "blocked", "progress": progress}, "blocker")
        elif fresh.get("kind") == "recurring":
            action = "scheduled"
            self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": "done", "progress": progress}, "recurring done")
        elif card_id in set(self.cfg["multi_round_tasks"]) and ALL_DONE_RE.search(text[:200]):
            action = "done"
            self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": "done", "progress": progress},
                       "multi-round finished")
            self.close_issues(fresh, outcome, rel)
        elif card_id in set(self.cfg["multi_round_tasks"]):
            action = "queued"
            self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": "queued", "agent": None,
                                                     "progress": progress}, "next round")
        else:
            action = "done"
            self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": "done", "progress": progress}, "done")
            self.close_issues(fresh, outcome, rel)
        kind = {"waiting": "decision", "blocked": "blocker"}.get(action, "finished")
        self.event(kind, card=card_id, agent=agent, title=(t.get("title") or fresh.get("title") or "")[:60], action=action,
                   outcome=outcome, summary=re.sub(r"\s+", " ", text[:600]), result=rel)
        self.summary.append(f"#{card_id} 收卡→{action}")
        run = self.state["runs"].get(str(card_id)) or {}
        if run.get("pid") and pid_alive(run["pid"]):
            from launch_agent import live_run, record_run
            if not self.dry and not live_run(card_id):  # runs launched before card #431 had no pid file
                record_run(card_id, run.get("agent") or agent, run["pid"], run.get("launched_at"))
            log(f"#{card_id}: collected while its CLI (pid {run['pid']}) still runs; not relaunched until it ends")
        self.state["runs"].pop(str(card_id), None)
        self.state["failures"].pop(str(card_id), None)

    def close_issues(self, task: dict, outcome: str, rel: str):
        """A finished one-off card fixes its 問題回報 (agents are told not to change statuses)."""
        for iid in task.get("issue_ids") or []:
            try:
                i = http("GET", f"/issues/{int(iid)}")
            except Exception as e:  # noqa: BLE001
                log(f"issue #{iid}: GET failed ({e})")
                continue
            if i.get("status") in ("fixed", "wont_fix", "needs_decision"):
                continue
            self.write("PUT", f"/issues/{int(iid)}", {"status": "fixed", "by": "Grokbot",
                       "resolution": f"卡 #{task.get('id')}：{outcome}（{rel}）"[:600]}, "issue fixed")

    # 3. dependencies
    def ask_owner(self, card_id: int, task: dict, text: str, rel: str):
        """owner 10/21: every 「需要你決定」 is a decision issue on the 問題回報 page, where the owner answers."""
        if self.dry:
            return
        q = DECISION_RE.split(text, maxsplit=1)[-1].lstrip("：: ").split("\n")[0].strip()[:200]
        # owner 10/23: 「要我決定的問題 長話短說 最多300字 並且需要付上你的建議」 — only the card's
        # decision paragraph (question, options, 建議), cut at 300 characters; the rest stays in result.md
        block = DECISION_RE.split(text, maxsplit=1)[-1].lstrip("：: ").split("\n\n")[0].split("\n## ")[0].strip()
        if len(block) > 300:
            block = block[:299] + "…"
        if "建議" not in block:
            block += "\n（卡片沒寫建議，見完整結果）"
        detail = block + f"\n\n完整結果：{rel}｜在「決定」欄回答後，卡 #{card_id} 會照你的決定繼續。"
        try:
            body = {"kind": "decision", "severity": "high", "area": "app",
                    "title": f"[待決定] 卡 #{card_id}：{q}"[:300], "detail": detail, "reporter": "派工程式"}
            if decision_options(block):
                body["options"] = decision_options(block)
            i = http("POST", "/issues", body)
            asks = self.state.setdefault("asks", {})
            asks[str(i["id"])] = card_id
            log(f"#{card_id}: decision asked as issue #{i['id']}")
        except Exception as e:  # noqa: BLE001
            log(f"ask_owner #{card_id}: {e}")

    def prune_decisions(self) -> bool:
        """owner 10/26: 「已經修好的，就不要出現在等待我決定那個地方了」. A waiting decision whose card
        is finished (done／cancelled) or whose issues are all fixed, or that only says 「無」, is closed."""
        if self.dry:
            return False
        try:
            items = http("GET", "/issues").get("items", [])
            tasks = {t["id"]: t for t in http("GET", "/tasks").get("items", [])}
        except Exception as e:  # noqa: BLE001
            log(f"prune_decisions: {e}")
            return False
        status = {i["id"]: i.get("status") for i in items}
        changed = False
        asks = self.state.get("asks") or {}
        for i in items:
            title = str(i.get("title") or "")
            # 10/27: an answered decision with no waiting card kept its 「[待決定]」 title, so the
            # swarm skipped it for good (#485 #484 #556 #561 #558 #580). It becomes owner work.
            if (i.get("decision") and title.startswith("[待決定]") and str(i["id"]) not in asks
                    and i.get("status") in ("open", "needs_decision")):
                self.write("PUT", f"/issues/{i['id']}", {"by": "Grokbot", "status": "open",
                           "title": re.sub(r"^\[待決定\]\s*", "[owner] ", title)}, "answered decision → owner work")
                log(f"#{i['id']}: answered decision → [owner] issue")
                changed = True
                continue
            if (i.get("status") not in ("open", "needs_decision") or i.get("decision")
                    or not (i.get("kind") == "decision" or "[待決定]" in title)):
                continue
            m = re.search(r"卡 #(\d+)", title)
            card = tasks.get(int(m.group(1))) if m else None
            linked = [status.get(n) for n in (card or {}).get("issue_ids") or []]
            question = re.sub(r"^\[待決定\]\s*卡 #\d+[：:]", "", title)
            why = None
            if card and card.get("status") in ("done", "cancelled"):
                why = f"卡 #{card['id']} 已結束"
            elif linked and all(s in ("fixed", "wont_fix") for s in linked):
                why = "相關問題都已修好"
            elif NO_DECISION_RE.match(question):
                why = "卡片寫「無」，不需決定"
            if not why:
                continue
            self.write("PUT", f"/issues/{i['id']}", {"by": "Grokbot", "status": "wont_fix",
                       "resolution": f"不用你決定了：{why}（派工程式 {hm(self.now)} 自動移除）"}, "stale decision")
            if card and card.get("status") == "waiting":
                self.write("PUT", f"/tasks/{card['id']}", {"by": "Grokbot", "status": "queued", "agent": None,
                           "progress": f"不需 owner 決定（{why}），照原計畫做完"}, "decision not needed")
            self.state.get("asks", {}).pop(str(i["id"]), None)
            log(f"#{i['id']}: waiting decision removed — {why}")
            changed = True
        return changed

    def answered(self) -> bool:
        """A [待決定] issue the owner answered → its waiting card goes back to the queue with the answer."""
        asks = self.state.get("asks") or {}
        changed = False
        for iid, cid in list(asks.items()):
            try:
                i = http("GET", f"/issues/{int(iid)}")
            except Exception:  # noqa: BLE001
                continue
            if not i.get("decision") and i.get("status") not in ("fixed", "wont_fix"):
                continue
            asks.pop(iid, None)
            if self.dry:
                continue
            try:
                t = http("GET", f"/tasks/{cid}")
                if t.get("status") == "waiting":
                    self.write("PUT", f"/tasks/{cid}", {
                        "by": "Grokbot", "status": "queued", "agent": None,
                        "detail": (t.get("detail") or "") + f"\n\n【owner 決定（問題回報 #{iid}）】{i.get('decision') or i.get('resolution') or ''}",
                        "progress": f"owner 已在問題回報 #{iid} 決定，排回待辦"}, "answered")
                    changed = True
                self.write("PUT", f"/issues/{int(iid)}", {"by": "Grokbot", "status": "fixed",
                           "resolution": f"已回答，卡 #{cid} 照決定繼續"}, "ask closed")
                self.decision_to_mac(int(iid), i, t)
            except Exception as e:  # noqa: BLE001
                log(f"answered #{iid}: {e}")
        return changed

    def unblock(self, board: dict) -> bool:
        changed = False
        for cid, deps in (self.cfg.get("unblock_after") or {}).items():
            try:
                t = http("GET", f"/tasks/{int(cid)}")
            except Exception:  # noqa: BLE001
                continue
            if t.get("status") != "blocked":
                continue
            if all(http("GET", f"/tasks/{int(d)}").get("status") == "done" for d in deps):
                self.write("PUT", f"/tasks/{int(cid)}", {"by": "Grokbot", "status": "queued", "agent": None,
                           "note": f"#{', #'.join(map(str, deps))} 已完成，解除卡住"}, "unblock")
                self.event("unblocked", card=int(cid), title=(t.get("title") or "")[:60],
                           outcome=f"#{', #'.join(map(str, deps))} 完成 → 排回待辦")
                changed = True
        return changed

    # 4. limits
    def set_limit(self, agent: str, until: datetime | None, line: str | None):
        if until is None and line:
            until = reset_from_line(line, self.now)
        if until is None:
            try:
                until = rest_until(agent, http("GET", "/schedule/agents-info?refresh=true", timeout=90)
                                   .get("usage") or {}, self.now)
            except Exception:  # noqa: BLE001
                until = None
        if until is None:
            until = self.now + timedelta(hours=float((self.cfg["limit_fallback_hours"] or {}).get(agent, 5)))
        prev = parse_iso(self.state["limits"].get(agent))
        self.state["limits"][agent] = until.isoformat(timespec="seconds")
        self.state.setdefault("limit_src", {})[agent] = "log" if line else "usage"
        if not prev or prev <= self.now:
            self.event("limit", agent=agent, outcome=f"額度用完，到 {hm(until)}（台北）恢復",
                       **({"line": line[:160]} if line else {}))

    def probe_ok(self, agent: str) -> bool:
        cmd = (self.cfg.get("probe_cmd") or {}).get(agent)
        if not cmd:
            return False
        probes = self.state.setdefault("probes", {})
        p = probes.get(agent) or {}
        if not probe_due(p.get("at"), time.time(), self.cfg.get("probe_interval_minutes", 60)):
            return bool(p.get("ok"))
        ok = run_probe(cmd)
        probes[agent] = {"at": time.time(), "ok": ok}
        log(f"{agent}: live probe {'OK' if ok else 'not OK'}")
        return ok

    def limited(self, agent: str) -> bool:
        until = parse_iso(self.state["limits"].get(agent))
        if until and until > self.now:
            # usage panel can be stale: a limit not seen in a real run log is re-checked live (<= hourly)
            if self.state.get("limit_src", {}).get(agent) != "log" and self.probe_ok(agent):
                self.state["limits"].pop(agent, None)
                self.event("recovered", agent=agent, outcome=f"live probe OK (panel said until {hm(until)})")
                return False
            return True
        if until:
            self.state["limits"].pop(agent, None)
            self.event("recovered", agent=agent, outcome=f"額度已恢復（原定 {hm(until)}）")
        return False

    def refresh_quota(self, idle: list[str]):
        todo = [a for a in idle if not self.limited(a)]
        if not todo:
            return
        try:
            usage = http("GET", "/schedule/agents-info", timeout=90).get("usage") or {}
        except Exception as e:  # noqa: BLE001
            log(f"agents-info failed: {e}")
            return
        for a in todo:
            until = rest_until(a, usage, self.now)
            if until and self.probe_ok(a):
                log(f"{a}: panel says limited until {hm(until)} but live probe OK -> available")
                continue
            if until:
                self.set_limit(a, until, None)

    # 5. grading
    def grade_if_needed(self, board: dict):
        ungraded = [c for c in board.get("deck", []) if not c.get("difficulty")]
        ungraded += [c for c in board.get("recurring", []) if not c.get("difficulty")]
        if not ungraded:
            return
        log(f"{len(ungraded)} ungraded card(s) → grade_cards.py")
        if self.dry:
            return
        r = subprocess.run([python_exe(), str(TOOLS / "grade_cards.py")], cwd=ROOT, capture_output=True,
                           timeout=300, creationflags=NO_WINDOW if os.name == "nt" else 0)
        log(f"grade_cards exit {r.returncode}: {r.stdout.decode('utf-8', 'replace')[-300:]}")

    # 6. dispatch
    def dispatch(self, board: dict):
        from pick_card import candidates
        diff_state = load_json(STATE_DIR / "card_difficulty.json", {})
        bots = {b.get("agent"): b for b in board.get("bots", [])}
        busy = {r["agent"] for r in self.state["runs"].values()}
        busy |= {a for a, b in bots.items() if any(t.get("status") == "in_progress" for t in b.get("doing", []))}
        idle = [a for a in self.cfg["agents_order"] if a not in busy and not (bots.get(a) or {}).get("paused")]
        self.refresh_quota(idle)
        full = {c["id"]: c for c in board.get("deck", []) + board.get("recurring", []) if c.get("card", "task") == "task" and c.get("id")}
        taken: set = set()
        for agent in idle:
            if self.limited(agent):
                continue
            cands = order_candidates(candidates(board, agent, self.caps, state=diff_state, now=self.now),
                                     agent, self.cfg, self.now, taken, self.night_tasks, full)
            cands = [c for c in cands if not self.prior_busy(c.get("task_id"))
                     # 「[給 Mac]」 work is the Mac's (#626); 10/26 three such cards went to Windows AIs here
                     and MAC_PREFIX not in str(c.get("title") or "") and "[待決定]" not in str(c.get("title") or "")[:12]]
            if not cands:
                log(f"{agent}: nothing eligible → rest")
                continue
            c = cands[0]
            taken.add(c["key"])
            self.launch(agent, c)

    def swarm(self, board: dict, owner_only: bool = False) -> set:
        """Each open 問題回報 card → its own new Claude CLI (owner, 2026-10-18)."""
        cfg = self.cfg.get("issue_swarm") or {}
        if not cfg.get("enabled"):
            return set()
        from pick_card import candidates
        bots = {b.get("agent"): b for b in board.get("bots", [])}
        claude_ok = not self.limited("Claude Code")
        codex_n = int(cfg.get("codex_parallel", 0))
        codex_ok = bool(codex_n) and not self.limited("Codex") and not (bots.get("Codex") or {}).get("paused")
        if not (claude_ok or codex_ok):
            log("issue swarm: Claude and Codex quota exhausted → wait")
            return set()
        used = {r["agent"] for r in self.state["runs"].values() if is_swarm(r["agent"])}
        used |= {a for a, b in bots.items() if is_swarm(a) and (b.get("paused") or any(
            t.get("status") == "in_progress" for t in b.get("doing", [])))}
        limit = int(cfg.get("max_parallel", 8))
        diff_state = load_json(STATE_DIR / "card_difficulty.json", {})
        cands = candidates(board, "Claude Code", self.caps, state=diff_state, now=self.now)
        # new 問題回報 cards, and queued unassigned cards made from one
        free_tasks = {t.get("id") for t in board.get("deck", [])
                      if t.get("card", "task") == "task" and not t.get("agent") and t.get("issue_ids")
                      and t.get("kind") != "recurring"}
        issues = [c for c in cands if (c.get("issue_id") and not c.get("task_id"))
                  or c.get("task_id") in free_tasks]
        # decisions the owner has answered: carrying them out is an issue card too
        seen = {c.get("issue_id") for c in issues}
        try:
            open_issues = http("GET", "/issues").get("items", [])
        except Exception as e:  # noqa: BLE001
            log(f"issue swarm: /issues failed ({e})")
            open_issues = []
        working = {i for t in board.get("deck", []) + [t for b in board.get("bots", []) for t in b.get("doing", [])]
                   if t.get("card", "task") == "task" for i in (t.get("issue_ids") or [])}
        skip_i = set(self.caps.get("skip_issues", []))
        for i in open_issues:
            if (i.get("kind") == "decision" and i.get("decision") and i.get("status") in ("open", "in_progress", "needs_decision")
                    and i["id"] not in seen and i["id"] not in working and i["id"] not in skip_i):
                issues.append({"key": f"i{i['id']}", "issue_id": i["id"], "task_id": None,
                               "difficulty": i.get("difficulty") or 3, "title": i.get("title")})
        # cover_for (owner, 2026-10-18): while that AI is out of quota or paused, Claude CLIs take
        # the cards it would have taken (standing scans included, same cooldown rules).
        full = {c["id"]: c for c in board.get("deck", []) + board.get("recurring", [])
                if c.get("card", "task") == "task" and c.get("id")}
        keys = {c["key"] for c in issues}
        for other in cfg.get("cover_for") or []:
            if not (self.limited(other) or (bots.get(other) or {}).get("paused")):
                continue
            for c in order_candidates(candidates(board, other, self.caps, state=diff_state, now=self.now),
                                      other, self.cfg, self.now, keys, self.night_tasks, full):
                if (c.get("task_id") and (full.get(c["task_id"]) or {}).get("agent") not in (None, other)):
                    continue
                keys.add(c["key"])
                issues.append(c)
        # nothing else waiting → free CLIs run the standing cards (owner 10/22: 「沒有卡了那就都跑常態卡」),
        # each at most every idle_recurring_cooldown_hours; issues above keep their place in line
        if cfg.get("idle_recurring"):
            idle_h = float(cfg.get("idle_recurring_cooldown_hours", 3))
            skip_t = set(self.caps.get("skip_tasks", []))
            # standing cards not due yet live in board["recurring"], outside the deck pick_card reads
            for card in board.get("recurring", []):
                tid = card.get("id")
                if (card.get("card", "task") != "task" or not tid or f"t{tid}" in keys or tid in skip_t
                        or card.get("agent") or card.get("status") not in ("scheduled", "queued")
                        or not night_launch_ok(tid, self.night_tasks, self.now, self.cfg["night_last_launch"])
                        or in_cooldown(card, self.now, idle_h)):
                    continue
                keys.add(f"t{tid}")
                issues.append({"key": f"t{tid}", "task_id": tid, "issue_id": None, "kind": "recurring",
                               "difficulty": card.get("difficulty") or 2, "title": card.get("title")})
        # 「[給 Mac]」 requests are for the Claude session on the owner's Mac, not for a CLI here
        issues = [c for c in issues if not str(c.get("title") or "").lstrip("問題回報 #0123456789：").startswith(MAC_PREFIX)
                  and MAC_PREFIX not in str(c.get("title") or "")[:40]
                  and "[待決定]" not in str(c.get("title") or "")[:12]]
        issues = [c for c in issues if not self.prior_busy(c.get("task_id"))]
        # owner 10/23: 「所有我回應的問題或需求都要優先修正」 — the owner's own reports and requests
        # go first, and may use owner_extra CLIs beyond max_parallel when every slot is busy
        reporters = {i["id"]: str(i.get("reporter") or "") for i in open_issues}
        task_issues = {t.get("id"): t.get("issue_ids") or [] for t in board.get("deck", []) if t.get("card", "task") == "task"}

        def from_owner(c) -> bool:
            title = str(c.get("title") or "")
            # a failing flutter test blocks the owner's fixes from reaching the iPhone: same priority
            if any(tag in title for tag in ("[owner]", "[卡片回報]", "[意見回饋]", "flutter test 失敗", "交 Windows")):
                return True
            ids = [c["issue_id"]] if c.get("issue_id") else task_issues.get(c.get("task_id"), [])
            return any(reporters.get(i, "").startswith(("owner", "App 使用者")) for i in ids)

        issues.sort(key=lambda c: not from_owner(c))
        if owner_only:
            issues = [c for c in issues if from_owner(c)]
        extra = int(cfg.get("owner_extra", 5))
        taken = set()
        for c in issues:
            # Codex first for cards it may take (≤ 3), Claude for the rest and when Codex is full
            agent = (free_slot(used, codex_n, CODEX_PREFIX)
                     if codex_ok and int(c.get("difficulty") or 3) <= 3 else None)
            if not agent and claude_ok:
                agent = free_slot(used, limit) or (free_slot(used, limit + extra) if from_owner(c) else None)
            if not agent:
                if claude_ok:
                    log(f"issue swarm: {limit} Claude CLIs busy, {len(issues) - len(taken)} issue(s) wait")
                    break
                continue
            used.add(agent)
            taken.add(c["key"])
            self.launch(agent, c)
        return taken

    def prior_busy(self, card_id) -> bool:
        """True while the CLI last launched on this card still runs (card #431: one card, one CLI).
        One that has been quiet for lingering_kill_minutes is hung: its process tree is ended."""
        if not card_id:
            return False
        cache = self.__dict__.setdefault("_prior", {})
        if card_id in cache:
            return cache[card_id]
        from launch_agent import agent_kind, live_run
        info = live_run(int(card_id))
        busy = False
        if info:
            files = [AG_LOGS / f"card{card_id}_{agent_kind(info.get('agent') or '')}.log",
                     AG_LOGS / f"card{card_id}.result.md", latest_round_path(int(card_id))]
            acts = [p.stat().st_mtime for p in files if p and p.exists()]
            last = max(acts + [float(info.get("at") or 0)])
            act = prior_cli_action(True, last, time.time(), self.cfg["lingering_kill_minutes"] * 60)
            quiet = int((time.time() - last) / 60)
            if act == "kill" and not self.dry:
                subprocess.run(["taskkill", "/PID", str(info["pid"]), "/T", "/F"], capture_output=True,
                               timeout=60, creationflags=NO_WINDOW if os.name == "nt" else 0)
                busy = live_run(int(card_id)) is not None
                log(f"#{card_id}: previous CLI pid {info['pid']} quiet {quiet} min → ended"
                    + (" (still running!)" if busy else ""))
                self.event("error", card=int(card_id), agent=info.get("agent"),
                           outcome=f"上一個 CLI（pid {info['pid']}）收卡後 {quiet} 分鐘沒動靜，已結束它"
                                   + ("，但還在跑" if busy else "，可以再派"))
            else:
                busy = True
                log(f"#{card_id}: previous CLI pid {info['pid']} ({info.get('agent')}) still running "
                    f"(quiet {quiet} min) → not launched again")
        cache[card_id] = busy
        return busy

    def launch(self, agent: str, c: dict):
        label =f"#{c['task_id']}" if c.get("task_id") else f"問題回報 #{c['issue_id']}"
        log(f"{agent}: pick {label} d{c['difficulty']} {(c.get('title') or '')[:50]}")
        if self.dry:
            log(f"DRY claim+launch {label} → {agent}")
            self.summary.append(f"(dry) {agent}→{label}")
            return
        body = {"agent": agent, **({"task_id": c["task_id"]} if c.get("task_id") else {"issue_id": c["issue_id"]})}
        try:
            t = http("POST", "/schedule/claim", body)
        except urllib.error.HTTPError as e:
            log(f"claim {label} → {agent} refused: HTTP {e.code}")
            return
        cid = int(t["id"])
        res = AG_LOGS / f"card{cid}.result.md"
        if res.exists():  # an old round's result must not look like this run's finish
            res.rename(next_round_path(cid))
        prev = latest_round_path(cid)
        task = http("GET", f"/tasks/{cid}")
        prompt = AG_LOGS / f"card{cid}.prompt.md"
        prompt.write_text(render_prompt(task, self.cfg, self.night_tasks,
                                        TEMPLATE_FILE.read_text(encoding="utf-8"), prev), encoding="utf-8")
        cmd = [python_exe(), str(TOOLS / "launch_agent.py"), "--card", str(cid), "--agent", agent,
               "--prompt", str(prompt)]
        flags = NO_WINDOW if os.name == "nt" else 0
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=180, creationflags=flags | BREAKAWAY)
        except OSError:  # job forbids breakaway
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=180, creationflags=flags)
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        m = re.search(r"pid=(\d+)", out)
        if r.returncode != 0 or not m:
            log(f"launch #{cid} failed: {out[-400:]}")
            self.write("PUT", f"/tasks/{cid}", {"by": "Grokbot", "status": "queued", "agent": None,
                       "progress": f"dispatch_tick 啟動 {agent} 失敗，排回待辦"}, "launch failed")
            self.event("error", card=cid, agent=agent, title=(task.get("title") or "")[:60],
                       outcome=f"啟動失敗：{out.strip().splitlines()[-1][:150] if out.strip() else r.returncode}")
            return
        self.state["runs"][str(cid)] = {"agent": agent, "pid": int(m.group(1)), "launched_at": time.time()}
        model = re.search(r"model ([\w.\-]+)", out)
        self.event("dispatched", card=cid, agent=agent, title=(task.get("title") or "")[:60],
                   outcome=f"難度 {task.get('difficulty')}，model {model.group(1) if model else '?'}")
        self.summary.append(f"{agent}→#{cid}")

    # 7. heartbeats + #13
    def heartbeats(self, board: dict):
        running = {r["agent"]: cid for cid, r in self.state["runs"].items()}
        bots = {b.get("agent"): b for b in board.get("bots", [])}
        for a in AGENTS:
            if bots.get(a, {}).get("doing") and a not in running:
                ip = [t for t in bots[a]["doing"] if t.get("status") == "in_progress"]
                if ip:
                    running[a] = str(ip[0]["id"])
        notes = {"Grokbot": f"dispatch_tick {hm(self.now)}"}
        for a in AGENTS:
            if a in running:
                notes[a] = f"卡 #{running[a]} 進行中"
            elif parse_iso(self.state["limits"].get(a)):
                notes[a] = f"額度用完，到 {hm(parse_iso(self.state['limits'][a]))}"
            else:
                notes[a] = "閒置（沒有合適的卡）"
        for a, n in notes.items():
            try:
                self.write("POST", "/agents/hello", {"agent": a, "note": n}, "heartbeat")
            except Exception as e:  # noqa: BLE001
                log(f"heartbeat {a} failed: {e}")
        line = "；".join(f"{a} {n}" for a, n in notes.items() if a != "Grokbot")
        if self.summary:
            line = "本輪：" + "、".join(self.summary) + "。" + line
        last = self.state.get("note", {})
        age = self.now.timestamp() - float(last.get("at") or 0)
        if line != last.get("text") or age > self.cfg["note_refresh_minutes"] * 60:
            self.write("PUT", f"/tasks/{self.cfg['note_task']}",
                       {"by": "Grokbot", "progress": f"{hm(self.now)} dispatch_tick：{line}"[:500]}, "#13 note")
            if not self.dry:
                self.state["note"] = {"text": line, "at": self.now.timestamp()}

    def run(self) -> int:
        every = float(self.cfg.get("watchdog_minutes", 60))  # owner 10/22: 「2分鐘太頻繁了 改成1小時」
        if (not self.dry and os.name == "nt" and self.cfg.get("watchdog", True)
                and time.time() - self.state.get("watchdog_at", 0) >= every * 60):
            # owner 10/22 「保持網路 不要斷掉了」: tunnel, API, UI, App, tagger come back on their own
            self.state["watchdog_at"] = time.time()
            try:
                from watchdog import ensure_all
                if ensure_all(log):
                    self.event("recovered", outcome="watchdog 重新啟動了停掉的服務（見 dispatch_tick.log）")
            except Exception as e:  # noqa: BLE001
                log(f"watchdog failed: {e}")
        try:
            board = http("GET", "/schedule/board")
        except Exception as e:  # noqa: BLE001
            n = self.state.get("api_fail", 0) + 1
            self.state["api_fail"] = n
            log(f"board unreachable ({e}); consecutive={n}")
            if n == 3:
                self.event("error", outcome=f"看板 API 連不上（連續 {n} 次）：{str(e)[:120]}")
            self.save()
            return 2
        if self.state.pop("api_fail", 0) >= 3:
            self.event("recovered", outcome="看板 API 恢復")
        if any(b.get("agent") == "Grokbot" and b.get("paused") for b in board.get("bots", [])):
            log("Grokbot paused on the board → skip tick")
            self.save()
            return 0
        self.qwen_schedule()
        changed = self.check_running(board)
        changed |= self.unblock(board)
        changed |= self.answered()
        changed |= self.prune_decisions()
        changed |= self.sweep_orphans()
        if changed and not self.dry:
            board = http("GET", "/schedule/board")
        self.grade_if_needed(board)
        if not self.dry and (self.cfg.get("mac_sync") or {}).get("enabled"):
            # Mac's failed rows → 問題回報 now, so this tick's swarm already picks them up
            try:
                r = subprocess.run([python_exe(), str(TOOLS / "mac_results_to_issues.py")], cwd=ROOT,
                                   capture_output=True, timeout=120,
                                   creationflags=NO_WINDOW if os.name == "nt" else 0)
                out = r.stdout.decode("utf-8", "replace").strip()
                if out:
                    log(f"mac results: {out[-300:]}")
                    board = http("GET", "/schedule/board")
            except Exception as e:  # noqa: BLE001
                log(f"mac_results_to_issues failed: {e}")
        self.route_app_reports()
        guard_hold = self.resource_guard()
        if guard_hold:
            log("resource_guard: memory over limit → collecting only, no new CLIs")
        elif self.cfg.get("hold_new_launches"):
            # owner 10/23 「現有的事情做完就先不要再派新的」: finish and collect, launch nothing
            log("hold_new_launches: collecting only, no new CLIs"
                + ("; owner's own reports still go out" if self.cfg.get("hold_allow_owner") else ""))
            if self.cfg.get("hold_allow_owner"):
                # owner 10/23: 「只派我這 6 筆回報，其他維持暫停」
                self.swarm(board, owner_only=True)
        else:
            swarmed = self.swarm(board)
            if swarmed and not self.dry:
                board = http("GET", "/schedule/board")
            self.dispatch(board)
        self.heartbeats(board)
        self.sync_issues()
        self.mac_sync()
        self.tag_fallback()
        try:
            self.serve_app_reload()
        except Exception as e:  # noqa: BLE001 — never lose the tick's state over it
            log(f"serve_app reload failed: {e}")
        self.save()
        return 0

    def resource_guard(self) -> bool:
        """Card #730 (issue #867): whole-PC memory/CPU/GPU/disk under 80 %. True = memory over the limit,
        so no new CLIs this tick (lifts by itself below release_pct). Never breaks the tick."""
        cfg = self.cfg.get("resource_guard") or {}
        if cfg.get("enabled") is False:
            return False
        try:
            import resource_guard as rg
            st = rg.run(dry=self.dry, cfg=cfg)
        except Exception as e:  # noqa: BLE001
            log(f"resource_guard failed: {e}")
            return False
        line = rg.summary(st)
        log(line + (f" {st['notes']}" if st.get("notes") else ""))
        if st.get("over"):
            self.summary.append(line.split("｜")[0].replace("資源 ", "資源:"))
        asked = self.state.setdefault("guard_alert", {})
        if st.get("alert") and not self.dry:
            key = ",".join(st["alert"])
            if asked.get("key") != key:
                try:
                    top = "、".join(f"{t['name']}×{t['count']} {t['mb']}MB" for t in st.get("top", []))
                    i = http("POST", "/issues", {"kind": "bug", "severity": "high", "area": "backend",
                             "title": f"[owner] Windows PC 資源超過 80% 超過 10 分鐘：{key}"[:300],
                             "detail": f"{line}\n最大程序：{top}\n自動處理（停派新 CLI、降優先權、清 TEMP）沒有降下來。",
                             "reporter": "派工程式"})
                    asked["key"] = key
                    self.event("resource_alert", issue=i.get("id"), over=key)
                except Exception as e:  # noqa: BLE001
                    log(f"resource_guard alert: {e}")
        elif not st.get("alert"):
            asked.pop("key", None)
        return bool(st.get("hold_launches"))

    def serve_app_reload(self):
        """Card #522 (owner decision #553 = A): serve_app hashes serve_app.py, lexicon_transport.py,
        lexicon/backend/app/**.py and lexicon/quality/**.json only at start-up, so fixed rules never
        reached the app pack until someone restarted it. Every check_minutes: code changed since the
        process started (content, not just mtime) → restart it once the change has settled
        (serve_app_reload_action); #380 keeps answering from the old pack while the new one builds."""
        cfg = self.cfg.get("serve_app_reload") or {}
        if not cfg.get("enabled") or os.name != "nt":
            return
        now = time.time()
        st_all = self.state.setdefault("serve_app", {})
        if now - float(st_all.get("checked_at") or 0) < float(cfg.get("check_minutes", 10)) * 60:
            return
        try:
            import serve_app_stale as sas
            st = sas.status()
            rev = sas.revision()
        except Exception as e:  # noqa: BLE001
            log(f"serve_app reload: check failed ({e})")
            return
        if not self.dry:
            st_all["checked_at"] = now
        if not st["running"]:
            return  # the watchdog brings it back
        started = st["started"].isoformat()
        if st_all.get("started") != started:
            st_all.update(started=started, rev=None, stale_since=None, reminded=False)
        if not st["changed"]:
            st_all["rev"] = rev
            return
        if st_all.get("rev") == rev:
            return  # files touched, content unchanged
        newest = st["changed"][0][0].timestamp()
        stale_since = float(st_all.get("stale_since") or now)
        st_all["stale_since"] = stale_since
        from launch_agent import live_run
        busy_ids = {int(x) for x in cfg.get("busy_tasks", [])}
        unsettled, busy = [], []
        for f in AG_LOGS.glob("card*.pid.json"):
            m = re.fullmatch(r"card(\d+)\.pid\.json", f.name)
            info = live_run(int(m.group(1))) if m else None
            if not info:
                continue
            cid = int(m.group(1))
            if cid in busy_ids:
                busy.append(cid)
            elif float(info.get("at") or 0) < newest and cid not in cfg.get("ignore_tasks", []):
                unsettled.append(cid)
        action, why = serve_app_reload_action(newest, sorted(unsettled), sorted(busy), stale_since, now, cfg)
        files = [f for _, f in st["changed"]]
        log(f"serve_app reload: {len(files)} file(s) changed since {hm(st['started'].astimezone(TAIPEI))} → {action} {why}")
        if action == "wait":
            if (not st_all.get("reminded") and now - stale_since > float(cfg.get("remind_hours", 3)) * 3600):
                st_all["reminded"] = True
                self.event("blocker", outcome=f"serve_app 跑舊程式 {int((now - stale_since) // 3600)} 小時還沒重啟（{why}）；"
                                             f"改過 {len(files)} 檔：{', '.join(files[:3])}")
            return
        if self.dry:
            log(f"DRY would restart serve_app pid {st['pids']}")
            return
        ok, msg = self.restart_serve_app(st["pids"])
        if ok:
            st_all.update(started=None, rev=None, stale_since=None, reminded=False)
            self.event("recovered", outcome=f"serve_app 重啟，載入 {len(files)} 個新改的檔案（{', '.join(files[:3])}）")
        else:
            self.event("error", outcome=f"serve_app 重啟失敗：{msg[:160]}")

    def restart_serve_app(self, pids: list[int]) -> tuple[bool, str]:
        import socket
        flags = NO_WINDOW if os.name == "nt" else 0
        ids = ",".join(str(int(p)) for p in pids)
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {ids} -Force"],
                       capture_output=True, timeout=60, creationflags=flags)
        for _ in range(30):
            with socket.socket() as s:
                s.settimeout(1)
                if s.connect_ex(("127.0.0.1", 8123)) != 0:
                    break
            time.sleep(1)
        try:
            r = subprocess.run([python_exe(), str(ROOT / "start_services.py")], cwd=ROOT, capture_output=True,
                               timeout=120, creationflags=flags)
        except subprocess.TimeoutExpired:
            return False, "start_services.py 120 秒沒回應"
        out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
        log(f"serve_app restart: {out[-200:]}")
        return r.returncode == 0, out

    def decision_to_mac(self, iid: int, issue: dict, task: dict):
        """The Mac can't read 問題回報 (no key): an owner decision on a card that came from the owner's
        App reports is written into docs/mac_inbox.md, so the Mac's App work follows it (10/23 #619:
        the Mac added 未來式 although the owner had chosen 「不加」)."""
        decision = issue.get("decision") or ""
        reporters = []
        for n in task.get("issue_ids") or []:
            try:
                reporters.append(str(http("GET", f"/issues/{n}").get("reporter") or ""))
            except Exception:  # noqa: BLE001
                pass
        if not decision or not any(r.startswith("App 使用者") for r in reporters):
            return
        inbox = ROOT / "docs" / "mac_inbox.md"
        no = max([int(n) for n in re.findall(r"^## M(\d+)", inbox.read_text(encoding="utf-8"), re.M)] or [0]) + 1
        with inbox.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n## M{no}（{self.now:%Y-%m-%d %H:%M}）狀態：參考（owner 的決定）\n"
                    f"卡：{str(task.get('title') or '')[:80]}\n"
                    f"問題：{str(issue.get('title') or '')[:150]}\n**owner 決定**：{decision[:600]}\n"
                    "App 畫面若和這個決定不同，請照決定改。\n")
        log(f"decision #{iid} copied to the Mac inbox (M{no})")

    def hand_to_mac(self, card_id: int, task: dict, text: str):
        """#626: a card's 「需要 Mac：…」 part (App screens) goes to docs/mac_inbox.md for the Mac."""
        m = re.search(r"需要 ?Mac[：:]", text)
        if not m or self.dry:
            return
        part = text[m.end():].split("\n\n## ")[0].strip()[:1500]
        inbox = ROOT / "docs" / "mac_inbox.md"
        no = max([int(n) for n in re.findall(r"^## M(\d+)", inbox.read_text(encoding="utf-8"), re.M)] or [0]) + 1
        with inbox.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n## M{no}（{self.now:%Y-%m-%d %H:%M}）狀態：待做（Windows 卡 #{card_id} 交給 Mac 的 App 畫面部分）\n"
                    f"卡：{str(task.get('title') or '')[:80]}\n\n{part}\n")
        log(f"#{card_id}: App part handed to the Mac (inbox M{no})")

    def save_screenshot(self, iid: int) -> str | None:
        """The Mac can't read 問題回報 (no key): a report's screenshot is saved as
        docs/mac_handover/<id>.png|jpg for it (Mac 10/24, #673 was one line plus a screenshot)."""
        import base64
        try:
            data = str(http("GET", f"/issues/{iid}").get("screenshot") or "")
        except Exception:  # noqa: BLE001
            return None
        m = re.match(r"data:image/(png|jpeg);base64,(.+)", data, re.S)
        if not m:
            return None
        rel = f"docs/mac_handover/{iid}.{'png' if m.group(1) == 'png' else 'jpg'}"
        (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / rel).write_bytes(base64.b64decode(m.group(2)))
        return rel

    def route_app_reports(self):
        """owner 10/23 (#626): App 畫面與互動由 Mac 修。The owner's reports from the App go to the Mac:
        titled 「[給 Mac]」 (the swarm skips them) and listed in docs/mac_inbox.md (mac_sync pushes it).
        Data / server parts come back as 「不通過」 rows in mac_verify_results.md → issues here."""
        if not (self.cfg.get("mac_sync") or {}).get("app_reports_to_mac", True) or self.dry:
            return
        try:
            items = http("GET", "/issues").get("items", [])
        except Exception as e:  # noqa: BLE001
            log(f"route_app_reports: /issues failed ({e})")
            return
        new = [i for i in items if str(i.get("reporter") or "").startswith("App 使用者")
               and i.get("status") == "open" and MAC_PREFIX not in str(i.get("title") or "")]
        if not new:
            return
        inbox = ROOT / "docs" / "mac_inbox.md"
        text = inbox.read_text(encoding="utf-8")
        no = max([int(n) for n in re.findall(r"^## M(\d+)", text, re.M)] or [0]) + 1
        rows = [f"\n## M{no}（{self.now:%Y-%m-%d %H:%M}）狀態：待做（owner 回報，給 Mac）",
                "owner 在 iPhone 送出的回報（#626：App 畫面與互動由 Mac 修）。資料或伺服器的部分請寫「不通過」列交回 Windows。",
                "", "| # | 回報 | 內容 |", "|---|---|---|"]
        for i in sorted(new, key=lambda i: i["id"]):
            detail = str(i.get("detail") or "").replace("|", "／").replace("\n", " / ")
            shot = self.save_screenshot(i["id"])
            rows.append(f"| {i['id']} | {str(i.get('title') or '')[:60]} | {detail[:400]}"
                        + (f"（截圖：`{shot}`）" if shot else "") + " |")
            self.write("PUT", f"/issues/{i['id']}", {"by": "Grokbot", "title": f"{MAC_PREFIX} {i.get('title') or ''}"[:300],
                       "resolution": f"給 Mac（inbox M{no}）"}, "app report → Mac")
        with inbox.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(rows) + "\n")
        log(f"route_app_reports: {len(new)} owner report(s) → Mac inbox M{no}")
        self.event("dispatched", agent="Mac", outcome=f"owner 的 {len(new)} 筆 App 回報交給 Mac（inbox M{no}）")

    def sweep_orphans(self) -> bool:
        """Cards left in_progress by a holder that went away (a closed session, an unnamed CLI)
        stop the swarm from ever retrying them (owner 10/21: 「cli 不要停 有工作就派工」).
        After orphan_hours without an update and no live CLI: result.md newer than the last
        update → collect it; otherwise back to the pile (standing cards → scheduled)."""
        hours = float(self.cfg.get("orphan_hours", 24))
        try:
            tasks = http("GET", "/tasks").get("items", [])
        except Exception as e:  # noqa: BLE001
            log(f"orphan sweep: /tasks failed ({e})")
            return False
        from launch_agent import live_run
        changed = False
        for t in tasks:
            cid, agent = t.get("id"), t.get("agent")
            if t.get("status") != "in_progress" or str(cid) in self.state["runs"] or agent == "Claude · Manager":
                continue
            upd = parse_iso(t.get("updated_at"))
            if not upd or (self.now - upd).total_seconds() < hours * 3600 or live_run(int(cid)):
                continue
            res = AG_LOGS / f"card{cid}.result.md"
            if res.exists() and res.stat().st_mtime >= upd.timestamp() - 3600:
                log(f"#{cid}: orphan of {agent} with result.md → collect")
                self.finish(int(cid), agent or "Claude CLI", t, res)
            else:
                status = "scheduled" if t.get("kind") == "recurring" else "queued"
                log(f"#{cid}: orphan of {agent} (quiet since {hm(upd)}) → {status}")
                self.write("PUT", f"/tasks/{cid}", {"by": "Grokbot", "status": status, "agent": None,
                           "progress": f"{agent or '無人'} 超過 {hours:g} 小時沒動、沒有 CLI 在跑，"
                                       f"放回待辦重派（dispatch_tick {hm(self.now)}）"}, f"orphan → {status}")
            changed = True
        return changed

    def tag_fallback(self):
        """問題回報 #327: Codex/Cursor photo tagging when Qwen is paused or ≥ threshold photos wait.
        tag_fallback.py run checks that itself, holds its own lock and stops at a usage limit."""
        if self.dry or not load_json(TOOLS / "tag_fallback_config.json", {}).get("enabled"):
            return
        flags = NO_WINDOW if os.name == "nt" else 0
        cmd = [python_exe(), str(TOOLS / "tag_fallback.py"), "run"]
        try:
            subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=flags | BREAKAWAY)
        except OSError:
            subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=flags)

    def qwen_schedule(self):
        """owner 10/21: Qwen runs only inside qwen_schedule.windows (09:30–19:30, 00:00–06:00), paused otherwise.
        Acts only when the period changes, so a manual ⏸／▶ on the board holds until the next switch."""
        cfg = self.cfg.get("qwen_schedule") or {}
        if not cfg.get("enabled") or self.dry:
            return
        hm_now = self.now.strftime("%H:%M")
        # run windows ["09:30-19:30", "00:00-06:00"] (owner 10/21); older configs use night_start/end
        windows = cfg.get("windows") or [f'{cfg.get("night_start", "19:00")}-{cfg.get("night_end", "07:00")}']
        def inside(w):
            start, end = w.split("-")
            return (hm_now >= start or hm_now < end) if start > end else (start <= hm_now < end)
        night = any(inside(w) for w in windows)
        want = "on" if night else "off"
        if self.state.get("qwen_period") == want:
            return
        action = "resume" if night else "pause"
        if night:
            # cards parked until Qwen's window (qwen_wait_tasks) go back to the queue now
            waiting = [int(x) for x in (self.cfg.get("qwen_wait_tasks") or [])]
            for cid in waiting:
                try:
                    t = http("GET", f"/tasks/{cid}")
                    if t.get("status") == "blocked":
                        self.write("PUT", f"/tasks/{cid}", {"by": "Grokbot", "status": "queued", "agent": None,
                                   "progress": f"Qwen 工作時段開始（{hm_now}），排回待辦"}, "qwen window")
                except Exception as e:  # noqa: BLE001
                    log(f"qwen wait #{cid}: {e}")
        try:
            http("POST", f"/agents/Qwen/{action}", {})
            self.state["qwen_period"] = want
            self.event("qwen", outcome=f"Qwen {'開始（工作時段）' if night else '暫停（非工作時段）'} {hm_now}")
        except Exception as e:  # noqa: BLE001
            log(f"Qwen {action} failed: {e}")

    def sync_issues(self):
        """owner 10/21: 處理中 issues whose cards all ended get 已修正／待處理 (sync_issue_status.py), ~every 10 min."""
        if self.dry:
            return
        n = int(self.state.get("issue_sync_n", 0)) + 1
        self.state["issue_sync_n"] = n
        if n % 5:
            return
        try:
            r = subprocess.run([python_exe(), str(TOOLS / "sync_issue_status.py")], cwd=ROOT, capture_output=True,
                               timeout=300, creationflags=NO_WINDOW if os.name == "nt" else 0)
            out = r.stdout.decode("utf-8", "replace").strip()
            if out:
                log(f"issue sync: {out[-200:]}")
        except Exception as e:  # noqa: BLE001
            log(f"issue sync failed: {e}")

    def mac_sync(self):
        """Finished app cards → tested, pushed and listed for the Mac (mac_sync.py, own lock)."""
        if self.dry or not (self.cfg.get("mac_sync") or {}).get("enabled"):
            return
        flags = NO_WINDOW if os.name == "nt" else 0
        try:
            subprocess.Popen([python_exe(), str(TOOLS / "mac_sync.py")], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=flags | BREAKAWAY)
        except OSError:
            subprocess.Popen([python_exe(), str(TOOLS / "mac_sync.py")], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)

    def save(self):
        if self.dry:
            log(f"DRY state would be: runs={list(self.state['runs'])} limits={self.state['limits']}; "
                f"{len(self.events)} event(s) not written")
            return
        self.state["last_tick"] = self.now.isoformat(timespec="seconds")
        save_json(STATE_FILE, self.state)
        if self.events:
            with EVENTS_FILE.open("a", encoding="utf-8") as f:
                for e in self.events:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not acquire_lock():
        log("another dispatch_tick is running → exit")
        flush_log()
        return 0
    code = 1
    try:
        log(f"tick start{' (dry-run)' if a.dry_run else ''}")
        code = Tick(a.dry_run).run()
    except Exception:  # noqa: BLE001
        log("CRASH " + traceback.format_exc()[-1500:])
        if not a.dry_run:
            try:
                with EVENTS_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": now_tp().isoformat(timespec="seconds"), "type": "error",
                                        "outcome": "dispatch_tick 當掉：" + traceback.format_exc().strip().splitlines()[-1][:160]},
                                       ensure_ascii=False) + "\n")
            except OSError:
                pass
    finally:
        log(f"tick end ({code})")
        release_lock()
        flush_log()
    return code


if __name__ == "__main__":
    sys.exit(main())
