"""Anonymous app events and retention numbers (card #914).

The app sends a random install id plus event names; no account, no content, no IP is
stored. Retention is the classic definition: day N counts an install only if it opened
the app exactly N days after its install day."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import db
from . import models as m

EVENTS = ("install", "onboarded", "first_photo", "first_review", "open")
MAX_BATCH = 20
MAX_SKEW_DAYS = 2
RETENTION_DAYS = (1, 7, 30)
_ID = re.compile(r"^[A-Za-z0-9-]{16,40}$")


def _today() -> date:
    return datetime.now(timezone.utc).date()


def record(s: Session, body: dict, today: date | None = None) -> dict:
    """Store a batch of {event, day}. The device's day is kept only when within 2 days of the
    server's (a wrong clock must not make fake cohorts). Repeats are ignored."""
    today = today or _today()
    iid = body.get("install_id")
    if not isinstance(iid, str) or not _ID.match(iid):
        raise ValueError("install_id")
    raw = body.get("events")
    stored = 0
    for item in (raw if isinstance(raw, list) else [])[:MAX_BATCH]:
        if not isinstance(item, dict) or item.get("event") not in EVENTS:
            continue
        day = today
        try:
            d = date.fromisoformat(str(item.get("day")))
            if abs((d - today).days) <= MAX_SKEW_DAYS:
                day = d
        except ValueError:
            pass
        res = s.execute(pg_insert(m.AppEvent).values(install_id=iid, event=item["event"], day=day)
                        .on_conflict_do_nothing(constraint="uq_app_event"))
        stored += res.rowcount or 0
    return {"ok": True, "stored": stored}


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def retention(s: Session, weeks: int = 12, today: date | None = None) -> dict:
    """Admin only. Cohort = install day; weekly cohorts start on Monday."""
    today = today or _today()
    weeks = max(1, min(weeks, 52))
    since = today - timedelta(days=7 * weeks)
    install_day = {i: d for i, d in s.execute(select(m.AppEvent.install_id, m.AppEvent.day)
                                              .where(m.AppEvent.event == "install", m.AppEvent.day >= since))}
    by_event: dict[str, set[str]] = {e: set() for e in ("onboarded", "first_photo", "first_review")}
    opens: dict[str, set[date]] = {}
    if install_day:
        for iid, ev, day in s.execute(select(m.AppEvent.install_id, m.AppEvent.event, m.AppEvent.day)
                                      .where(m.AppEvent.install_id.in_(list(install_day)))):
            if ev in by_event:
                by_event[ev].add(iid)
            elif ev == "open":
                opens.setdefault(iid, set()).add(day)

    def block(ids: list[str]) -> dict:
        out = {"installs": len(ids),
               "onboarded": sum(i in by_event["onboarded"] for i in ids),
               "first_photo": sum(i in by_event["first_photo"] for i in ids),
               "first_review": sum(i in by_event["first_review"] for i in ids)}
        out["onboarded_rate"] = _rate(out["onboarded"], len(ids))
        out["first_review_rate"] = _rate(out["first_review"], len(ids))
        for n in RETENTION_DAYS:
            # Only installs old enough to have had day N yet are counted.
            ok = [i for i in ids if install_day[i] + timedelta(days=n) <= today]
            back = sum(install_day[i] + timedelta(days=n) in opens.get(i, ()) for i in ok)
            out[f"d{n}"] = {"eligible": len(ok), "returned": back, "rate": _rate(back, len(ok))}
        return out

    ids = list(install_day)
    cohorts = []
    for w in range(weeks):
        start = today - timedelta(days=today.weekday()) - timedelta(days=7 * w)
        end = start + timedelta(days=7)
        c = [i for i in ids if start <= install_day[i] < end]
        if c:
            cohorts.append({"week_start": start.isoformat(), **block(c)})
    return {"today": today.isoformat(), "weeks": weeks, "total": block(ids), "cohorts": cohorts,
            "definition": "第 N 天留存 = 安裝後剛好第 N 天有開啟 App 的比例（classic）；還沒滿 N 天的安裝不計入分母。"}


def register(app, auth):
    @app.get("/admin/retention", dependencies=[auth])
    def admin_retention(weeks: int = 12, s: Session = Depends(db.get_session)):
        return retention(s, weeks)
