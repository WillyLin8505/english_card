"""問題回報 (Issue Reports): problems found while using or testing the app,
admin and card studio, plus requirements that aren't built yet and questions
waiting for the owner's decision. Registered on the API like images.py.

Every change of status, decision or resolution is appended to `history`, so
the page shows how an issue moved from 待處理 to 已修正.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field as PField
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import db
from . import models as m

KINDS = {"bug": "問題", "todo": "未完成需求", "decision": "待決定"}
STATUSES = {"open": "待處理", "in_progress": "處理中", "needs_decision": "等你決定",
            "fixed": "已修正", "wont_fix": "不處理"}
SEVERITIES = {"high": "高", "medium": "中", "low": "低"}
AREAS = {"app": "App", "admin": "語言資料後台", "card_studio": "字卡工作室",
         "data": "詞庫資料", "tagger": "照片辨識", "other": "其他"}
CLOSED = ("fixed", "wont_fix")
TRACKED = ("status", "decision", "resolution", "severity", "kind")


class IssueBody(BaseModel):
    kind: str | None = None
    status: str | None = None
    severity: str | None = None
    area: str | None = None
    title: str | None = PField(default=None, max_length=300)
    detail: str | None = None
    steps: str | None = None
    expected: str | None = None
    actual: str | None = None
    resolution: str | None = None
    options: list[str] | None = None
    decision: str | None = None
    target_language: str | None = None
    native_language: str | None = None
    lemma: str | None = None
    code_ref: str | None = None
    spec_ref: str | None = None
    reporter: str | None = None
    note: str | None = None          # a line for the history, not stored as a field


class DecideBody(BaseModel):
    decision: str = PField(min_length=1)
    note: str | None = None


def _check(body: IssueBody):
    for value, allowed, what in ((body.kind, KINDS, "類型"), (body.status, STATUSES, "狀態"),
                                 (body.severity, SEVERITIES, "嚴重度"), (body.area, AREAS, "範圍")):
        if value is not None and value not in allowed:
            raise HTTPException(422, f"不認得的{what}：{value}")


def issue_dict(r: m.IssueReport) -> dict:
    return {c: getattr(r, c) for c in (
        "id", "kind", "status", "severity", "area", "title", "detail", "steps", "expected",
        "actual", "resolution", "options", "decision", "target_language", "native_language",
        "lemma", "code_ref", "spec_ref", "reporter", "history", "created_at", "updated_at",
        "resolved_at")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply(r: m.IssueReport, data: dict, note: str | None, by: str):
    changes = []
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        if getattr(r, key) == value:
            continue
        if key in TRACKED:
            changes.append({"field": key, "from": getattr(r, key), "to": value})
        setattr(r, key, value)
    if "status" in data:
        r.resolved_at = datetime.now(timezone.utc) if r.status in CLOSED else None
    if changes or note:
        r.history = [*(r.history or []), {"at": _now(), "by": by, "changes": changes,
                                          "note": (note or "").strip() or None}]


def register(app, auth):
    DB = Depends(db.get_session)

    @app.get("/issues/meta", dependencies=[auth])
    def issues_meta():
        return {"kinds": KINDS, "statuses": STATUSES, "severities": SEVERITIES, "areas": AREAS}

    @app.get("/issues", dependencies=[auth])
    def list_issues(kind: str | None = None, status: str | None = None, area: str | None = None,
                    q: str | None = None, s: Session = DB):
        stmt = select(m.IssueReport)
        if kind:
            stmt = stmt.where(m.IssueReport.kind == kind)
        if status == "active":
            stmt = stmt.where(m.IssueReport.status.not_in(CLOSED))
        elif status == "closed":
            stmt = stmt.where(m.IssueReport.status.in_(CLOSED))
        elif status:
            stmt = stmt.where(m.IssueReport.status == status)
        if area:
            stmt = stmt.where(m.IssueReport.area == area)
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(m.IssueReport.title.ilike(like), m.IssueReport.detail.ilike(like),
                                  m.IssueReport.lemma.ilike(like), m.IssueReport.actual.ilike(like)))
        # Decisions first, then open work by severity, closed ones last.
        order = {"needs_decision": 0, "in_progress": 1, "open": 2, "fixed": 3, "wont_fix": 4}
        sev = {"high": 0, "medium": 1, "low": 2}
        rows = sorted(s.execute(stmt).scalars(),
                      key=lambda r: (order.get(r.status, 9), sev.get(r.severity, 9),
                                     -(r.updated_at or r.created_at).timestamp()))
        counts = {f"{k}:{st}": n for k, st, n in s.execute(
            select(m.IssueReport.kind, m.IssueReport.status, func.count()).group_by(
                m.IssueReport.kind, m.IssueReport.status)).all()}
        return {"items": [issue_dict(r) for r in rows], "counts": counts}

    @app.get("/issues/{issue_id}", dependencies=[auth])
    def get_issue(issue_id: int, s: Session = DB):
        r = s.get(m.IssueReport, issue_id)
        if not r:
            raise HTTPException(404, "找不到這筆回報")
        return issue_dict(r)

    @app.post("/issues", dependencies=[auth], status_code=201)
    def create_issue(body: IssueBody, s: Session = DB):
        _check(body)
        if not (body.title or "").strip():
            raise HTTPException(422, "請填標題")
        data = body.model_dump(exclude={"note"}, exclude_none=True)
        data.setdefault("kind", "bug")
        data.setdefault("status", "needs_decision" if data["kind"] == "decision" else "open")
        r = m.IssueReport(title=data.pop("title").strip(), history=[])
        s.add(r)
        _apply(r, data, body.note or "建立", body.reporter or "manual")
        s.flush()
        return issue_dict(r)

    @app.put("/issues/{issue_id}", dependencies=[auth])
    def update_issue(issue_id: int, body: IssueBody, s: Session = DB):
        _check(body)
        r = s.get(m.IssueReport, issue_id)
        if not r:
            raise HTTPException(404, "找不到這筆回報")
        data = body.model_dump(exclude={"note", "reporter"}, exclude_unset=True)
        if "title" in data and not (data["title"] or "").strip():
            raise HTTPException(422, "標題不能是空的")
        _apply(r, data, body.note, body.reporter or "manual")
        s.flush()
        return issue_dict(r)

    @app.post("/issues/{issue_id}/decide", dependencies=[auth])
    def decide_issue(issue_id: int, body: DecideBody, s: Session = DB):
        """The owner's answer to a 待決定 question: the work goes back to 待處理."""
        r = s.get(m.IssueReport, issue_id)
        if not r:
            raise HTTPException(404, "找不到這筆回報")
        _apply(r, {"decision": body.decision, "status": "open"}, body.note, "owner")
        s.flush()
        return issue_dict(r)

    @app.delete("/issues/{issue_id}", dependencies=[auth], status_code=204)
    def delete_issue(issue_id: int, s: Session = DB):
        r = s.get(m.IssueReport, issue_id)
        if not r:
            raise HTTPException(404, "找不到這筆回報")
        s.delete(r)
