"""Accounts and shared decks (card #324, 問題回報 #322).

Everything the app needs is a plain function over a Session (like decks.py), so the
stdlib server in serve_app.py can call it today and a Cloudflare Worker can port it
later: users/user_tokens/user_blocks/deck_reports/decks/deck_items map 1:1 to D1
tables, photo bytes (config.MEDIA/user/<sha>.jpg) to an R2 bucket, tokens stay
SHA-256 hashed. The admin routes (`register`) feed the 分享統計 page."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, db, decks
from . import models as m

NICK_MAX = 40
PHOTO_MAX_BYTES = 5 * 1024 * 1024
BACKUP_MAX_BYTES = 200 * 1024 * 1024
BACKUP_MAGIC = b"ENGLISH-CARD-BACKUP "
PBKDF2_ROUNDS = 240_000
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
JPEG, PNG = b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"
# Pluggable so tests and a future Worker can swap it: (identity_token) -> {"sub", "email"} or raises ValueError.
# The real one verifies Apple's JWT signature against https://appleid.apple.com/auth/keys (needs PyJWT).
apple_verifier = None
# Same shape for Google (card #910): (id_token) -> claims or raises ValueError. None = built from
# LEXICON_GOOGLE_CLIENT_IDS (comma list of OAuth client IDs: iOS / Android / web) on first use.
google_verifier = None
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


class AccountError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _hash_pw(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dig = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${dig.hex()}"


def _check_pw(password: str, stored: str | None) -> bool:
    try:
        _, rounds, salt, dig = (stored or "").split("$")
        cand = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(cand.hex(), dig)
    except ValueError:
        return False


def _issue_token(s: Session, user: m.User) -> str:
    token = secrets.token_urlsafe(32)
    s.add(m.UserToken(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest()))
    s.flush()
    return token


def profile(user: m.User) -> dict:
    return {"id": user.id, "nickname": user.nickname, "email": user.email, "native_lang": user.native_lang,
            "level": user.level, "provider": user.provider}


def _clean_profile(nickname, native_lang, level) -> tuple[str, str | None, str | None]:
    nickname = (nickname or "").strip()
    if not nickname or len(nickname) > NICK_MAX:
        raise AccountError(422, "暱稱要 1–40 個字")
    if level and level not in decks.CEFR:
        raise AccountError(422, "程度只能是 A1…C2")
    return nickname, (native_lang or None), (level or None)


def register_email(s: Session, email: str, password: str, nickname: str,
                   native_lang: str | None = None, level: str | None = None) -> tuple[m.User, str]:
    email = (email or "").strip().lower()
    if not EMAIL.match(email):
        raise AccountError(422, "Email 格式不對")
    if len(password or "") < 8:
        raise AccountError(422, "密碼至少 8 個字元")
    nickname, native_lang, level = _clean_profile(nickname, native_lang, level)
    if s.scalar(select(m.User.id).where((m.User.provider_sub == email) | (m.User.email == email))):
        raise AccountError(409, "這個 Email 已經註冊了")
    user = m.User(provider="email", provider_sub=email, email=email, password_hash=_hash_pw(password),
                  nickname=nickname, native_lang=native_lang, level=level)
    s.add(user)
    s.flush()
    return user, _issue_token(s, user)


def login_email(s: Session, email: str, password: str) -> tuple[m.User, str]:
    sub = (email or "").strip().lower()
    user = s.scalar(select(m.User).where(m.User.provider_sub == sub, m.User.provider == "email"))
    if user is None or not _check_pw(password or "", user.password_hash):
        raise AccountError(401, "Email 或密碼不對")
    if user.blocked:
        raise AccountError(403, "這個帳號已被停用")
    return user, _issue_token(s, user)


def login_apple(s: Session, identity_token: str, nickname: str | None = None,
                native_lang: str | None = None, level: str | None = None) -> tuple[m.User, str]:
    try:
        claims = (apple_verifier or _default_apple_verifier)(identity_token)
    except ValueError as e:
        raise AccountError(401, f"Apple 登入驗證失敗：{e}")
    user = s.scalar(select(m.User).where(m.User.provider_sub == claims["sub"]))
    if user is None:
        nick, native_lang, level = _clean_profile(nickname, native_lang, level)
        user = m.User(provider="apple", provider_sub=claims["sub"], email=claims.get("email"),
                      nickname=nick, native_lang=native_lang, level=level)
        s.add(user)
        s.flush()
    if user.blocked:
        raise AccountError(403, "這個帳號已被停用")
    return user, _issue_token(s, user)


def check_google_claims(claims: dict, client_ids: list[str], now: float | None = None) -> dict:
    return check_oidc_claims(claims, client_ids, GOOGLE_ISSUERS, now)


def check_oidc_claims(claims: dict, client_ids: list[str], issuers: tuple, now: float | None = None) -> dict:
    """The checks after the signature: issuer, audience (one of our client IDs), expiry, verified email."""
    import time
    if claims.get("iss") not in issuers:
        raise ValueError("issuer")
    if not client_ids or claims.get("aud") not in client_ids:
        raise ValueError("audience")
    if float(claims.get("exp", 0)) <= (time.time() if now is None else now):
        raise ValueError("expired")
    if not claims.get("sub"):
        raise ValueError("no sub")
    if claims.get("email") and claims.get("email_verified", True) not in (True, "true"):
        raise ValueError("email not verified")
    return claims


def _oidc_verify(id_token: str, env: str, jwks_url: str, issuers: tuple, label: str) -> dict:
    """Signature (RS256 via the provider's published keys) + iss / aud / exp. Client IDs come from the environment."""
    import os
    ids = [x.strip() for x in os.environ.get(env, "").split(",") if x.strip()]
    if not ids:
        raise AccountError(501, f"伺服器還沒設定 {label} 登入（{env}）")
    try:
        import jwt  # PyJWT[crypto]
    except ImportError:
        raise AccountError(501, f"伺服器缺少 PyJWT[crypto]，無法驗證 {label} 登入")
    try:
        key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(id_token, key, algorithms=["RS256"], options={"verify_aud": False, "verify_exp": False})
    except Exception as e:
        raise ValueError(f"signature: {e}")
    return check_oidc_claims(claims, ids, issuers)


def _default_google_verifier(id_token: str) -> dict:
    return _oidc_verify(id_token, "LEXICON_GOOGLE_CLIENT_IDS", GOOGLE_JWKS_URL, GOOGLE_ISSUERS, "Google")


def _default_apple_verifier(id_token: str) -> dict:
    return _oidc_verify(id_token, "LEXICON_APPLE_CLIENT_IDS", "https://appleid.apple.com/auth/keys",
                        ("https://appleid.apple.com",), "Sign in with Apple")


def login_google(s: Session, id_token: str, nickname: str | None = None,
                 native_lang: str | None = None, level: str | None = None) -> tuple[m.User, str]:
    """Verify a Google ID token; reuse the account for the same Google sub, or the existing email
    account with the same (verified) address, else create one."""
    verify = google_verifier or _default_google_verifier
    try:
        claims = verify(id_token)
    except ValueError as e:
        raise AccountError(401, f"Google 登入驗證失敗：{e}")
    sub, email = f"google:{claims['sub']}", (claims.get("email") or "").strip().lower() or None
    user = s.scalar(select(m.User).where(m.User.provider_sub == sub))
    if user is None and email:
        user = s.scalar(select(m.User).where(m.User.email == email).order_by(m.User.id))
    if user is None:
        nick = (nickname or claims.get("name") or (email or "").split("@")[0] or "learner").strip()[:NICK_MAX]
        nick, native_lang, level = _clean_profile(nick, native_lang, level)
        user = m.User(provider="google", provider_sub=sub, email=email, nickname=nick,
                      native_lang=native_lang, level=level)
        s.add(user)
        s.flush()
    if user.blocked:
        raise AccountError(403, "這個帳號已被停用")
    return user, _issue_token(s, user)


def user_from_token(s: Session, token: str | None) -> m.User:
    if not token:
        raise AccountError(401, "請先登入")
    h = hashlib.sha256(token.encode()).hexdigest()
    user = s.scalar(select(m.User).join(m.UserToken, m.UserToken.user_id == m.User.id)
                    .where(m.UserToken.token_hash == h))
    if user is None:
        raise AccountError(401, "登入已失效，請重新登入")
    if user.blocked:
        raise AccountError(403, "這個帳號已被停用")
    return user


def logout(s: Session, token: str) -> None:
    s.query(m.UserToken).filter(m.UserToken.token_hash == hashlib.sha256(token.encode()).hexdigest()).delete()


def update_profile(s: Session, user: m.User, nickname, native_lang, level) -> dict:
    user.nickname, user.native_lang, user.level = _clean_profile(nickname, native_lang, level)
    s.flush()
    return profile(user)


def delete_account(s: Session, user: m.User) -> None:
    """App Review 5.1.1(v): in-app account deletion. Shared decks and the cloud backup go with the account."""
    _backup_path(user).unlink(missing_ok=True)
    for d in s.scalars(select(m.Deck).where(m.Deck.owner_user_id == user.id)):
        s.delete(d)
    s.delete(user)
    s.flush()


# ---- cloud backup (card #902, 問題回報 #1173: 帳號登入與跨裝置同步) -------------------
# One backup file per account: the app's own AppBackup file (words, photos, cards, review
# history, settings), stored as-is so a Worker can move it to an R2 object `backups/<id>`.

def _backup_path(user: m.User):
    return config.MEDIA / "user_backups" / f"{user.id}.bak"


def save_backup(user: m.User, data: bytes) -> dict:
    if not data.startswith(BACKUP_MAGIC):
        raise AccountError(422, "這不是備份檔")
    if len(data) > BACKUP_MAX_BYTES:
        raise AccountError(413, "備份不能超過 200 MB")
    path = _backup_path(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)   # a failed upload never damages the last good backup
    return backup_info(user)


def load_backup(user: m.User) -> bytes:
    path = _backup_path(user)
    if not path.exists():
        raise AccountError(404, "雲端還沒有備份")
    return path.read_bytes()


def backup_info(user: m.User) -> dict:
    path = _backup_path(user)
    if not path.exists():
        return {"exists": False, "size": 0, "updated_at": None}
    st = path.stat()
    return {"exists": True, "size": st.st_size, "updated_at": int(st.st_mtime)}


# ---- sharing ---------------------------------------------------------------

def upload_photo(s: Session, user: m.User, data: bytes) -> int:
    """Stores a user's photo as an unchecked ImageAsset. The existing safety worker
    checks it; a shared deck goes live only when every picture is 'safe'."""
    if not data or len(data) > PHOTO_MAX_BYTES:
        raise AccountError(413, "照片不能超過 5 MB")
    if not (data.startswith(JPEG) or data.startswith(PNG)):
        raise AccountError(415, "只收 JPEG 或 PNG")
    sha = hashlib.sha256(data).hexdigest()
    existing = s.scalar(select(m.ImageAsset).where(m.ImageAsset.sha256 == sha))
    if existing:
        if not (existing.source == "user" and existing.source_image_id.startswith(f"u{user.id}-")):
            raise AccountError(409, "這張照片已經在平台上了")
        return existing.id
    ext = "jpg" if data.startswith(JPEG) else "png"
    rel = f"user/{sha}.{ext}"
    path = config.MEDIA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    a = m.ImageAsset(source="user", source_image_id=f"u{user.id}-{sha[:12]}", author=user.nickname,
                     mime="image/jpeg" if ext == "jpg" else "image/png", size_bytes=len(data),
                     sha256=sha, path=rel, thumbnail_path=rel, status="ready", safety_status="unchecked")
    s.add(a)
    s.flush()
    return a.id


def _slug(s: Session, title: str, user: m.User) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:30] or "deck"
    while True:
        slug = f"u{user.id}-{base}-{secrets.token_hex(2)}"
        if not s.scalar(select(m.Deck.id).where(m.Deck.slug == slug)):
            return slug


def _live_state(s: Session, deck: m.Deck) -> None:
    """pending → shared once all pictures are safe; any blocked picture removes it."""
    if deck.share_status not in ("pending", "shared"):
        return
    if deck.kind == "words":
        status = "shared"
    else:
        states = set(s.scalars(select(m.ImageAsset.safety_status).join(
            m.DeckItem, m.DeckItem.asset_id == m.ImageAsset.id).where(m.DeckItem.deck_id == deck.id)))
        status = "removed" if "blocked" in states else ("shared" if states <= {"safe"} else "pending")
    deck.share_status = status
    deck.published = status == "shared"


def share_deck(s: Session, user: m.User, *, kind: str, title: str, cefr: str | None = None,
               topic: str | None = None, description: str | None = None,
               words: list[dict] | None = None, photos: list[dict] | None = None,
               acknowledged_privacy: bool = False) -> dict:
    """`photos`: [{asset_id (from upload_photo), labels: [{word,pos,cefr,point}]}]."""
    if not acknowledged_privacy:
        raise AccountError(422, "分享前請先確認照片裡沒有他人的臉或隱私資訊")
    if kind not in decks.KINDS:
        raise AccountError(422, "kind 只能是 words 或 photos")
    if cefr and cefr not in decks.CEFR:
        raise AccountError(422, "程度只能是 A1…C2")
    title = (title or "").strip()
    if not title or len(title) > 80:
        raise AccountError(422, "名稱要 1–80 個字")
    by_id = {}
    if kind == "words":
        if not words:
            raise AccountError(422, "至少要有一個單字")
    else:
        for p in photos or []:
            by_id.setdefault(p["asset_id"], p)
        if not by_id:
            raise AccountError(422, "至少要有一張照片")
        for aid, p in by_id.items():
            a = s.get(m.ImageAsset, aid)
            if a is None or a.source != "user" or not (a.source_image_id or "").startswith(f"u{user.id}-"):
                raise AccountError(422, f"照片 {aid} 不是你上傳的")
            if not decks.clean_labels(p.get("labels")):
                raise AccountError(422, f"照片 {aid} 要有至少一個單字標籤")
    deck = m.Deck(slug=_slug(s, title, user), kind=kind, title=title, cefr=cefr, topic=topic,
                  description=(description or "")[:500] or None, author=user.nickname,
                  owner_user_id=user.id, share_status="pending", published=False)
    s.add(deck)
    s.flush()
    if kind == "words":
        decks.set_items(s, deck, words=words)
        if not s.scalar(select(func.count()).select_from(m.DeckItem).where(m.DeckItem.deck_id == deck.id)):
            raise AccountError(422, "至少要有一個單字")
    else:
        for pos, (aid, p) in enumerate(by_id.items()):
            s.add(m.DeckItem(deck_id=deck.id, position=pos, asset_id=aid,
                             labels=decks.clean_labels(p.get("labels"))))
        deck.cover_asset_id = next(iter(by_id))
    s.flush()
    _live_state(s, deck)
    return {**decks.summary(s, deck), "share_status": deck.share_status}


def my_shares(s: Session, user: m.User) -> dict:
    rows = s.scalars(select(m.Deck).where(m.Deck.owner_user_id == user.id).order_by(m.Deck.id.desc())).all()
    for d in rows:
        _live_state(s, d)
    return {"decks": [{**decks.summary(s, d), "share_status": d.share_status, "downloads": d.downloads}
                      for d in rows]}


def withdraw(s: Session, user: m.User, slug: str) -> None:
    deck = s.scalar(select(m.Deck).where(m.Deck.slug == slug, m.Deck.owner_user_id == user.id))
    if deck is None:
        raise AccountError(404, "沒有這個分享")
    deck.share_status, deck.published = "private", False
    s.flush()


# ---- browsing, downloads, reports, blocks ------------------------------------

def public_list(s: Session, viewer: m.User | None = None, target: str | None = None,
                native: str | None = None) -> dict:
    """decks.public_list minus decks by authors the viewer blocked; also settles pending shares."""
    for d in s.scalars(select(m.Deck).where(m.Deck.share_status == "pending")).all():
        _live_state(s, d)
    s.flush()
    data = decks.public_list(s, target, native)
    blocked = set()
    if viewer:
        blocked = set(s.scalars(select(m.UserBlock.blocked_user_id).where(m.UserBlock.user_id == viewer.id)))
    owners = dict(s.execute(select(m.Deck.slug, m.Deck.owner_user_id)).all())
    data["decks"] = [d for d in data["decks"] if owners.get(d["slug"]) not in blocked]
    return data


def count_download(s: Session, slug: str) -> None:
    s.query(m.Deck).filter(m.Deck.slug == slug, m.Deck.published.is_(True)).update(
        {m.Deck.downloads: m.Deck.downloads + 1})


def report_deck(s: Session, user: m.User, slug: str, reason: str) -> None:
    deck = s.scalar(select(m.Deck).where(m.Deck.slug == slug))
    if deck is None:
        raise AccountError(404, "沒有這個集合")
    reason = (reason or "").strip()
    if not reason:
        raise AccountError(422, "請寫檢舉原因")
    s.add(m.DeckReport(deck_id=deck.id, reporter_id=user.id, reason=reason[:500]))
    s.flush()


def block_author(s: Session, user: m.User, slug: str) -> None:
    deck = s.scalar(select(m.Deck).where(m.Deck.slug == slug))
    if deck is None or deck.owner_user_id is None or deck.owner_user_id == user.id:
        raise AccountError(404, "找不到可封鎖的作者")
    if s.get(m.UserBlock, (user.id, deck.owner_user_id)) is None:
        s.add(m.UserBlock(user_id=user.id, blocked_user_id=deck.owner_user_id))
    s.flush()


# ---- admin (X-API-Key) --------------------------------------------------------

def stats(s: Session) -> dict:
    shared = m.Deck.owner_user_id.is_not(None)
    rows = s.execute(select(m.Deck, m.User.nickname).join(m.User, m.User.id == m.Deck.owner_user_id, isouter=True)
                     .where(shared).order_by(m.Deck.id.desc())).all()
    reports = dict(s.execute(select(m.DeckReport.deck_id, func.count()).where(m.DeckReport.resolved.is_(False))
                             .group_by(m.DeckReport.deck_id)).all())
    items = dict(s.execute(select(m.DeckItem.deck_id, func.count()).group_by(m.DeckItem.deck_id)).all())
    decks_out = []
    for d, nick in rows:
        n = items.get(d.id, 0)
        decks_out.append({"slug": d.slug, "title": d.title, "kind": d.kind, "author": nick,
                          "share_status": d.share_status, "words": n if d.kind == "words" else 0,
                          "images": n if d.kind == "photos" else 0, "downloads": d.downloads,
                          "open_reports": reports.get(d.id, 0),
                          "created_at": d.created_at.isoformat() if d.created_at else None})
    return {"users": s.scalar(select(func.count()).select_from(m.User)) or 0,
            "sharers": len({d.owner_user_id for d, _ in rows if d.share_status != "private"}),
            "shared_decks": sum(d["share_status"] == "shared" for d in decks_out),
            "downloads": sum(d["downloads"] for d in decks_out),
            "decks": decks_out,
            "latest": decks_out[:10],
            "reported": [d for d in decks_out if d["open_reports"]]}


def takedown(s: Session, slug: str, restore: bool = False) -> None:
    deck = s.scalar(select(m.Deck).where(m.Deck.slug == slug))
    if deck is None:
        raise AccountError(404, "沒有這個集合")
    deck.published = False
    if restore:
        deck.share_status = "pending"
        _live_state(s, deck)
    else:
        deck.share_status = "hidden"
        s.query(m.DeckReport).filter(m.DeckReport.deck_id == deck.id).update({m.DeckReport.resolved: True})
    s.flush()


class BanIn(BaseModel):
    blocked: bool = True


def register(app, auth):
    @app.get("/share-stats", dependencies=[auth])
    def share_stats(s: Session = Depends(db.get_session)):
        return stats(s)

    @app.post("/share-stats/{slug}/takedown", dependencies=[auth])
    def share_takedown(slug: str, restore: bool = False, s: Session = Depends(db.get_session)):
        try:
            takedown(s, slug, restore)
        except AccountError as e:
            raise HTTPException(e.status, e.message)
        return {"slug": slug, "restored": restore}

    @app.put("/users/{user_id}/ban", dependencies=[auth])
    def ban_user(user_id: int, body: BanIn, s: Session = Depends(db.get_session)):
        user = s.get(m.User, user_id)
        if user is None:
            raise HTTPException(404, "沒有這個使用者")
        user.blocked = body.blocked
        if body.blocked:
            for d in s.scalars(select(m.Deck).where(m.Deck.owner_user_id == user.id)):
                d.share_status, d.published = "hidden", False
            s.query(m.UserToken).filter(m.UserToken.user_id == user.id).delete()
        return {"id": user.id, "blocked": user.blocked}
