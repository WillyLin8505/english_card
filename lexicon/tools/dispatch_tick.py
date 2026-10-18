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
MAC_PREFIX = "[給 Mac]"


def is_swarm(agent: str | None) -> bool:
    """An issue-swarm Claude CLI ("Claude CLI 3"); shares Claude Code's quota."""
    return bool(agent) and agent.startswith(SWARM_PREFIX) and agent[len(SWARM_PREFIX):].isdigit()


def quota_agent(agent: str) -> str:
    return "Claude Code" if is_swarm(agent) else agent


def free_slot(used: set[str], limit: int) -> str | None:
    for n in range(1, limit + 1):
        if f"{SWARM_PREFIX}{n}" not in used:
            return f"{SWARM_PREFIX}{n}"
    return None
NO_WINDOW = 0x08000000
BREAKAWAY = 0x01000000
LOG_CAP = 1_000_000
LOCK_STALE_S = 15 * 60
DECISION_RE = re.compile(r"需要你決定|待你決定|請你決定|需使用者決定|需要使用者決定|decision needed|needs owner", re.I)
ALL_DONE_RE = re.compile(r"^\s*(全部完成|ALL DONE)", re.I | re.M)
BLOCKER_RE = re.compile(r"^\s*(BLOCKED|卡住|無法完成)", re.I | re.M)

DEFAULT_CFG = {
    "agents_order": AGENTS, "prefer": {}, "reserved": {}, "multi_round_tasks": [],
    "unblock_after": {}, "cooldown_hours": 12, "night_last_launch": "06:15",
    "night_safe_stop": "06:45", "finish_grace_minutes": 10, "alive_log_minutes": 45,
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
            if b.get("agent") in AGENTS or is_swarm(b.get("agent")):
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
            limit_line = detect_limit(log_text) if alive is False else None
            verdict = classify_run(run["launched_at"], rm, alive, limit_line, time.time(),
                                   self.cfg["finish_grace_minutes"] * 60)
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
        elif DECISION_RE.search(text[:800]):
            action = "waiting"
            self.write("PUT", f"/tasks/{card_id}", {"by": "Grokbot", "status": "waiting", "progress": progress}, "decision")
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
            if not cands:
                log(f"{agent}: nothing eligible → rest")
                continue
            c = cands[0]
            taken.add(c["key"])
            self.launch(agent, c)

    def swarm(self, board: dict) -> set:
        """Each open 問題回報 card → its own new Claude CLI (owner, 2026-10-18)."""
        cfg = self.cfg.get("issue_swarm") or {}
        if not cfg.get("enabled"):
            return set()
        if self.limited("Claude Code"):
            log("issue swarm: Claude quota exhausted → wait")
            return set()
        from pick_card import candidates
        bots = {b.get("agent"): b for b in board.get("bots", [])}
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
            if (i.get("kind") == "decision" and i.get("decision") and i.get("status") in ("open", "in_progress")
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
        # 「[給 Mac]」 requests are for the Claude session on the owner's Mac, not for a CLI here
        issues = [c for c in issues if not str(c.get("title") or "").lstrip("問題回報 #0123456789：").startswith(MAC_PREFIX)
                  and MAC_PREFIX not in str(c.get("title") or "")[:40]]
        taken = set()
        for c in issues:
            agent = free_slot(used, limit)
            if not agent:
                log(f"issue swarm: {limit} Claude CLIs busy, {len(issues) - len(taken)} issue(s) wait")
                break
            used.add(agent)
            taken.add(c["key"])
            self.launch(agent, c)
        return taken

    def launch(self, agent: str, c: dict):
        label = f"#{c['task_id']}" if c.get("task_id") else f"問題回報 #{c['issue_id']}"
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
        changed = self.check_running(board)
        changed |= self.unblock(board)
        if changed and not self.dry:
            board = http("GET", "/schedule/board")
        self.grade_if_needed(board)
        swarmed = self.swarm(board)
        if swarmed and not self.dry:
            board = http("GET", "/schedule/board")
        self.dispatch(board)
        self.heartbeats(board)
        self.save()
        return 0

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
