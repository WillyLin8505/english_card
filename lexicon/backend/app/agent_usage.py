"""Each AI's 5-hour and weekly usage for the board's AI 機器人 panel (card #157).

Only local, non-secret records are read — never auth files:

* Codex: ~/.codex/sessions/**/rollout-*.jsonl `token_count` events carry the
  server's own `rate_limits` (primary = 5-hour window, secondary = weekly):
  used_percent and resets_at. Exact, as of the last Codex call.
* Claude Code: ~/.claude/projects/**/*.jsonl. Percentages are not recorded;
  a limit message ("You've hit your weekly limit · resets Oct 19, 7pm
  (Asia/Taipei)") means 100 % until that time. Otherwise the percent is 未知
  and we show the tokens counted in the window.
* Cursor CLI: launch_agent.py runs it with `--output-format json`, whose
  result line carries `usage`; tokens are summed from
  lexicon/logs/agents/card*_cursor.log. Cursor's plan is monthly — there is
  no 5-hour/weekly window, so the percent is 未知.

Numbers are never invented: unknown stays None (UI: 未知).
Per-file parse results are cached by (mtime, size); the whole answer for 120 s.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

HOME = Path(os.environ.get("AGENT_USAGE_HOME", Path.home()))
LOGS = config.HOME / "logs" / "agents"
TTL = 120.0
FIVE_H = timedelta(hours=5)
WEEK = timedelta(days=7)
_cache: dict = {"at": 0.0, "data": None}
_files: dict[str, tuple[tuple[float, int], object]] = {}


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cached(path: Path, parse):
    st = path.stat()
    key = (st.st_mtime, st.st_size)
    hit = _files.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    value = parse(path)
    _files[str(path)] = (key, value)
    return value


def _recent(paths, days: int = 9) -> list[Path]:
    cutoff = time.time() - days * 86400
    out = []
    for p in paths:
        try:
            if p.stat().st_mtime >= cutoff:
                out.append(p)
        except OSError:
            pass
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def _window(used: float | None, resets_at: datetime | None, minutes: int | None, now: datetime,
            source: str, exact: bool, note: str | None = None, tokens: int | None = None) -> dict:
    d = {"used_percent": used, "resets_at": resets_at.isoformat() if resets_at else None,
         "window_minutes": minutes, "exact": exact, "source": source, "note": note, "tokens": tokens}
    if resets_at and resets_at <= now and used is not None:
        # The window rolled over after the last record: nothing used since.
        d.update(used_percent=0.0, note="視窗已重置，之後沒有使用紀錄", exact=False,
                 resets_at=None)
    return d


# ── Codex ──────────────────────────────────────────────────────────────

def _codex_file(path: Path):
    last = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"rate_limits"' not in line or '"used_percent"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            rl = (d.get("payload") or {}).get("rate_limits") or {}
            if rl.get("primary") or rl.get("secondary"):
                last = (d.get("timestamp"), rl)
    return last


def codex_usage(now: datetime | None = None, home: Path | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = (home or HOME) / ".codex" / "sessions"
    best = None
    for p in _recent(root.glob("**/rollout-*.jsonl"))[:30]:
        got = _cached(p, _codex_file)
        if got and (best is None or (got[0] or "") > (best[0] or "")):
            best = got
    src = "~/.codex/sessions rate_limits"
    if not best:
        return {"five_hour": _window(None, None, 300, now, src, False, "找不到 Codex 的用量紀錄"),
                "weekly": _window(None, None, 10080, now, src, False, "找不到 Codex 的用量紀錄"),
                "observed_at": None, "plan": None}
    ts, rl = best

    def win(w, minutes):
        if not w:
            return _window(None, None, minutes, now, src, False, "紀錄裡沒有這個視窗")
        reset = datetime.fromtimestamp(w["resets_at"], timezone.utc) if w.get("resets_at") else None
        return _window(float(w.get("used_percent")), reset, w.get("window_minutes") or minutes, now, src, True)

    return {"five_hour": win(rl.get("primary"), 300), "weekly": win(rl.get("secondary"), 10080),
            "observed_at": ts, "plan": rl.get("plan_type")}


# ── Claude Code ────────────────────────────────────────────────────────

_LIMIT_RE = re.compile(r"(weekly|session|5-hour|five-hour|daily|opus|sonnet)?\s*limit[^\n\"]{0,40}?resets\s+"
                       r"([A-Za-z]{3,9}\s+\d{1,2},\s*)?(\d{1,2}(?::\d{2})?\s*[ap]m)\s*(?:\(([^)]+)\))?", re.I)


def parse_limit(text: str, at: datetime) -> tuple[str, datetime] | None:
    """('weekly'|'five_hour', reset time) from a Claude limit message seen at `at`."""
    m = _LIMIT_RE.search(text)
    if not m:
        return None
    which = "weekly" if (m.group(1) or "").lower() in ("weekly", "opus", "sonnet") else "five_hour"
    tz = timezone.utc
    if m.group(4):
        try:
            tz = ZoneInfo(m.group(4).strip())
        except Exception:  # noqa: BLE001
            tz = timezone.utc
    local = at.astimezone(tz)
    clock = m.group(3).replace(" ", "").lower()
    fmt = "%I:%M%p" if ":" in clock else "%I%p"
    t = datetime.strptime(clock, fmt)
    if m.group(2):
        day = datetime.strptime(m.group(2).strip().rstrip(",") + f" {local.year}", "%b %d %Y")
        reset = local.replace(month=day.month, day=day.day, hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if reset < local - timedelta(days=1):
            reset = reset.replace(year=reset.year + 1)
    else:
        reset = local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if reset <= local:
            reset += timedelta(days=1)
    return which, reset.astimezone(timezone.utc)


def _claude_file(path: Path):
    hours: dict[str, list[int]] = {}   # hour bucket iso -> [input+cache_write, output, cache_read]
    limits: list[tuple[str, str, str]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            is_usage = '"usage"' in line and '"assistant"' in line
            is_limit = "resets" in line and "limit" in line
            if not (is_usage or is_limit):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            ts = _parse_ts(d.get("timestamp"))
            if not ts:
                continue
            msg = d.get("message") or {}
            if is_limit and d.get("type") == "assistant":
                for c in msg.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text" and len(c.get("text", "")) < 300:
                        got = parse_limit(c["text"], ts)
                        if got:
                            limits.append((ts.isoformat(), got[0], got[1].isoformat()))
            u = msg.get("usage")
            if is_usage and d.get("type") == "assistant" and isinstance(u, dict):
                b = hours.setdefault(ts.replace(minute=0, second=0, microsecond=0).isoformat(), [0, 0, 0])
                b[0] += int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
                b[1] += int(u.get("output_tokens") or 0)
                b[2] += int(u.get("cache_read_input_tokens") or 0)
    return {"hours": hours, "limits": limits}


def claude_usage(now: datetime | None = None, home: Path | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = (home or HOME) / ".claude" / "projects"
    hours: dict[str, list[int]] = {}
    limits: list[tuple[str, str, str]] = []
    for p in _recent(root.glob("**/*.jsonl")):
        got = _cached(p, _claude_file)
        for h, v in got["hours"].items():
            b = hours.setdefault(h, [0, 0, 0])
            for i in range(3):
                b[i] += v[i]
        limits += got["limits"]
    src = "~/.claude/projects 用量與額度訊息"

    def tokens_since(start: datetime) -> int:
        return sum(v[0] + v[1] for h, v in hours.items() if datetime.fromisoformat(h) >= start - timedelta(hours=1))

    out = {"observed_at": max((h for h in hours), default=None), "plan": None}
    for which, minutes in (("five_hour", 300), ("weekly", 10080)):
        span = FIVE_H if which == "five_hour" else WEEK
        hits = sorted((l for l in limits if l[1] == which), key=lambda l: l[0])
        last = hits[-1] if hits else None
        reset = datetime.fromisoformat(last[2]) if last else None
        if reset and reset > now:
            out[which] = _window(100.0, reset, minutes, now, src, True, f"Claude 回報已達上限（{last[0][:16]}）",
                                 tokens_since(reset - span))
        else:
            start = (reset if reset and reset + span > now else now - span) if which == "weekly" else now - span
            nxt = (reset + span) if reset and which == "weekly" and reset + span > now else None
            out[which] = _window(None, nxt, minutes, now, src, False,
                                 "百分比未知（Claude 不在本機記錄），顯示視窗內 tokens（不含快取讀取）",
                                 tokens_since(start))
    return out


# ── Cursor CLI ─────────────────────────────────────────────────────────

_CURSOR_LIMIT = re.compile(r"usage limit|hit your (usage )?limit|limit reached|spend(ing)? limit|out of (usage|credits)", re.I)


def _cursor_log(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    toks, seen = 0, False
    for line in text.splitlines():
        if '"usage"' in line and line.lstrip().startswith("{"):
            try:
                u = json.loads(line).get("usage") or {}
            except ValueError:
                continue
            seen = True
            toks += int(u.get("inputTokens") or 0) + int(u.get("outputTokens") or 0) + int(u.get("cacheWriteTokens") or 0)
    lim = next((ln.strip()[:200] for ln in text.splitlines()[-60:] if _CURSOR_LIMIT.search(ln)), None)
    return {"tokens": toks if seen else None, "limit": lim, "mtime": path.stat().st_mtime}


def cursor_usage(now: datetime | None = None, logs: Path | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = [_cached(p, _cursor_log) for p in _recent((logs or LOGS).glob("card*_cursor*.log"))]
    src = "launch_agent.py --output-format json 的 usage（估計）"
    note = "Cursor 方案按月計，沒有 5 小時／週額度；百分比未知"

    def toks(span):
        """Tokens of the runs in the window that logged usage; None if none did
        (older runs used --output-format text, which has no usage)."""
        cut = (now - span).timestamp()
        got = [r["tokens"] for r in rows if r["mtime"] >= cut and r["tokens"] is not None]
        return sum(got) if got else None

    lim = next((r["limit"] for r in sorted(rows, key=lambda r: -r["mtime"]) if r["limit"]), None)
    out = {"observed_at": datetime.fromtimestamp(max((r["mtime"] for r in rows), default=0), timezone.utc).isoformat()
           if rows else None, "plan": None, "limit_message": lim}
    out["five_hour"] = _window(None, None, None, now, src, False, note, toks(FIVE_H))
    out["weekly"] = _window(None, None, None, now, src, False, note, toks(WEEK))
    return out


def collect(force: bool = False) -> dict:
    if not force and _cache["data"] and time.monotonic() - _cache["at"] < TTL:
        return _cache["data"]
    now = datetime.now(timezone.utc)
    data = {"generated_at": now.isoformat(), "agents": {}}
    for name, fn in (("Claude Code", claude_usage), ("Codex", codex_usage), ("Cursor CLI", cursor_usage)):
        try:
            data["agents"][name] = fn(now)
        except Exception as e:  # noqa: BLE001 — a panel number, never fail the board
            data["agents"][name] = {"error": f"{type(e).__name__}: {e}"[:200]}
    _cache.update(at=time.monotonic(), data=data)
    return data
