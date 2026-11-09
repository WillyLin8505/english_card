"""Card #1007: Sign in with Apple defaults, token exchange and revoke on account deletion."""
import pytest

from app import accounts


@pytest.fixture
def media(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    return tmp_path


def _apple_user(session, monkeypatch):
    monkeypatch.setattr(accounts, "apple_verifier", lambda t: {"sub": "apple-7", "email": "h@privaterelay.appleid.com"})
    return accounts.login_apple(session, "tok", "Bo")[0]


def test_default_audience_is_bundle_id_and_fake_token_is_401(session, monkeypatch):
    monkeypatch.delenv("LEXICON_APPLE_CLIENT_IDS", raising=False)
    import jwt
    monkeypatch.setattr(jwt.PyJWKClient, "get_signing_key_from_jwt", lambda self, t: (_ for _ in ()).throw(ValueError("bad")))
    with pytest.raises(accounts.AccountError) as e:
        accounts.login_apple(session, "fake", "Bo")
    assert e.value.status == 401
    claims = {"iss": "https://appleid.apple.com", "aud": accounts.APPLE_BUNDLE_ID, "exp": 9e9, "sub": "x"}
    assert accounts.check_oidc_claims(claims, [accounts.APPLE_BUNDLE_ID], ("https://appleid.apple.com",))["sub"] == "x"


def test_no_key_delete_still_works(session, media, monkeypatch):
    for k in ("LEXICON_APPLE_KEY_ID", "LEXICON_APPLE_TEAM_ID", "LEXICON_APPLE_KEY_PATH"):
        monkeypatch.delenv(k, raising=False)
    u = _apple_user(session, monkeypatch)
    assert accounts.store_apple_authorization(u, "code") is False
    accounts.delete_account(session, u)


def test_exchange_then_revoke_on_delete(session, media, monkeypatch, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    keyfile = tmp_path / "fake.p8"
    keyfile.write_bytes(pem)
    monkeypatch.setenv("LEXICON_APPLE_KEY_ID", "KID")
    monkeypatch.setenv("LEXICON_APPLE_TEAM_ID", "TEAM")
    monkeypatch.setenv("LEXICON_APPLE_KEY_PATH", str(keyfile))
    calls = []

    def fake(url, form):
        calls.append((url, form))
        return 200, ({"refresh_token": "r-1"} if url == accounts.APPLE_TOKEN_URL else {})
    monkeypatch.setattr(accounts, "apple_http", fake)
    u = _apple_user(session, monkeypatch)
    assert accounts.store_apple_authorization(u, "code-1") is True
    accounts.delete_account(session, u)
    assert [c[0] for c in calls] == [accounts.APPLE_TOKEN_URL, accounts.APPLE_REVOKE_URL]
    assert calls[1][1]["token"] == "r-1" and calls[1][1]["client_id"] == accounts.APPLE_BUNDLE_ID
    assert not (media / "apple_tokens").exists() or not list((media / "apple_tokens").iterdir())


def test_revoke_failure_does_not_block_delete(session, media, monkeypatch, tmp_path):
    u = _apple_user(session, monkeypatch)
    p = accounts._apple_token_path(u)
    p.parent.mkdir(parents=True)
    p.write_text("r", encoding="utf-8")
    monkeypatch.setenv("LEXICON_APPLE_KEY_ID", "K")
    monkeypatch.setenv("LEXICON_APPLE_TEAM_ID", "T")
    monkeypatch.setenv("LEXICON_APPLE_KEY_PATH", str(tmp_path / "missing.p8"))
    accounts.delete_account(session, u)
    assert not p.exists()
