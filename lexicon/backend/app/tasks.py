"""排程 (Schedule): a board of task cards and the AIs that pull them.

Left, the AIs (bots): every Claude session or Codex app that reports here,
and the local Qwen model. Right, the deck: cards from top to bottom that an
idle AI pulls and works on —

* one-off cards: a request the owner made (in chat or on the page);
* 問題回報 cards: every open bug / unbuilt requirement not yet taken (a
  virtual card until an AI claims it, which links a task to the issue);
* standing (recurring) cards: checks that come back every interval — scan
  which words lack pictures, which pictures' labels aren't finished, which
  label levels look wrong. Between runs they wait as 「等下次執行」; their
  card shows a live number (METRICS) so the owner sees the backlog.

An AI claims a card (POST /schedule/claim, `tasks.py next`), reports progress
and finishes it; a finished standing card goes back to waiting for its next
run. `/schedule/background` adds what runs without an AI session: import jobs,
the picture queue, and what the local Qwen model is answering this moment.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field as PField
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import agent_usage, config, db, issues, jobs
from . import models as m

STATUSES = {"queued": "排隊中", "in_progress": "進行中", "waiting": "等你回覆",
            "blocked": "卡住", "scheduled": "等下次執行", "done": "完成", "cancelled": "取消"}
KINDS = {"once": "一次性", "recurring": "常態"}
ACTIVE = ("queued", "in_progress", "waiting", "blocked")
WORKING = ("in_progress", "waiting", "blocked")
CLOSED = ("done", "cancelled")
TRACKED = ("status", "agent", "progress", "title", "difficulty")
# Card difficulty (card #156); who may take which level: lexicon/tools/agent_capabilities.json.
DIFFICULTY = {1: "簡單", 2: "中等", 3: "困難", 4: "極難"}
# An AI that hasn't touched its in-progress card for this long may have stopped.
STALE_AFTER = timedelta(minutes=30)
# An AI not heard from for this long is shown as offline.
OFFLINE_AFTER = timedelta(hours=2)
CLAIM_LOCK = 770000100
# Bots the owner paused on the board (start/pause button). A paused bot keeps
# the card it is on (it may finish it) but can't claim a new one; launch_agent.py
# won't start it; a paused Grokbot means the dispatcher routine dispatches nothing.
# Qwen (local model) uses the same file; the tagger rejects new inference with 503.
from .agent_pause import paused_agents, set_paused  # noqa: E402


# ── Standing cards' live numbers ──────────────────────────────────────

def _pictures_missing(s: Session) -> dict:
    # picture_need: only a full noun needs a picture. Other parts of speech
    # show that noun's pictures and are not counted here.
    from .picture_need import missing_stats
    stats = missing_stats(s)
    return {"value": stats["missing"],
            "label": f"個名詞沒有圖片（需要圖的名詞 {stats['need']} 個，詞庫 {stats['words']} 字）",
            "detail": f"等待下載 {stats['fetch']} 個字 · 等待審核 {stats['review']} 張"}


def _labelled_since_pause(s: Session) -> int | None:
    """Done pictures whose tagged_at is at or after the owner's Qwen pause.

    None when Qwen is not paused. Read-only; the running API keeps the old
    response until it is restarted.
    """
    raw = paused_agents().get("Qwen")
    if not raw:
        return None
    try:
        since = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    n = s.scalar(select(func.count()).select_from(m.ImageAsset).where(
        m.ImageAsset.tagged_at >= since, m.ImageAsset.tag_status == "done"))
    return int(n or 0)


def _labels_pending(s: Session) -> dict:
    rows = dict(s.execute(text("SELECT tag_status, count(*) FROM image_assets WHERE status = 'ready' "
                               "GROUP BY tag_status")).all())
    hour = s.scalar(text("SELECT count(*) FROM image_assets WHERE tag_status = 'done' "
                         "AND tagged_at > now() - interval '1 hour'"))
    return {"value": rows.get("pending", 0), "label": "張圖片的 AI 標籤還沒完成",
            "detail": f"失敗 {rows.get('failed', 0)} · 已完成 {rows.get('done', 0)} · 過去 1 小時 {hour}"}


def _label_levels(s: Session) -> dict:
    rows = dict(s.execute(text("""SELECT coalesce(t->>'cefrSource', '') , count(*) FROM image_assets a,
        jsonb_array_elements(coalesce(a.tags::jsonb, '[]'::jsonb)) t
        WHERE a.tag_status = 'done' GROUP BY 1""")).all())
    total = sum(rows.values())
    return {"value": rows.get("estimate", 0), "label": "個標籤的等級是估算的（最可能分錯級）",
            "detail": f"共 {total} 個標籤 · 查 CEFR 表 {rows.get('cefrj', 0)} · 由原形推得 "
                      f"{rows.get('base', 0)} · 片語 {rows.get('phrase', 0)}"}


# app/test/simulation/run_round.py writes each round here.
ROUNDS = Path(__file__).resolve().parents[3] / "app" / "build" / "rounds"


def _simulation(s: Session) -> dict:
    found = s.scalar(text("SELECT count(*) FROM issue_reports WHERE reporter = 'claude-simulation' "
                          "AND status NOT IN ('fixed', 'wont_fix')"))
    rounds = sorted((int(p.name) for p in ROUNDS.glob("*") if p.name.isdigit()), reverse=True)
    for n in rounds:
        summary = ROUNDS / str(n) / "summary.json"
        if summary.exists():
            r = json.loads(summary.read_text(encoding="utf-8"))
            total, failed = len(r.get("results", {})), r.get("failed", [])
            return {"value": len(failed), "label": f"個模擬在第 {n} 輪失敗（共 {total} 個）",
                    "detail": f"{r.get('finished', '')} · " + (f"失敗：{'、'.join(failed)} · " if failed else "")
                              + f"模擬找到、還沒處理的問題 {found} 個"}
    return {"value": found, "label": "個模擬找到的問題還沒處理",
            "detail": f"最近一輪：第 {rounds[0]} 輪（舊格式，沒有摘要）" if rounds else "還沒跑過模擬"}


METRICS = {"pictures_missing": ("缺圖片的字", _pictures_missing),
           "labels_pending": ("未完成的圖片標籤", _labels_pending),
           "label_levels": ("可能分錯級的標籤", _label_levels),
           "simulation": ("模擬使用者的結果", _simulation)}


CAPABILITIES = config.HOME / "tools" / "agent_capabilities.json"
_caps: dict = {"at": None, "data": {}}


def capabilities() -> dict:
    """lexicon/tools/agent_capabilities.json, re-read at most once a minute."""
    now = datetime.now(timezone.utc)
    if _caps["at"] is None or now - _caps["at"] > timedelta(seconds=60):
        try:
            _caps["data"] = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            _caps["data"] = {"error": f"讀不到 agent_capabilities.json：{e}"}
        _caps["at"] = now
    return _caps["data"]


# ── API bodies and helpers ────────────────────────────────────────────

class TaskBody(BaseModel):
    title: str | None = PField(default=None, max_length=300)
    detail: str | None = None
    status: str | None = None
    agent: str | None = PField(default=None, max_length=64)
    requested_by: str | None = PField(default=None, max_length=64)
    progress: str | None = None
    issue_ids: list[int] | None = None
    kind: str | None = None
    interval_minutes: int | None = PField(default=None, ge=5)
    metric: str | None = None
    position: float | None = None
    difficulty: int | None = PField(default=None, ge=1, le=4)
    difficulty_reason: str | None = None
    next_run_at: datetime | None = None   # a standing card: now = 「立刻排入」
    by: str | None = None            # who made this change (an AI's name, or owner)
    note: str | None = None          # a line for the history, not stored as a field


class ClaimBody(BaseModel):
    agent: str = PField(min_length=1, max_length=64)
    task_id: int | None = None       # this card, or
    issue_id: int | None = None      # this 問題回報 card, or neither: the top of the deck
    pile: str | None = None          # with neither: only from 「once」 or 「recurring」


class DifficultyBody(BaseModel):
    task_id: int | None = None
    issue_id: int | None = None
    difficulty: int | None = PField(default=None, ge=1, le=4)   # None clears it
    reason: str | None = None
    by: str | None = None


class AssignBody(BaseModel):
    agent: str = PField(min_length=1, max_length=64)
    task_id: int | None = None
    issue_id: int | None = None


class HelloBody(BaseModel):
    agent: str = PField(min_length=1, max_length=64)
    kind: str | None = None
    note: str | None = None


# The board lists 400+ cards; their full history made it ~800 KB and slow
# (card #445). Board cards carry only the recent entries (a standing card: every
# entry since its last run, which dispatch_tick's cooldown check reads); the
# whole history comes with GET /tasks/<id>.
BOARD_HISTORY = 3
BOARD_HISTORY_SINCE_RUN = 50


def _board_history(t: m.AgentTask) -> list:
    h = list(t.history or [])
    keep = h[-BOARD_HISTORY:]
    if t.kind == "recurring" and t.last_run_at:
        last = t.last_run_at.isoformat()
        since = [e for e in h if str(e.get("at") or "") > last][-BOARD_HISTORY_SINCE_RUN:]
        if len(since) > len(keep):
            keep = since
    return keep


def task_dict(t: m.AgentTask, full: bool = True) -> dict:
    d = {c: getattr(t, c) for c in (
        "id", "title", "detail", "status", "agent", "requested_by", "progress", "issue_ids",
        "history", "created_at", "updated_at", "started_at", "finished_at", "kind",
        "interval_minutes", "next_run_at", "last_run_at", "last_result", "metric", "position",
        "difficulty", "difficulty_reason", "stage", "stage_state", "stage_note", "stage_at")}
    now = datetime.now(timezone.utc)
    d["stale"] = bool(t.status == "in_progress" and t.updated_at and now - t.updated_at > STALE_AFTER)
    d["due"] = bool(t.kind == "recurring" and t.status == "scheduled"
                    and (t.next_run_at is None or t.next_run_at <= now))
    if not full:
        d["history_n"] = len(t.history or [])
        d["history"] = _board_history(t)
    return d


# ── Slow numbers, served from a cache refreshed in the background (card #445) ──
# The standing cards' metrics scan every picture's tags (5–6 s) and the tagger's
# /activity can take 2–3 s while Qwen is busy. The board serves the last value
# and, once it is older than its TTL, refreshes it in a background thread, so a
# board request never waits for them (only the very first one does).

_slow: dict[str, dict] = {}
_slow_lock = threading.Lock()
SLOW_TTL = {"metric": 60.0, "qwen": 5.0}


def _slow_refresh(key: str, compute) -> None:
    try:
        value = compute()
    except Exception as e:  # noqa: BLE001 — keep the old value, note the error
        value = None
        err = f"{type(e).__name__}: {e}"
    else:
        err = None
    with _slow_lock:
        e = _slow.setdefault(key, {})
        if err is None:
            e.update(value=value, at=time.monotonic(), has=True)
        e["busy"] = False
        e["error"] = err


def slow_value(key: str, ttl: float, compute, compute_now=None):
    """[compute] runs in the background thread; [compute_now] (default: the same)
    on the first request, which has nothing cached to serve."""
    now = time.monotonic()
    with _slow_lock:
        e = _slow.get(key)
        fresh = e is not None and e.get("has") and now - e["at"] < ttl
        if e is not None and e.get("has") and not fresh and not e.get("busy"):
            e["busy"] = True
            threading.Thread(target=_slow_refresh, args=(key, compute), daemon=True,
                             name=f"board-{key}").start()
        if e is not None and e.get("has"):
            return e["value"]
    _slow_refresh(key, compute_now or compute)   # first request: compute now
    with _slow_lock:
        e = _slow[key]
        if not e.get("has"):
            raise RuntimeError(e.get("error") or "no value")
        return e["value"]


def clear_slow_cache() -> None:
    with _slow_lock:
        _slow.clear()


def _metric_in_own_session(name: str):
    def compute():
        with db.session_scope() as s:
            return METRICS[name][1](s)
    return compute


def _touch(s: Session, name: str | None, kind: str | None = None, note: str | None = None):
    """Record that an AI was heard from (any change it makes counts)."""
    if not name or name == "owner":
        return
    a = s.get(m.Agent, name) or m.Agent(name=name, kind=kind or "ai")
    a.last_seen = datetime.now(timezone.utc)
    if kind:
        a.kind = kind
    if note is not None:
        a.note = note.strip() or None
    s.add(a)


def _apply(t: m.AgentTask, data: dict, note: str | None, by: str):
    now = datetime.now(timezone.utc)
    changes = []
    # A finished standing card isn't done for good: it waits for its next run.
    if t.kind == "recurring" and data.get("status") == "done":
        data = {**data, "status": "scheduled", "agent": None}
        t.last_run_at = now
        t.last_result = (data.get("progress") or t.progress or "").strip() or None
        t.next_run_at = now + timedelta(minutes=t.interval_minutes or 360)
        note = note or "這次檢查完成，等下次執行"
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        if getattr(t, key) == value:
            continue
        if key in TRACKED:
            changes.append({"field": key, "from": getattr(t, key), "to": value})
        setattr(t, key, value)
    if "status" in data:
        if t.status == "in_progress" and (t.started_at is None or t.kind == "recurring"):
            t.started_at = now
        t.finished_at = now if t.status in CLOSED else None
    if changes or note:
        t.updated_at = now
        t.history = [*(t.history or []), {"at": now.isoformat(), "by": by, "changes": changes,
                                          "note": (note or "").strip() or None}]


def _check(body: TaskBody):
    if body.status is not None and body.status not in STATUSES:
        raise HTTPException(422, f"不認得的狀態：{body.status}")
    if body.kind is not None and body.kind not in KINDS:
        raise HTTPException(422, f"不認得的卡片類型：{body.kind}")
    if body.metric is not None and body.metric not in METRICS:
        raise HTTPException(422, f"不認得的統計：{body.metric}")


def qwen_activity() -> dict:
    """The tagging service's GET /activity: the requests the local model is
    answering now, and how many of llama-server's slots are busy."""
    request = urllib.request.Request(config.AI_URL.rstrip("/") + "/activity",
                                     headers={"X-API-Key": config.AI_KEY or ""})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return {"ok": True, **json.loads(response.read())}
    except urllib.error.HTTPError as e:
        why = "標籤服務還是舊版，重啟後才有這項資訊" if e.code == 404 else f"HTTP {e.code}"
        return {"ok": False, "error": why}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "error": f"標籤服務沒有回應：{e}"}


# ── The board ─────────────────────────────────────────────────────────

def _taken_issue_ids(s: Session) -> set[int]:
    out: set[int] = set()
    for ids in s.execute(select(m.AgentTask.issue_ids).where(m.AgentTask.status.in_(WORKING))).scalars():
        out.update(ids or [])
    return out


def _issue_card(r: m.IssueReport) -> dict:
    return {"card": "issue", "issue_id": r.id, "title": r.title, "detail": r.detail,
            "kind": r.kind, "severity": r.severity, "area": r.area, "reporter": r.reporter,
            "created_at": r.created_at, "difficulty": r.difficulty, "difficulty_reason": r.difficulty_reason}


def deck(s: Session) -> list[dict]:
    """Cards waiting for an AI, top first: standing checks that are due, the
    owner's queued requests, then open 問題回報 nobody has taken."""
    now = datetime.now(timezone.utc)
    due = s.execute(select(m.AgentTask).where(
        m.AgentTask.kind == "recurring", m.AgentTask.status == "scheduled",
        (m.AgentTask.next_run_at.is_(None)) | (m.AgentTask.next_run_at <= now))
        .order_by(m.AgentTask.next_run_at.nulls_first(), m.AgentTask.position)).scalars().all()
    queued = s.execute(select(m.AgentTask).where(m.AgentTask.status == "queued")
                       .order_by(m.AgentTask.position, m.AgentTask.created_at)).scalars().all()
    taken = _taken_issue_ids(s) | {i for t in queued for i in (t.issue_ids or [])}
    queued = [t for t in queued if not t.agent]  # a card handed to an AI waits under it
    sev = {"high": 0, "medium": 1, "low": 2}
    open_issues = sorted((r for r in s.execute(select(m.IssueReport).where(
        m.IssueReport.status == "open", m.IssueReport.kind.in_(("bug", "todo")))).scalars()
        if r.id not in taken), key=lambda r: (sev.get(r.severity, 9), r.id))
    return ([{"card": "task", **task_dict(t, full=False)} for t in due + queued]
            + [_issue_card(r) for r in open_issues])


def board(s: Session) -> dict:
    now = datetime.now(timezone.utc)
    working = s.execute(select(m.AgentTask).where(m.AgentTask.status.in_(WORKING))
                        .order_by(m.AgentTask.updated_at.desc())).scalars().all()
    bots: dict[str, dict] = {}
    for a in s.execute(select(m.Agent)).scalars():
        bots[a.name] = {"agent": a.name, "kind": a.kind, "last_seen": a.last_seen, "note": a.note,
                        "doing": [], "assigned": []}
    assigned = s.execute(select(m.AgentTask).where(m.AgentTask.status == "queued",
                                                   m.AgentTask.agent.is_not(None))
                         .order_by(m.AgentTask.position, m.AgentTask.created_at)).scalars().all()
    for t in [*working, *assigned]:
        if not t.agent:
            continue
        b = bots.setdefault(t.agent, {"agent": t.agent, "kind": "ai", "last_seen": t.updated_at,
                                      "note": None, "doing": [], "assigned": []})
        b["assigned" if t.status == "queued" else "doing"].append(task_dict(t, full=False))
    for b in bots.values():
        doing = b["doing"]
        seen = b["last_seen"]
        if any(d["status"] == "in_progress" and not d["stale"] for d in doing):
            b["state"] = "working"
        elif any(d["status"] == "waiting" for d in doing):
            b["state"] = "waiting"
        elif doing:
            b["state"] = "stale" if any(d["stale"] for d in doing) else "blocked"
        else:
            b["state"] = "offline" if seen and now - seen > OFFLINE_AFTER else "idle"
    # Always show the local model as a bot so the owner can pause/resume it.
    qa = slow_value("qwen", SLOW_TTL["qwen"], qwen_activity)
    slots = (qa.get("slots") or {}) if qa.get("ok") else {}
    reqs = list(qa.get("requests") or []) if qa.get("ok") else []
    busy_n = slots.get("busy")
    try:
        busy_n = int(busy_n) if busy_n is not None else len(reqs)
    except (TypeError, ValueError):
        busy_n = len(reqs)
    qwen_note = None
    if reqs:
        qwen_note = '、'.join(
            f"{r.get('kind', '?')}:{(r.get('what') or '—')[:40]}" for r in reqs[:3])
    elif qa.get("ok") and slots.get("total") is not None:
        qwen_note = f"{slots.get('busy', 0)}/{slots.get('total')} slots busy"
    elif not qa.get("ok"):
        qwen_note = qa.get("error") or "tagger not responding"
    qwen_bot = bots.setdefault("Qwen", {"agent": "Qwen", "kind": "model", "last_seen": None,
                                        "note": None, "doing": [], "assigned": []})
    qwen_bot["kind"] = "model"
    qwen_bot["note"] = qwen_note
    qwen_bot["last_seen"] = now if qa.get("ok") else qwen_bot.get("last_seen")
    if not qa.get("ok"):
        qwen_bot["state"] = "offline"
    elif busy_n or reqs:
        qwen_bot["state"] = "working"
    else:
        qwen_bot["state"] = "idle"

    paused = paused_agents()
    for name in paused:
        bots.setdefault(name, {"agent": name, "kind": "ai", "last_seen": None, "note": None,
                               "doing": [], "assigned": [], "state": "idle"})
    for b in bots.values():
        b["paused"] = b["agent"] in paused
        b["paused_at"] = paused.get(b["agent"])
    order = {"working": 0, "waiting": 1, "blocked": 2, "stale": 3, "idle": 4, "offline": 5}
    recurring = []
    for t in s.execute(select(m.AgentTask).where(m.AgentTask.kind == "recurring")
                       .order_by(m.AgentTask.position, m.AgentTask.id)).scalars():
        d = task_dict(t, full=False)
        if t.metric in METRICS:
            try:
                d["metric_value"] = slow_value("metric:" + t.metric, SLOW_TTL["metric"],
                                               _metric_in_own_session(t.metric),
                                               lambda f=METRICS[t.metric][1]: f(s))
            except Exception as e:  # noqa: BLE001 — a number, not worth failing the board
                d["metric_value"] = {"value": None, "label": f"算不出來：{type(e).__name__}"}
        recurring.append(d)
    done = s.execute(select(m.AgentTask).where(m.AgentTask.status.in_(CLOSED))
                     .order_by(m.AgentTask.updated_at.desc()).limit(15)).scalars().all()
    the_deck = deck(s)
    return {"bots": sorted(bots.values(), key=lambda b: (order[b["state"]], b["agent"])),
            "deck": the_deck, "recurring": recurring,
            "issues": open_issues_elsewhere(s, the_deck),
            "done": [task_dict(t, full=False) for t in done]}


def open_issues_elsewhere(s: Session, the_deck: list[dict]) -> list[dict]:
    """Every open 問題回報 that is NOT a deck card (decisions, or ones attached to a
    standing / handed-out card), each with the cards it is attached to, so no open
    report is invisible on the 排程 board."""
    in_deck = {c["issue_id"] for c in the_deck if c.get("card") == "issue"}
    rows = [r for r in s.execute(select(m.IssueReport).where(m.IssueReport.status == "open")
                                 .order_by(m.IssueReport.id)).scalars() if r.id not in in_deck]
    if not rows:
        return []
    want = {r.id for r in rows}
    links: dict[int, list[dict]] = {}
    for t in s.execute(select(m.AgentTask).where(m.AgentTask.status.not_in(CLOSED))).scalars():
        for i in t.issue_ids or []:
            if i in want:
                links.setdefault(i, []).append({"id": t.id, "title": t.title, "status": t.status,
                                                "agent": t.agent, "kind": t.kind})
    sev = {"high": 0, "medium": 1, "low": 2}
    out = [{**_issue_card(r), "linked": links.get(r.id, [])} for r in rows]
    return sorted(out, key=lambda c: (c["kind"] != "decision", sev.get(c["severity"], 9), c["issue_id"]))


def _pile(card: dict) -> str:
    return "recurring" if card.get("card") == "task" and card.get("kind") == "recurring" else "once"


def claim(s: Session, agent: str, task_id: int | None = None, issue_id: int | None = None,
          pile: str | None = None) -> m.AgentTask:
    """Give a card to [agent] to work on now: that task, that 問題回報, or —
    neither given — the first card the owner handed to it, else the top of
    the deck (only from [pile] — 「once」 or 「recurring」 — when given)."""
    if agent in paused_agents():
        raise HTTPException(423, f"{agent} 已暫停，不能接新卡；請先在看板按「開始」（POST /agents/{agent}/resume）")
    s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CLAIM_LOCK})
    if task_id is None and issue_id is None:
        mine = s.execute(select(m.AgentTask.id).where(
            m.AgentTask.status == "queued", m.AgentTask.agent == agent)
            .order_by(m.AgentTask.position, m.AgentTask.created_at).limit(1)).scalar()
        if pile not in (None, "once", "recurring"):
            raise HTTPException(422, f"不認得的牌堆：{pile}")
        top = {"id": mine} if mine else next(
            (c for c in deck(s) if pile is None or _pile(c) == pile), None)
        if top is None:
            raise HTTPException(404, "牌堆是空的，沒有可以接的卡")
        task_id, issue_id = top.get("id"), top.get("issue_id")
    if task_id is not None:
        t = s.get(m.AgentTask, task_id)
        if not t:
            raise HTTPException(404, "找不到這張卡")
        if t.status in WORKING and t.agent and t.agent != agent:
            raise HTTPException(409, f"這張卡已經由 {t.agent} 在做")
        _apply(t, {"status": "in_progress", "agent": agent, "progress": None}, "接手這張卡", agent)
        for r in s.execute(select(m.IssueReport).where(
                m.IssueReport.id.in_(t.issue_ids or []), m.IssueReport.status == "open")).scalars():
            issues._apply(r, {"status": "in_progress"}, f"{agent} 接手（排程 #{t.id}）", agent)
    else:
        r = s.get(m.IssueReport, issue_id)
        if not r:
            raise HTTPException(404, "找不到這筆問題回報")
        if issue_id in _taken_issue_ids(s):
            raise HTTPException(409, "這筆問題回報已經有 AI 在做")
        t = m.AgentTask(title=f"問題回報 #{r.id}：{r.title}"[:300], detail=r.detail, issue_ids=[r.id],
                        requested_by="問題回報", kind="once", history=[],
                        difficulty=r.difficulty, difficulty_reason=r.difficulty_reason)
        s.add(t)
        _apply(t, {"status": "in_progress", "agent": agent}, f"從問題回報 #{r.id} 接手", agent)
        s.flush()
        issues._apply(r, {"status": "in_progress"}, f"{agent} 接手（排程 #{t.id}）", agent)
    _touch(s, agent)
    s.flush()
    return t


def assign(s: Session, agent: str, task_id: int | None, issue_id: int | None) -> m.AgentTask:
    """The owner hands a card to an AI (dragged onto it): it waits under that
    AI, which takes it before the deck's top card. A standing card handed over
    runs now."""
    s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CLAIM_LOCK})
    if task_id is not None:
        t = s.get(m.AgentTask, task_id)
        if not t:
            raise HTTPException(404, "找不到這張卡")
        if t.status in WORKING:
            raise HTTPException(409, f"這張卡已經由 {t.agent} 在做")
        _apply(t, {"agent": agent, "status": "queued"}, f"交給 {agent}", "owner")
    elif issue_id is not None:
        r = s.get(m.IssueReport, issue_id)
        if not r:
            raise HTTPException(404, "找不到這筆問題回報")
        if issue_id in _taken_issue_ids(s) | {i for ids in s.execute(select(m.AgentTask.issue_ids).where(
                m.AgentTask.status == "queued")).scalars() for i in (ids or [])}:
            raise HTTPException(409, "這筆問題回報已經排給別的 AI")
        t = m.AgentTask(title=f"問題回報 #{r.id}：{r.title}"[:300], detail=r.detail, issue_ids=[r.id],
                        requested_by="問題回報", kind="once", history=[],
                        difficulty=r.difficulty, difficulty_reason=r.difficulty_reason)
        s.add(t)
        _apply(t, {"status": "queued", "agent": agent}, f"交給 {agent}", "owner")
    else:
        raise HTTPException(422, "要指定一張卡")
    s.flush()
    return t


# ── API ───────────────────────────────────────────────────────────────

def register(app, auth):
    DB = Depends(db.get_session)

    @app.get("/tasks/meta", dependencies=[auth])
    def tasks_meta():
        return {"statuses": STATUSES, "kinds": KINDS, "difficulties": DIFFICULTY,
                "metrics": {k: label for k, (label, _) in METRICS.items()},
                "stale_minutes": int(STALE_AFTER.total_seconds() // 60)}

    @app.get("/schedule/board", dependencies=[auth])
    def get_board(s: Session = DB):
        return board(s)

    @app.post("/schedule/claim", dependencies=[auth])
    def post_claim(body: ClaimBody, s: Session = DB):
        return task_dict(claim(s, body.agent.strip(), body.task_id, body.issue_id, body.pile))

    @app.put("/schedule/difficulty", dependencies=[auth])
    def put_difficulty(body: DifficultyBody, s: Session = DB):
        """Set (or clear) a card's difficulty: a task or an open 問題回報."""
        by = body.by or "owner"
        reason = (body.reason or "").strip() or None
        if body.task_id is not None:
            t = s.get(m.AgentTask, body.task_id)
            if not t:
                raise HTTPException(404, "找不到這張卡")
            _apply(t, {"difficulty": body.difficulty, "difficulty_reason": reason},
                   f"難度 → {DIFFICULTY.get(body.difficulty, '未定')}", by)
            s.flush()
            return task_dict(t)
        if body.issue_id is not None:
            r = s.get(m.IssueReport, body.issue_id)
            if not r:
                raise HTTPException(404, "找不到這筆問題回報")
            r.difficulty, r.difficulty_reason = body.difficulty, reason
            s.flush()
            return _issue_card(r)
        raise HTTPException(422, "要指定一張卡（task_id 或 issue_id）")

    @app.get("/schedule/agents-info", dependencies=[auth])
    def agents_info(refresh: bool = False):
        """The AI 機器人 panel: what each AI may take (agent_capabilities.json)
        and its 5-hour / weekly usage (agent_usage.collect, cached)."""
        return {"capabilities": capabilities(), "usage": agent_usage.collect(force=refresh)}

    @app.post("/schedule/assign", dependencies=[auth])
    def post_assign(body: AssignBody, s: Session = DB):
        return task_dict(assign(s, body.agent.strip(), body.task_id, body.issue_id))

    @app.post("/agents/hello", dependencies=[auth])
    def hello(body: HelloBody, s: Session = DB):
        _touch(s, body.agent.strip(), body.kind, body.note)
        return {"ok": True}

    @app.post("/agents/{name}/pause", dependencies=[auth])
    def pause_agent(name: str):
        return {"agent": name, "paused": True, "paused_agents": set_paused(name.strip(), True)}

    @app.post("/agents/{name}/resume", dependencies=[auth])
    def resume_agent(name: str):
        return {"agent": name, "paused": False, "paused_agents": set_paused(name.strip(), False)}

    @app.delete("/agents/{name}", dependencies=[auth], status_code=204)
    def forget_agent(name: str, s: Session = DB):
        a = s.get(m.Agent, name)
        if a:
            s.delete(a)

    @app.get("/tasks", dependencies=[auth])
    def list_tasks(status: str | None = None, agent: str | None = None, s: Session = DB):
        stmt = select(m.AgentTask)
        if status == "active":
            stmt = stmt.where(m.AgentTask.status.in_(ACTIVE))
        elif status == "closed":
            stmt = stmt.where(m.AgentTask.status.in_(CLOSED))
        elif status:
            stmt = stmt.where(m.AgentTask.status == status)
        if agent:
            stmt = stmt.where(m.AgentTask.agent == agent)
        order = {"waiting": 0, "in_progress": 1, "blocked": 2, "queued": 3, "scheduled": 4,
                 "done": 5, "cancelled": 6}
        rows = sorted(s.execute(stmt).scalars(),
                      key=lambda t: (order.get(t.status, 9),
                                     -(t.updated_at or t.created_at).timestamp()))
        counts = dict(s.execute(select(m.AgentTask.status, func.count())
                                .group_by(m.AgentTask.status)).all())
        return {"items": [task_dict(t) for t in rows], "counts": counts}

    @app.get("/tasks/agents", dependencies=[auth])
    def list_agents(s: Session = DB):
        return {"items": board(s)["bots"]}

    @app.get("/schedule/background", dependencies=[auth])
    def background(s: Session = DB):
        """Work that runs without an AI session: import jobs, the picture
        queue, and what the local Qwen model is answering this moment."""
        running = s.execute(select(m.ImportJob).where(
            m.ImportJob.status.in_(("running", "queued", "paused", "pausing")))
            .order_by(m.ImportJob.id)).scalars().all()
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        pictures = dict(s.execute(select(m.ImageAsset.tag_status, func.count()).where(
            m.ImageAsset.status == "ready").group_by(m.ImageAsset.tag_status)).all())
        labelled_hour = s.scalar(select(func.count()).select_from(m.ImageAsset).where(
            m.ImageAsset.tagged_at >= hour_ago, m.ImageAsset.tag_status == "done"))
        labelled_since_pause = _labelled_since_pause(s)
        fetch_waiting = s.scalar(select(func.count()).select_from(m.ImageFetchTask).where(
            m.ImageFetchTask.status.in_(("queued", "running"))))
        qwen = qwen_activity()
        # The pictures Qwen is labelling or just labelled, with the labels they
        # already carry (word, where it is, its score), drawn on the picture.
        ids = {int(r["ref"].split(":", 1)[1]) for r in [*qwen.get("requests", []), *qwen.get("recent", [])]
               if str(r.get("ref") or "").startswith("image:") and r["ref"].split(":", 1)[1].isdigit()}
        detail = {}
        for a in (s.execute(select(m.ImageAsset).where(m.ImageAsset.id.in_(ids))).scalars() if ids else []):
            words = s.execute(text("""SELECT DISTINCT l.normalized FROM sense_images si
                JOIN senses sn ON sn.id = si.sense_id JOIN lexemes l ON l.id = sn.lexeme_id
                WHERE si.image_asset_id = :id"""), {"id": a.id}).scalars().all()
            detail[a.id] = {
                "id": a.id, "words": list(words), "tag_status": a.tag_status,
                "safety_status": a.safety_status, "width": a.width, "height": a.height,
                "tags": [{k: t.get(k) for k in ("word", "point", "box", "score", "cefr", "pos")}
                         for t in (a.tags or []) if isinstance(t, dict)],
                "dropped": len(a.dropped_tags or [])}
        return {"jobs": [jobs.job_dict(j) for j in running],
                "pictures": {"pending": pictures.get("pending", 0), "done": pictures.get("done", 0),
                             "failed": pictures.get("failed", 0),
                             "labelled_last_hour": labelled_hour or 0,
                             "labelled_since_pause": labelled_since_pause,
                             "downloads_waiting": fetch_waiting or 0},
                "qwen": qwen, "pictures_detail": detail}

    @app.get("/schedule/picture/{asset_id}", dependencies=[auth])
    def schedule_picture(asset_id: int, s: Session = DB):
        """The picture behind one of Qwen's requests, for the owner's own
        board — also before the safety check has finished; only a picture the
        check blocked stays hidden."""
        a = s.get(m.ImageAsset, asset_id)
        if not a or a.status != "ready" or not a.path or a.safety_status == "blocked":
            raise HTTPException(404, "找不到圖片，或安全檢查判定不能顯示")
        path = (config.MEDIA / a.path).resolve()
        if not path.is_relative_to(config.MEDIA.resolve()) or not path.is_file():
            raise HTTPException(404, "找不到圖片檔案")
        return FileResponse(path, media_type=a.mime)

    @app.get("/tasks/{task_id}", dependencies=[auth])
    def get_task(task_id: int, s: Session = DB):
        t = s.get(m.AgentTask, task_id)
        if not t:
            raise HTTPException(404, "找不到這項任務")
        return task_dict(t)

    @app.post("/tasks", dependencies=[auth], status_code=201)
    def create_task(body: TaskBody, s: Session = DB):
        _check(body)
        if not (body.title or "").strip():
            raise HTTPException(422, "請填任務內容")
        data = body.model_dump(exclude={"note", "by"}, exclude_none=True)
        data.setdefault("requested_by", "owner")
        data.setdefault("kind", "once")
        recurring = data["kind"] == "recurring"
        data.setdefault("status", "scheduled" if recurring else "queued")
        if recurring:
            data.setdefault("interval_minutes", 360)
        t = m.AgentTask(title=data.pop("title").strip(), issue_ids=[], history=[],
                        kind=data.pop("kind"))
        s.add(t)
        _apply(t, data, body.note or "建立", body.by or data["requested_by"])
        _touch(s, body.by or body.agent)
        s.flush()
        return task_dict(t)

    @app.put("/tasks/{task_id}", dependencies=[auth])
    def update_task(task_id: int, body: TaskBody, s: Session = DB):
        _check(body)
        t = s.get(m.AgentTask, task_id)
        if not t:
            raise HTTPException(404, "找不到這項任務")
        data = body.model_dump(exclude={"note", "by"}, exclude_unset=True)
        if "title" in data and not (data["title"] or "").strip():
            raise HTTPException(422, "任務內容不能是空的")
        by = body.by or body.agent or "owner"
        _apply(t, data, body.note, by)
        _touch(s, by)
        s.flush()
        return task_dict(t)

    @app.delete("/tasks/{task_id}", dependencies=[auth], status_code=204)
    def delete_task(task_id: int, s: Session = DB):
        t = s.get(m.AgentTask, task_id)
        if not t:
            raise HTTPException(404, "找不到這項任務")
        s.delete(t)
