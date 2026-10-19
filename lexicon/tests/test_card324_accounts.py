"""帳號＋分享圖片集／單字集 (card #324): sign-up, sharing, safety gate, reports, blocks, stats."""

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app import models as m

H = {"X-API-Key": "test-key"}
JPEG = b"\xff\xd8\xff\xe0" + b"x" * 64
LABEL = [{"word": "Dog", "pos": "noun", "cefr": "A1", "point": [0.5, 0.5], "score": 0.9}]


@pytest.fixture
def media(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    return tmp_path


def _user(s, email="a@x.com", nick="Amy"):
    return accounts.register_email(s, email, "password1", nick, "zh-TW", "B1")


def test_register_login_token_and_wrong_password(session):
    user, token = _user(session)
    assert accounts.user_from_token(session, token).id == user.id
    assert user.password_hash.startswith("pbkdf2$") and "password1" not in user.password_hash
    with pytest.raises(accounts.AccountError) as e:
        accounts.login_email(session, "a@x.com", "nope")
    assert e.value.status == 401
    _, t2 = accounts.login_email(session, "A@x.com", "password1")
    assert t2 != token
    with pytest.raises(accounts.AccountError) as e:
        _user(session)
    assert e.value.status == 409
    accounts.logout(session, token)
    with pytest.raises(accounts.AccountError):
        accounts.user_from_token(session, token)


def test_validation(session):
    for args in (("bad", "password1", "N"), ("a@x.com", "short", "N"), ("a@x.com", "password1", "")):
        with pytest.raises(accounts.AccountError) as e:
            accounts.register_email(session, *args)
        assert e.value.status == 422


def test_apple_login_uses_verifier(session, monkeypatch):
    with pytest.raises(accounts.AccountError) as e:
        accounts.login_apple(session, "tok", "Bo")
    assert e.value.status == 501
    monkeypatch.setattr(accounts, "apple_verifier", lambda t: {"sub": "apple-1", "email": "p@relay.com"})
    u1, _ = accounts.login_apple(session, "tok", "Bo", "ja", "A2")
    u2, _ = accounts.login_apple(session, "tok")
    assert u1.id == u2.id and u1.provider == "apple"


def test_share_words_requires_privacy_ack_and_goes_live(session):
    user, _ = _user(session)
    kw = dict(kind="words", title="My words", cefr="B1", words=[{"word": "Apple", "pos": "noun"}])
    with pytest.raises(accounts.AccountError):
        accounts.share_deck(session, user, **kw)
    out = accounts.share_deck(session, user, acknowledged_privacy=True, **kw)
    assert out["share_status"] == "shared" and out["author"] == "Amy" and out["count"] == 1
    assert [d["slug"] for d in accounts.public_list(session)["decks"]] == [out["slug"]]
    accounts.count_download(session, out["slug"])
    accounts.count_download(session, out["slug"])
    assert accounts.my_shares(session, user)["decks"][0]["downloads"] == 2
    accounts.withdraw(session, user, out["slug"])
    assert accounts.public_list(session)["decks"] == []


def test_photo_deck_waits_for_safety_check(session, media):
    user, _ = _user(session)
    aid = accounts.upload_photo(session, user, JPEG)
    assert accounts.upload_photo(session, user, JPEG) == aid          # same bytes → same asset
    assert (media / "user").exists()
    out = accounts.share_deck(session, user, kind="photos", title="Pets", acknowledged_privacy=True,
                              photos=[{"asset_id": aid, "labels": LABEL}])
    assert out["share_status"] == "pending"
    assert accounts.public_list(session)["decks"] == []
    session.get(m.ImageAsset, aid).safety_status = "safe"
    assert len(accounts.public_list(session)["decks"]) == 1
    session.get(m.ImageAsset, aid).safety_status = "blocked"
    session.query(m.Deck).update({m.Deck.share_status: "shared"})
    accounts.my_shares(session, user)
    assert accounts.public_list(session)["decks"] == []
    assert session.query(m.Deck).one().share_status == "removed"


def test_cannot_share_someone_elses_photo_or_bad_files(session, media):
    a, _ = _user(session)
    b, _ = _user(session, "b@x.com", "Ben")
    aid = accounts.upload_photo(session, a, JPEG)
    with pytest.raises(accounts.AccountError) as e:
        accounts.upload_photo(session, b, JPEG)
    assert e.value.status == 409
    with pytest.raises(accounts.AccountError):
        accounts.share_deck(session, b, kind="photos", title="x", acknowledged_privacy=True,
                            photos=[{"asset_id": aid, "labels": LABEL}])
    with pytest.raises(accounts.AccountError) as e:
        accounts.upload_photo(session, a, b"GIF89a....")
    assert e.value.status == 415


def test_report_block_takedown_and_stats(session):
    a, _ = _user(session)
    b, _ = _user(session, "b@x.com", "Ben")
    d = accounts.share_deck(session, a, kind="words", title="Deck", words=[{"word": "cat"}],
                            acknowledged_privacy=True)
    accounts.report_deck(session, b, d["slug"], "不當內容")
    st = accounts.stats(session)
    assert (st["users"], st["sharers"], st["shared_decks"]) == (2, 1, 1)
    assert st["reported"][0]["open_reports"] == 1 and st["decks"][0]["words"] == 1
    accounts.block_author(session, b, d["slug"])
    assert accounts.public_list(session, b)["decks"] == []
    assert len(accounts.public_list(session, a)["decks"]) == 1
    accounts.takedown(session, d["slug"])
    assert accounts.public_list(session)["decks"] == []
    assert accounts.stats(session)["reported"] == []
    accounts.takedown(session, d["slug"], restore=True)
    assert len(accounts.public_list(session)["decks"]) == 1
    with pytest.raises(accounts.AccountError):
        accounts.block_author(session, a, d["slug"])                  # not yourself


def test_delete_account_removes_shares(session):
    a, tok = _user(session)
    accounts.share_deck(session, a, kind="words", title="D", words=[{"word": "cat"}], acknowledged_privacy=True)
    accounts.delete_account(session, a)
    assert session.query(m.Deck).count() == 0 and session.query(m.User).count() == 0


def test_admin_routes_and_ban(session, monkeypatch):
    from app import config
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    a, tok = _user(session)
    d = accounts.share_deck(session, a, kind="words", title="D", words=[{"word": "cat"}], acknowledged_privacy=True)
    session.commit()
    with TestClient(app) as c:
        assert c.get("/share-stats").status_code == 401
        assert c.get("/share-stats", headers=H).json()["shared_decks"] == 1
        assert c.put(f"/users/{a.id}/ban", headers=H, json={"blocked": True}).json()["blocked"] is True
        assert c.get("/share-stats", headers=H).json()["shared_decks"] == 0
    session.expire_all()
    with pytest.raises(accounts.AccountError) as e:
        accounts.user_from_token(session, tok)
    assert e.value.status == 401
    with pytest.raises(accounts.AccountError) as e:
        accounts.login_email(session, "a@x.com", "password1")
    assert e.value.status == 403
