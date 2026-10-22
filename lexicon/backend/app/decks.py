"""卡片集／圖片集 (card #323, 問題回報 #320): decks the learner can browse and
download in the app. `public_list` / `public_deck` are the read-only,
keyless views served by serve_app.py (rate-limited like the dictionary);
`register` adds the admin API that creates and edits decks."""

from __future__ import annotations

import re

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field as PField
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import db
from . import models as m

KINDS = ("words", "photos")
CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
LABEL_LIMIT = 8   # labels a deck picture keeps (the app lists five words per photo)


def _count(s: Session, deck: m.Deck) -> int:
    return s.scalar(select(func.count()).select_from(m.DeckItem).where(m.DeckItem.deck_id == deck.id)) or 0


I18N_FIELDS = ("title", "topic", "description", "author")


def summary(s: Session, deck: m.Deck, native: str | None = None) -> dict:
    """`native` swaps in the deck's text for that language when it has one
    (問題回報 #537); decks without a translation keep the zh-TW original."""
    tr = ((deck.i18n or {}).get(native) or {}) if native else {}
    def pick(f):
        return tr.get(f) or getattr(deck, f)
    return {"slug": deck.slug, "kind": deck.kind, "title": pick("title"), "cefr": deck.cefr,
            "topic": pick("topic"), "description": pick("description"), "author": pick("author"),
            "cover_asset_id": deck.cover_asset_id, "count": _count(s, deck),
            "target_language": deck.target_language,
            "updated_at": deck.updated_at.isoformat() if deck.updated_at else None}


def public_list(s: Session, target: str | None = None, native: str | None = None) -> dict:
    """Published decks; with `target` only that learning language's (問題回報 #501)."""
    q = select(m.Deck).where(m.Deck.published.is_(True))
    if target:
        q = q.where(m.Deck.target_language == target)
    decks = s.scalars(q.order_by(m.Deck.id)).all()
    return {"decks": [summary(s, d, native) for d in decks]}


def _credit(a) -> dict:
    """Who made a picture and under which licence (CC BY needs the credit shown)."""
    if a is None:
        return {}
    return {"license": a.license_code, "license_url": a.license_url,
            "author": a.author, "page_url": a.page_url}


def public_deck(s: Session, slug: str) -> dict | None:
    """The deck with everything the app needs to add it offline: words as
    (word, pos, cefr); pictures as asset ids (fetched from /api/image) with labels."""
    deck = s.scalar(select(m.Deck).where(m.Deck.slug == slug, m.Deck.published.is_(True)))
    if deck is None:
        return None
    items = s.scalars(select(m.DeckItem).where(m.DeckItem.deck_id == deck.id)
                      .order_by(m.DeckItem.position, m.DeckItem.id)).all()
    if deck.kind == "words":
        rows = [{"word": i.lemma, "pos": i.pos or "", "cefr": i.cefr} for i in items]
    else:
        assets = {a.id: a for a in s.scalars(select(m.ImageAsset).where(
            m.ImageAsset.id.in_([i.asset_id for i in items if i.asset_id])))}
        rows = [{"asset_id": i.asset_id, "labels": i.labels or [], **_credit(assets.get(i.asset_id))}
                for i in items]
    return {**summary(s, deck), "items": rows}


def clean_labels(tags: list | None, limit: int = LABEL_LIMIT) -> list[dict]:
    """A picture's AI tags reduced to what the app needs, best first."""
    out, seen = [], set()
    for t in sorted(tags or [], key=lambda t: -(t.get("score") or 0)):
        word = (t.get("word") or "").strip().lower()
        point = t.get("point")
        if not word or word in seen or not point or len(point) != 2:
            continue
        seen.add(word)
        out.append({"word": word, "pos": t.get("pos") or "", "cefr": t.get("cefr"),
                    "point": [round(float(point[0]), 3), round(float(point[1]), 3)]})
        if len(out) >= limit:
            break
    return out


def set_items(s: Session, deck: m.Deck, *, words: list[dict] | None = None,
              asset_ids: list[int] | None = None) -> int:
    """Replaces a deck's items: `words` [{word, pos, cefr}] for a word deck,
    `asset_ids` for a picture deck (labels come from each picture's tags)."""
    s.query(m.DeckItem).filter(m.DeckItem.deck_id == deck.id).delete()
    n = 0
    if deck.kind == "words":
        seen = set()
        for w in words or []:
            key = ((w.get("word") or "").strip().lower(), w.get("pos") or "")
            if not key[0] or key in seen:
                continue
            seen.add(key)
            s.add(m.DeckItem(deck_id=deck.id, position=n, lemma=key[0], pos=key[1] or None,
                             cefr=w.get("cefr")))
            n += 1
    else:
        for aid in dict.fromkeys(asset_ids or []):
            a = s.get(m.ImageAsset, aid)
            if a is None or a.status != "ready" or a.safety_status != "safe":
                raise HTTPException(422, f"圖片 {aid} 不能放進圖片集（不存在、未就緒或未通過安全檢查）")
            labels = clean_labels(a.tags)
            if not labels:
                raise HTTPException(422, f"圖片 {aid} 還沒有標籤")
            s.add(m.DeckItem(deck_id=deck.id, position=n, asset_id=aid, labels=labels))
            n += 1
    s.flush()
    return n


class DeckIn(BaseModel):
    slug: str
    kind: str
    title: str = PField(min_length=1)
    cefr: str | None = None
    topic: str | None = None
    description: str | None = None
    author: str | None = None
    cover_asset_id: int | None = None
    published: bool = False
    words: list[dict] | None = None
    asset_ids: list[int] | None = None
    i18n: dict | None = None


class DeckPatch(BaseModel):
    title: str | None = None
    cefr: str | None = None
    topic: str | None = None
    description: str | None = None
    author: str | None = None
    cover_asset_id: int | None = None
    published: bool | None = None
    words: list[dict] | None = None
    asset_ids: list[int] | None = None
    i18n: dict | None = None


def _check(kind: str | None = None, cefr: str | None = None) -> None:
    if kind is not None and kind not in KINDS:
        raise HTTPException(422, "kind 只能是 words 或 photos")
    if cefr is not None and cefr not in CEFR:
        raise HTTPException(422, "程度只能是 A1…C2")


def register(app, auth):
    @app.get("/decks", dependencies=[auth])
    def list_decks(s: Session = Depends(db.get_session)):
        return {"decks": [{**summary(s, d), "published": d.published}
                          for d in s.scalars(select(m.Deck).order_by(m.Deck.id))]}

    @app.get("/deck-images", dependencies=[auth])
    def deck_images(word: str = "", cefr: str = "", limit: int = Query(60, ge=1, le=200),
                    s: Session = Depends(db.get_session)):
        """Library pictures that can go into a picture deck: safe, tagged, filtered by a
        label word and/or the CEFR level most of their labels have."""
        _check(None, cefr or None)
        rows = s.execute(text("""
            SELECT a.id, a.thumbnail_path, jsonb_array_length(a.tags) AS n,
              (SELECT string_agg(x->>'word', ', ') FROM (SELECT x FROM jsonb_array_elements(a.tags) x
                 ORDER BY (x->>'score')::float DESC NULLS LAST LIMIT 6) q) AS words,
              (SELECT count(*) FROM jsonb_array_elements(a.tags) x WHERE x->>'cefr' = :cefr) AS at_level
            FROM image_assets a
            WHERE a.status = 'ready' AND a.safety_status = 'safe' AND a.tag_status = 'done'
              AND jsonb_typeof(a.tags) = 'array' AND jsonb_array_length(a.tags) > 0
              AND (:word = '' OR EXISTS (SELECT 1 FROM jsonb_array_elements(a.tags) x
                                         WHERE x->>'word' ILIKE :like))
            ORDER BY at_level DESC, a.id LIMIT :limit"""),
            {"cefr": cefr, "word": word.strip(), "like": f"%{word.strip()}%", "limit": limit}).mappings()
        return [dict(r) for r in rows if not cefr or r["at_level"] > 0]

    @app.get("/decks/{slug}", dependencies=[auth])
    def get_deck(slug: str, s: Session = Depends(db.get_session)):
        deck = s.scalar(select(m.Deck).where(m.Deck.slug == slug))
        if deck is None:
            raise HTTPException(404, "沒有這個集合")
        items = s.scalars(select(m.DeckItem).where(m.DeckItem.deck_id == deck.id)
                          .order_by(m.DeckItem.position)).all()
        return {**summary(s, deck), "published": deck.published,
                "items": [{"lemma": i.lemma, "pos": i.pos, "cefr": i.cefr,
                           "asset_id": i.asset_id, "labels": i.labels} for i in items]}

    @app.post("/decks", dependencies=[auth], status_code=201)
    def create_deck(body: DeckIn, s: Session = Depends(db.get_session)):
        _check(body.kind, body.cefr)
        if not SLUG.match(body.slug):
            raise HTTPException(422, "slug 只能用小寫英數與 -")
        if s.scalar(select(m.Deck.id).where(m.Deck.slug == body.slug)):
            raise HTTPException(409, "slug 已經有人用了")
        deck = m.Deck(**body.model_dump(exclude={"words", "asset_ids"}))
        s.add(deck)
        s.flush()
        set_items(s, deck, words=body.words, asset_ids=body.asset_ids)
        return summary(s, deck)

    @app.put("/decks/{slug}", dependencies=[auth])
    def update_deck(slug: str, body: DeckPatch, s: Session = Depends(db.get_session)):
        deck = s.scalar(select(m.Deck).where(m.Deck.slug == slug))
        if deck is None:
            raise HTTPException(404, "沒有這個集合")
        _check(None, body.cefr)
        for k, v in body.model_dump(exclude={"words", "asset_ids"}, exclude_unset=True).items():
            setattr(deck, k, v)
        if body.words is not None or body.asset_ids is not None:
            set_items(s, deck, words=body.words, asset_ids=body.asset_ids)
        s.flush()
        return summary(s, deck)

    @app.delete("/decks/{slug}", dependencies=[auth])
    def delete_deck(slug: str, s: Session = Depends(db.get_session)):
        deck = s.scalar(select(m.Deck).where(m.Deck.slug == slug))
        if deck is None:
            raise HTTPException(404, "沒有這個集合")
        s.delete(deck)
        return {"deleted": slug}
