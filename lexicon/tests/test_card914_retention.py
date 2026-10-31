"""Anonymous events and classic day-1/7/30 retention (card #914), checked on made-up installs."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import app_events, models as m

TODAY = date(2026, 10, 31)   # a Saturday
H = {"X-API-Key": "test-key"}


def _id(n):
    return f"install-{n:08d}-abcdef"


def _ev(s, n, event, day):
    app_events.record(s, {"install_id": _id(n), "events": [{"event": event, "day": day.isoformat()}]}, TODAY)


def test_classic_retention_hand_checked(session):
    d0 = TODAY - timedelta(days=40)
    # install 1: opens exactly on day 1, 7 and 30 -> counted in all three
    # install 2: opens on day 2..6 and 8 only -> never "exactly" day 1/7
    # install 3: installed 3 days ago -> too young for day 7/30, opens on day 1
    # install 4: installed 8 days ago, opens day 7 only
    for n, inst in ((1, d0), (2, d0), (3, TODAY - timedelta(days=3)), (4, TODAY - timedelta(days=8))):
        _ev(session, n, "install", inst)
    for k in (1, 7, 30):
        _ev(session, 1, "open", d0 + timedelta(days=k))
    for k in (2, 3, 4, 5, 6, 8):
        _ev(session, 2, "open", d0 + timedelta(days=k))
    _ev(session, 3, "open", TODAY - timedelta(days=2))
    _ev(session, 4, "open", TODAY - timedelta(days=1))
    _ev(session, 1, "onboarded", d0); _ev(session, 2, "onboarded", d0); _ev(session, 3, "onboarded", TODAY)
    _ev(session, 1, "first_review", d0)
    r = app_events.retention(session, 12, TODAY)["total"]
    assert r["installs"] == 4 and r["onboarded"] == 3 and r["onboarded_rate"] == 0.75
    assert r["first_review"] == 1 and r["first_review_rate"] == 0.25
    # day 1: eligible 1,2,3,4 (all >= 1 day old); returned 1 and 3 and ... 4 opened day 7 (yesterday), not day 1
    assert r["d1"] == {"eligible": 4, "returned": 2, "rate": 0.5}
    # day 7: eligible 1,2,4; returned 1 and 4
    assert r["d7"] == {"eligible": 3, "returned": 2, "rate": 0.6667}
    # day 30: eligible 1,2 only; returned 1
    assert r["d30"] == {"eligible": 2, "returned": 1, "rate": 0.5}


def test_weekly_cohorts_split_on_monday(session):
    sat, sun, mon = date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)   # Sat, Sun, Mon
    for n, d in ((1, sat), (2, sun), (3, mon)):
        _ev(session, n, "install", d)
    cohorts = app_events.retention(session, 4, TODAY)["cohorts"]
    assert {c["week_start"]: c["installs"] for c in cohorts} == {"2026-10-19": 2, "2026-10-26": 1}


def test_record_dedups_validates_and_clamps_clock(session):
    ok = {"install_id": _id(9), "events": [{"event": "install", "day": "2026-10-31"}] * 3
          + [{"event": "bogus"}, {"event": "open", "day": "2000-01-01"}, "x"]}
    assert app_events.record(session, ok, TODAY)["stored"] == 2
    days = {(e.event, e.day) for e in session.query(m.AppEvent)}
    assert days == {("install", TODAY), ("open", TODAY)}   # wrong clock -> server day
    with pytest.raises(ValueError):
        app_events.record(session, {"install_id": "short", "events": []}, TODAY)
    with pytest.raises(ValueError):
        app_events.record(session, {"install_id": "a b" * 10, "events": []}, TODAY)


def test_admin_retention_needs_key(session, monkeypatch):
    from app import config
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    session.commit()
    with TestClient(app) as c:
        assert c.get("/admin/retention").status_code == 401
        r = c.get("/admin/retention", headers=H)
        assert r.status_code == 200 and r.json()["total"]["installs"] == 0 and "classic" in r.json()["definition"]


def test_public_server_has_events_but_not_retention():
    import pathlib, re
    src = pathlib.Path(__file__).resolve().parents[2].joinpath("serve_app.py").read_text(encoding="utf-8")
    assert "/api/events" in src and not re.search(r"admin/retention", src)
