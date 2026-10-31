"""What each AI is really doing (card #919): the process, not the board's bookkeeping.

A card can be in_progress with no program behind it. 「工作中」 counts only a live process that belongs
to the card (tools/proc_identity.py, the check launch_agent and dispatch_tick use). Everything else gets
its own word: 等收卡 (result written), 等你, 閒置／舊卡. Interactive Claude sessions are listed apart.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

sys.path.insert(0, str(config.HOME / "tools"))
import proc_identity  # noqa: E402

AGENT_LOGS = config.HOME / "logs" / "agents"
SESSIONS = Path.home() / ".claude" / "sessions"
PROJECT = str(config.HOME.parent).lower()
DISPATCHED_ENTRYPOINT = "sdk-cli"   # `claude -p`; anything else is someone at the keyboard
INTERACTIVE_RECENT = timedelta(minutes=30)
SESSION_MATCH_S = 45                # launch_agent's time vs the session's own start
ORPHAN_DAYS = 3
SESSIONS_TTL = 10.0
PAUSED_PREFIX = "owner 暫停"
_sessions_cache: tuple[float, list[dict]] = (0.0, [])


def is_paused(progress: str | None) -> bool:
    return (progress or "").startswith(PAUSED_PREFIX)


def is_interactive_agent(agent: str | None) -> bool:
    return bool(agent) and agent.startswith(("Claude · ", "Codex 桌面"))


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds") if ts else None


def sessions() -> list[dict]:
    """Live Claude sessions in this project (~/.claude/sessions); entries of ended ones stay on disk."""
    global _sessions_cache
    now = time.time()
    if now - _sessions_cache[0] < SESSIONS_TTL:
        return _sessions_cache[1]
    out = []
    for f in SESSIONS.glob("*.json") if SESSIONS.is_dir() else []:
        d = proc_identity.read_run(f)
        if not d or not str(d.get("cwd", "")).lower().startswith(PROJECT):
            continue
        try:
            started = int(d["procStart"]) / 1e7 - 11644473600
        except (KeyError, TypeError, ValueError):
            started = None
        if not proc_identity.same_process(d.get("pid"), started, (d.get("startedAt") or 0) / 1000):
            continue
        out.append({"pid": d["pid"], "name": d.get("name") or "未命名", "status": d.get("status"),
                    "interactive": d.get("entrypoint") != DISPATCHED_ENTRYPOINT,
                    "started": (d.get("startedAt") or 0) / 1000,
                    "activity": (d.get("statusUpdatedAt") or d.get("updatedAt") or 0) / 1000})
    _sessions_cache = (now, out)
    return out


def interactive_sessions() -> list[dict]:
    return [{"name": x["name"], "status": x["status"], "started_at": _iso(x["started"]),
             "last_activity": _iso(x["activity"])} for x in sessions() if x["interactive"]]


def _cli_activity(at: float | None) -> float | None:
    """A `claude -p` log is written only at the end; its session entry says when it last moved."""
    if not at:
        return None
    near = [x for x in sessions() if not x["interactive"] and abs(x["started"] - at) <= SESSION_MATCH_S]
    return max((x["activity"] for x in near), default=None) if len(near) == 1 else None


def card_run(card: int, status: str, agent: str | None, updated_at: datetime | None, started_at: datetime | None,
             progress: str | None = None) -> dict:
    """{state, pid, started_at, last_activity}; state ∈ running · collecting · waiting · blocked · paused ·
    session (an interactive session's fresh card) · idle (nothing behind it)."""
    info = proc_identity.read_run(AGENT_LOGS / f"card{card}.pid.json")
    alive = proc_identity.run_alive(info)
    at = float(info["at"]) if info and info.get("at") else None
    launched = at or (started_at.timestamp() if started_at else None)
    result_at = _mtime(AGENT_LOGS / f"card{card}.result.md")
    wrote = bool(result_at and launched and result_at >= launched - 60)
    logs = [_mtime(AGENT_LOGS / f"card{card}_{k}.log") for k in ("claude", "codex", "cursor")]
    updated = updated_at.timestamp() if updated_at else None
    seen = [x for x in (updated, result_at, *logs, _cli_activity(at) if alive else None) if x]
    if is_paused(progress):
        state = "paused"
    elif status == "waiting":
        state = "waiting"
    elif status == "blocked":
        state = "blocked"
    elif wrote and status == "in_progress":
        state = "collecting"
    elif alive:
        state = "running"
    elif is_interactive_agent(agent) and updated and time.time() - updated < INTERACTIVE_RECENT.total_seconds():
        state = "session"
    else:
        state = "idle"
    return {"state": state, "alive": alive, "pid": info.get("pid") if info and alive else None,
            "started_at": _iso(launched), "last_activity": _iso(max(seen) if seen else None)}


def stop_cli(card: int) -> bool:
    return proc_identity.kill_tree(proc_identity.read_run(AGENT_LOGS / f"card{card}.pid.json"))


def lingering_cards(open_ids: set[int]) -> list[dict]:
    """A CLI that is alive though its card was collected or closed: it still uses a slot."""
    out = []
    cutoff = time.time() - ORPHAN_DAYS * 86400
    for f in AGENT_LOGS.glob("card*.pid.json"):
        m = f.name[4:].split(".")[0]
        if not m.isdigit() or int(m) in open_ids or (_mtime(f) or 0) < cutoff:
            continue
        info = proc_identity.read_run(f)
        if proc_identity.run_alive(info):
            out.append({"card": int(m), "agent": info.get("agent"), "started_at": _iso(info.get("at"))})
    return out


def overview(rows: list[dict]) -> dict:
    """`rows`: card_run + card/title/agent for every card in hand. Split so the numbers add up."""
    groups = {"working": ("running",), "collecting": ("collecting",), "waiting": ("waiting",),
              "idle": ("idle", "blocked", "paused"), "session": ("session",)}
    by_agent: dict[str, list[int]] = {}
    for r in rows:
        if r["state"] in ("running", "collecting", "session", "idle") and r.get("agent"):
            by_agent.setdefault(r["agent"], []).append(r["card"])
    for r in rows:
        r["also"] = [c for c in by_agent.get(r.get("agent") or "", []) if c != r["card"]]
    out = {k: [r for r in rows if r["state"] in v] for k, v in groups.items()}
    out["sessions"] = interactive_sessions()
    out["lingering"] = lingering_cards({r["card"] for r in rows})
    out["counts"] = {k: len(out[k]) for k in (*groups, "sessions", "lingering")}
    return out
