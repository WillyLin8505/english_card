"""後台使用者頁 (card #911): app-reported numbers, admin-only views, gone with the account."""

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app import models as m

H = {"X-API-Key": "test-key"}


def _user(s, email, nick="N"):
    return accounts.register_email(s, email, "password1", nick, "zh-TW", "B1")[0]


def test_report_replaces_and_clamps(session):
    u = _user(session, "a@x.com")
    accounts.report_stats(session, u, {"albums": ["Food", " Food ", "Zoo", 5, ""], "reviews_total": 10, "reviews_7d": 99,
                                       "photos_taken": -3, "photos_opened": "x", "app_version": "1.0.0+1"})
    d = accounts.user_detail(session, u.id)
    assert d["albums"] == ["Food", "Zoo"] and d["reviews_7d"] == 10 and d["photos_taken"] == 0 and d["photos_opened"] == 0
    accounts.report_stats(session, u, {"albums": ["Zoo"], "reviews_total": 12, "reviews_7d": 2, "photos_opened": 4})
    d = accounts.user_detail(session, u.id)
    assert d["albums"] == ["Zoo"] and d["reviews_total"] == 12 and d["photos_opened"] == 4 and d["app_version"] is None
    assert session.query(m.UserStat).count() == 1


def test_overview_search_sort_active_and_no_personal_fields(session):
    a, b, c = _user(session, "amy@x.com", "Amy Secret"), _user(session, "bob@x.com"), _user(session, "cy@x.com")
    accounts.report_stats(session, a, {"albums": ["Food"], "reviews_total": 5, "reviews_7d": 5})
    accounts.report_stats(session, b, {"albums": ["Zoo"], "reviews_total": 50, "reviews_7d": 0})
    session.query(m.UserStat).filter(m.UserStat.user_id == b.id).update({m.UserStat.last_seen: m.UserStat.last_seen - __import__("datetime").timedelta(days=30)})
    o = accounts.users_overview(session)
    assert o["total_users"] == 3 and o["active_7d"] == 1
    assert [r["email"] for r in accounts.users_overview(session, sort="reviews_total")["users"]][:2] == ["bob@x.com", "amy@x.com"]
    assert [r["email"] for r in accounts.users_overview(session, q="zoo")["users"]] == ["bob@x.com"]
    assert [r["email"] for r in accounts.users_overview(session, q="CY@")["users"]] == ["cy@x.com"]
    assert "Amy Secret" not in str(o) and "nickname" not in str(o)
    assert accounts.users_overview(session, sort="bogus")["total_users"] == 3


def test_decks_and_languages_are_stored_and_filterable(session):
    """Card #1002: installed databases and the language pair; old apps send neither."""
    a, b, c = _user(session, "ann@x.com"), _user(session, "ben@x.com"), _user(session, "cat@x.com")
    accounts.report_stats(session, a, {"decks": [{"slug": "food-en", "kind": "words", "title": "Food"},
                                                 {"slug": "p1", "kind": "photos", "title": "Trip"},
                                                 {"slug": "food-en", "kind": "words", "title": "dup"}],
                                       "languages": {"learning": "fr", "native": "en", "words": 12}})
    accounts.report_stats(session, b, {"decks": [{"slug": "food-en", "kind": "words", "title": "Food"}],
                                       "languages": {"learning": "en", "native": "zh-TW", "words": 3}})
    accounts.report_stats(session, c, {"albums": ["Old"]})  # old app: no decks, no languages
    d = accounts.user_detail(session, a.id)
    assert [x["slug"] for x in d["decks"]] == ["food-en", "p1"] and d["deck_count"] == 2
    assert d["languages"] == {"learning": "fr", "native": "en", "words": 12}
    assert accounts.user_detail(session, c.id)["decks"] == [] and accounts.user_detail(session, c.id)["languages"] == {}
    o = accounts.users_overview(session, deck="food-en")
    assert o["matched"] == 2 and {r["email"] for r in o["users"]} == {"ann@x.com", "ben@x.com"}
    assert accounts.users_overview(session, q="trip")["matched"] == 1
    assert accounts.users_overview(session, deck="p1")["matched"] == 1
    assert accounts.users_overview(session, deck="nope")["matched"] == 0
    assert o["deck_usage"][0] == {"slug": "food-en", "kind": "words", "title": "Food", "users": 2}
    assert {u["slug"]: u["users"] for u in o["deck_usage"]} == {"food-en": 2, "p1": 1}
    both = accounts.users_overview(session, q="trip", deck="food-en")
    assert [r["email"] for r in both["users"]] == ["ann@x.com"]  # q and deck filters combine


def test_delete_account_removes_stats(session):
    u = _user(session, "d@x.com")
    accounts.report_stats(session, u, {"reviews_total": 1})
    accounts.delete_account(session, u)
    assert session.query(m.UserStat).count() == 0


def test_admin_endpoints_need_the_key(session, monkeypatch):
    from app import config
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    u = _user(session, "e@x.com")
    accounts.report_stats(session, u, {"albums": ["Food"], "reviews_total": 3})
    session.commit()
    with TestClient(app) as c:
        for path in ("/admin/users", f"/admin/users/{u.id}"):
            assert c.get(path).status_code == 401
            assert c.get(path, headers={"X-API-Key": "wrong"}).status_code == 401
        assert c.get("/admin/users", headers=H).json()["total_users"] == 1
        assert c.get(f"/admin/users/{u.id}", headers=H).json()["albums"] == ["Food"]
        assert c.get("/admin/users/9999", headers=H).status_code == 404


def test_public_server_does_not_expose_admin_users():
    import re, pathlib
    src = pathlib.Path(__file__).resolve().parents[2].joinpath("serve_app.py").read_text(encoding="utf-8")
    assert not re.search(r"admin/users", src)


def test_delete_stats_forgets_only_that_users_row(session):
    """Card #1009: switching 'send my usage numbers' off removes the row; repeat is harmless."""
    u = _user(session, "e@x.com")
    other = _user(session, "f@x.com")
    accounts.report_stats(session, u, {"reviews_total": 1})
    accounts.report_stats(session, other, {"reviews_total": 2})
    assert accounts.delete_stats(session, u)["deleted"] == 1
    assert accounts.delete_stats(session, u)["deleted"] == 0
    assert session.query(m.UserStat).count() == 1
