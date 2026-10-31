"""統一流程 (card #916, lexicon/docs/PIPELINE.md): which stage each card and 問題回報 is in.

lexicon/tools/flow_tick.py works the stages out from the facts (cards, mac_inbox,
mac_verify_results) and stores them here; nobody sets a stage by hand. This module
answers the overview page: cards per stage, what is stuck longest, whether this version
can ship and why, phone feedback → card and stage, and what needs the owner.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import config, db
from . import models as m

STAGES = {"dev": "開發", "windows_check": "Windows 檢查", "mac_verify": "Mac 驗證", "ipad_verify": "iPad 驗證",
          "ready": "可發布", "released": "已發布", "done": "完成（不需驗證）", "cancelled": "取消"}
FINISHED = ("released", "done", "cancelled")
VERIFYING = ("windows_check", "mac_verify", "ipad_verify")
ACTIVE_ISSUE = ("open", "in_progress", "needs_decision")
TOOLS = config.HOME / "tools"
STATE = config.HOME / "state"
FACTS = STATE / "flow_facts.json"
DIGEST = STATE / "daily_digest.json"
OWNER_CHECK_RE = re.compile(r"owner|手動|相機")
ACCOUNT_RE = re.compile(r"帳號|付款|條款|憑證|金鑰|App Store Connect|Google Play", re.I)
MAC_QUIET_HOURS = 48


class StageItem(BaseModel):
    type: str                       # task · issue
    id: int
    stage: str
    state: str | None = None
    note: str | None = None


class StagesBody(BaseModel):
    items: list[StageItem]
    by: str = "flow_tick"


def start_ids() -> dict:
    """First card / issue the pipeline follows: older rows are never rewritten."""
    cfg = json.loads((TOOLS / "dispatch_config.json").read_text(encoding="utf-8")).get("flow") or {}
    return {"task": int(cfg.get("start_task") or 0), "issue": int(cfg.get("start_issue") or 0)}


def _load(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def app_version() -> str | None:
    try:
        text = (config.HOME.parent / "app" / "pubspec.yaml").read_text(encoding="utf-8")
    except OSError:
        return None
    found = re.search(r"^version:\s*(\S+)", text, re.M)
    return found.group(1) if found else None


def set_stage(row, item: StageItem, by: str) -> bool:
    if (row.stage, row.stage_state, row.stage_note) == (item.stage, item.state, item.note):
        return False
    now = datetime.now(timezone.utc)
    if row.stage != item.stage:
        row.history = [*(row.history or []), {"at": now.isoformat(), "by": by, "note": item.note, "changes": [
            {"field": "stage", "from": STAGES.get(row.stage or "", row.stage), "to": STAGES[item.stage]}]}]
        row.stage_at = now
    row.stage, row.stage_state, row.stage_note = item.stage, item.state, item.note
    return True


def _hours(at: datetime | None, now: datetime) -> int:
    return int((now - at).total_seconds() // 3600) if at else 0


def _stuck(rows: list, type_: str, now: datetime) -> list[dict]:
    return [{"type": type_, "id": r.id, "title": r.title, "stage": r.stage, "state": r.stage_state,
             "note": r.stage_note, "hours": _hours(r.stage_at, now)}
            for r in rows if r.stage not in FINISHED and r.stage != "ready"]


def release_gate(tasks: list, high: list, facts: dict) -> dict:
    """PIPELINE stage 7: every card of this version passed and no high-severity problem."""
    by_stage = {k: [t for t in tasks if t.stage == k] for k in (*VERIFYING, "ready")}
    failed = [t for t in tasks if t.stage_state == "failed" and t.stage not in FINISHED]
    reasons = []
    waiting = [f"{STAGES[k]} {len(by_stage[k])}" for k in VERIFYING if by_stage[k]]
    if waiting:
        reasons.append("還在驗證：" + "、".join(waiting))
    if failed:
        reasons.append("驗證不通過：" + "、".join(f"#{t.id}" for t in failed[:8]))
    if high:
        reasons.append("高嚴重度問題未處理：" + "、".join(f"#{i.id}" for i in high[:8]))
    if facts.get("inbox_todo"):
        reasons.append(f"Mac 收件夾還有 {facts['inbox_todo']} 項待做（含流程開始前的舊卡）")
    if not by_stage["ready"]:
        reasons.append("還沒有通過 iPad 驗證的新卡")
    return {"version": app_version(), "can_release": not reasons, "ready": len(by_stage["ready"]),
            "reasons": reasons}


def is_decision(i) -> bool:
    return i.status == "needs_decision" or (i.kind == "decision" and i.status == "open")


def task_need(t) -> str | None:
    """Why a card can only go on with the owner: reply · account · manual · None."""
    if t.status == "waiting":
        return "reply"
    if t.status == "blocked" and ACCOUNT_RE.search(t.progress or ""):
        return "account"
    if t.stage == "ipad_verify" and t.stage_state == "note" and OWNER_CHECK_RE.search(t.stage_note or ""):
        return "manual"
    return None


def needs_owner(tasks: list, issues: list, release: dict, facts: dict, now: datetime) -> list[str]:
    """PIPELINE「Owner 只介入這些事」: one line per thing only the owner can do."""
    lines = []
    decisions = [i for i in issues if is_decision(i)]
    if decisions:
        lines.append(f"有 {len(decisions)} 個待決定：" + "、".join(f"#{i.id} {i.title[:24]}" for i in decisions[:5]))
    for t in tasks:
        need = task_need(t)
        if need == "reply":
            lines.append(f"卡 #{t.id} 等你回覆：{t.title[:40]}")
        elif need == "account":
            lines.append(f"卡 #{t.id} 需要帳號／付款／憑證：{(t.progress or '')[:60]}")
        elif need == "manual":
            lines.append(f"卡 #{t.id} 要你在 iPad 手動確認：{t.title[:40]}")
    if release["can_release"]:
        lines.append(f"版本 {release['version']} 可以發布：{release['ready']} 張卡都過了 iPad 驗證")
    pending = mac_silent(tasks, facts, now)
    if pending:
        lines.append(f"Mac 超過 {MAC_QUIET_HOURS // 24} 天沒有寫驗證結果，{pending} 張卡在等：請確認 Mac 有開著")
    return lines


def mac_silent(tasks: list, facts: dict, now: datetime) -> int:
    """Cards waiting on a Mac that has gone quiet (0 when it is not quiet)."""
    pending = sum(t.stage in ("mac_verify", "ipad_verify") for t in tasks)
    last = facts.get("mac_last_at")
    return pending if pending and last and (now.timestamp() - last) / 3600 > MAC_QUIET_HOURS else 0


def feedback_rows(s: Session, q: str | None) -> list[dict]:
    """Phone feedback → its cards and stage. Rows older than the pipeline show the card only."""
    cols = (m.IssueReport.id, m.IssueReport.title, m.IssueReport.status, m.IssueReport.stage,
            m.IssueReport.stage_state, m.IssueReport.created_at)
    stmt = select(*cols).where(or_(m.IssueReport.reporter.like("App 使用者%"),
                                   m.IssueReport.title.like("%[意見回饋]%")))
    if q and q.strip().lstrip("#").isdigit():
        stmt = stmt.where(m.IssueReport.id == int(q.strip().lstrip("#")))
    elif q:
        stmt = stmt.where(m.IssueReport.title.ilike(f"%{q.strip()}%"))
    rows = s.execute(stmt.order_by(m.IssueReport.id.desc()).limit(100)).all()
    want = {r.id for r in rows}
    cards: dict[int, list[int]] = {}
    for tid, ids in s.execute(select(m.AgentTask.id, m.AgentTask.issue_ids)).all():
        for i in ids or []:
            if i in want:
                cards.setdefault(i, []).append(tid)
    return [{"id": r.id, "title": r.title, "status": r.status, "stage": r.stage, "state": r.stage_state,
             "created_at": r.created_at, "cards": sorted(cards.get(r.id, []))} for r in rows]


def overview(s: Session, q: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    start = start_ids()
    tasks = list(s.execute(select(m.AgentTask).where(m.AgentTask.kind == "once", m.AgentTask.id >= start["task"],
                                                     m.AgentTask.stage.is_not(None))).scalars())
    flow_issues = list(s.execute(select(m.IssueReport).where(m.IssueReport.id >= start["issue"],
                                                             m.IssueReport.stage.is_not(None))).scalars())
    active = list(s.execute(select(m.IssueReport).where(m.IssueReport.status.in_(ACTIVE_ISSUE))).scalars())
    waiting_tasks = list(s.execute(select(m.AgentTask).where(
        m.AgentTask.status.in_(("waiting", "blocked")), m.AgentTask.stage.is_(None))).scalars())
    high = [i for i in active if i.area == "app" and i.severity == "high" and i.kind == "bug"]
    facts = _load(FACTS)
    release = release_gate(tasks, high, facts)
    stuck = sorted(_stuck(tasks, "task", now) + _stuck(flow_issues, "issue", now), key=lambda r: -r["hours"])
    return {"stages": STAGES,
            "tasks": {k: sum(t.stage == k for t in tasks) for k in STAGES},
            "issues": {k: sum(i.stage == k for i in flow_issues) for k in STAGES},
            "start": start, "stuck": stuck[:10], "release": release,
            "needs_you": needs_owner(tasks + waiting_tasks, active, release, facts, now),
            "feedback": feedback_rows(s, q), "digest": _load(DIGEST),
            "updated_at": facts.get("at")}


def register(app, auth):
    DB = Depends(db.get_session)

    @app.get("/flow/items", dependencies=[auth])
    def flow_items(s: Session = DB):
        """What flow_tick needs, without histories and screenshots."""
        start = start_ids()
        task_cols = (m.AgentTask.id, m.AgentTask.title, m.AgentTask.status, m.AgentTask.issue_ids, m.AgentTask.stage,
                     m.AgentTask.stage_state, m.AgentTask.stage_note, m.AgentTask.created_at)
        issue_cols = (m.IssueReport.id, m.IssueReport.title, m.IssueReport.status, m.IssueReport.area,
                      m.IssueReport.stage, m.IssueReport.stage_state, m.IssueReport.stage_note)
        return {"start": start,
                "tasks": [{**dict(r._mapping), "created_at": str(r._mapping["created_at"] or "")}
                          for r in s.execute(select(*task_cols).where(
                              m.AgentTask.kind == "once", m.AgentTask.id >= start["task"]))],
                "issues": [dict(r._mapping) for r in s.execute(select(*issue_cols).where(
                    m.IssueReport.id >= start["issue"]))]}

    @app.post("/flow/stages", dependencies=[auth])
    def flow_stages(body: StagesBody, s: Session = DB):
        changed = 0
        for item in body.items:
            if item.stage not in STAGES or item.type not in ("task", "issue"):
                raise HTTPException(422, f"不認得的階段：{item.type} {item.stage}")
            row = s.get(m.AgentTask if item.type == "task" else m.IssueReport, item.id)
            if row is not None:
                changed += set_stage(row, item, body.by)
        s.flush()
        return {"changed": changed}

    @app.get("/flow/overview", dependencies=[auth])
    def flow_overview(q: str | None = None, s: Session = DB):
        return overview(s, q)
