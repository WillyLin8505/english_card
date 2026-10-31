"""Google 登入 (card #910): claim checks, account linking by email, no duplicate accounts."""

import pytest

from app import accounts

IDS = ["ios-client.apps.googleusercontent.com"]


def _claims(**kw):
    c = {"iss": "https://accounts.google.com", "aud": IDS[0], "exp": 2_000_000_000, "sub": "g1",
         "email": "Gina@Gmail.com", "email_verified": True, "name": "Gina"}
    c.update(kw)
    return c


@pytest.mark.parametrize("bad", [{"iss": "https://evil.com"}, {"aud": "other"}, {"exp": 5},
                                 {"sub": ""}, {"email_verified": False}])
def test_claim_checks_reject(bad):
    with pytest.raises(ValueError):
        accounts.check_google_claims(_claims(**bad), IDS, now=1_000)


def test_claim_checks_accept_and_empty_client_ids():
    assert accounts.check_google_claims(_claims(), IDS, now=1_000)["sub"] == "g1"
    with pytest.raises(ValueError):
        accounts.check_google_claims(_claims(), [], now=1_000)


def test_login_google_creates_reuses_and_links(session, monkeypatch):
    monkeypatch.setattr(accounts, "google_verifier", lambda t: _claims())
    u1, tok = accounts.login_google(session, "t")
    assert u1.provider == "google" and u1.email == "gina@gmail.com" and u1.nickname == "Gina"
    assert accounts.user_from_token(session, tok).id == u1.id
    u2, _ = accounts.login_google(session, "t")
    assert u2.id == u1.id
    with pytest.raises(accounts.AccountError) as e:   # same email cannot open a second account
        accounts.register_email(session, "gina@gmail.com", "password1", "G2")
    assert e.value.status == 409


def test_google_links_existing_email_account(session, monkeypatch):
    mine, _ = accounts.register_email(session, "gina@gmail.com", "password1", "Gina")
    monkeypatch.setattr(accounts, "google_verifier", lambda t: _claims(sub="g2"))
    u, _ = accounts.login_google(session, "t")
    assert u.id == mine.id


def test_google_bad_token_and_unconfigured(session, monkeypatch):
    def boom(t):
        raise ValueError("audience")
    monkeypatch.setattr(accounts, "google_verifier", boom)
    with pytest.raises(accounts.AccountError) as e:
        accounts.login_google(session, "t")
    assert e.value.status == 401
    monkeypatch.setattr(accounts, "google_verifier", None)
    monkeypatch.delenv("LEXICON_GOOGLE_CLIENT_IDS", raising=False)
    with pytest.raises(accounts.AccountError) as e:
        accounts.login_google(session, "t")
    assert e.value.status == 501
