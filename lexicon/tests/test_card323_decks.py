"""卡片集／圖片集 (card #323): admin CRUD and the public read-only views."""

import pytest
from fastapi.testclient import TestClient

H = {"X-API-Key": "test-key"}


@pytest.fixture
def client(session, monkeypatch):
    from app import config
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    with TestClient(app) as c:
        yield c


def _asset(s, tags, status="ready", safety="safe"):
    from app import models as m
    a = m.ImageAsset(source="t", source_image_id=str(len(tags)) + status, status=status,
                     safety_status=safety, tags=tags)
    s.add(a)
    s.flush()
    return a.id


def test_word_deck_lifecycle_and_public_view(client):
    r = client.post("/decks", headers=H, json={
        "slug": "basic", "kind": "words", "title": "基礎", "cefr": "A1", "published": True,
        "words": [{"word": "Apple", "pos": "noun", "cefr": "A1"}, {"word": "apple", "pos": "noun"},
                  {"word": "run", "pos": "verb"}]})
    assert r.status_code == 201 and r.json()["count"] == 2   # duplicates collapse
    assert client.post("/decks", headers=H, json={"slug": "basic", "kind": "words", "title": "x"}).status_code == 409
    assert client.post("/decks", headers=H, json={"slug": "Bad Slug", "kind": "words", "title": "x"}).status_code == 422
    assert client.post("/decks", headers=H, json={"slug": "z", "kind": "words", "title": "x", "cefr": "D9"}).status_code == 422

    from app import db, decks
    with db.session_scope() as s:
        assert [d["slug"] for d in decks.public_list(s)["decks"]] == ["basic"]
        deck = decks.public_deck(s, "basic")
        assert deck["items"][0] == {"word": "apple", "pos": "noun", "cefr": "A1"}
        assert decks.public_deck(s, "nope") is None

    client.put("/decks/basic", headers=H, json={"published": False})
    with db.session_scope() as s:   # unpublished decks are never public
        assert decks.public_list(s)["decks"] == [] and decks.public_deck(s, "basic") is None
    assert client.delete("/decks/basic", headers=H).json() == {"deleted": "basic"}
    assert client.get("/decks", headers=H).json()["decks"] == []


def test_photo_deck_takes_labels_from_tags_and_rejects_bad_pictures(client):
    from app import db, decks
    tags = [{"word": "Fruit", "pos": "noun", "cefr": "A1", "point": [0.5, 0.25], "score": 0.9},
            {"word": "fruit", "pos": "noun", "point": [0.1, 0.1], "score": 0.5},   # duplicate word
            {"word": "nopoint", "pos": "noun", "score": 0.99}]
    with db.session_scope() as s:
        good = _asset(s, tags)
        pending = _asset(s, tags, status="pending")
        unsafe = _asset(s, tags, safety="unsafe")
        untagged = _asset(s, [])
    body = {"slug": "pics", "kind": "photos", "title": "圖", "cefr": "B1", "published": True,
            "cover_asset_id": good}
    assert client.post("/decks", headers=H, json={**body, "asset_ids": [pending]}).status_code == 422
    assert client.post("/decks", headers=H, json={**body, "slug": "u", "asset_ids": [unsafe]}).status_code == 422
    assert client.post("/decks", headers=H, json={**body, "slug": "t", "asset_ids": [untagged]}).status_code == 422
    assert client.post("/decks", headers=H, json={**body, "asset_ids": [good, good]}).json()["count"] == 1
    with db.session_scope() as s:
        item = decks.public_deck(s, "pics")["items"][0]
    assert item == {"asset_id": good, "labels": [
        {"word": "fruit", "pos": "noun", "cefr": "A1", "point": [0.5, 0.25]}]}


def test_public_rate_limit_covers_deck_paths():
    import importlib.util, pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    src = (root / "serve_app.py").read_text(encoding="utf-8")
    assert "'/api/decks': " in src and "path.startswith('/api/decks/')" in src


def test_deck_images_picker_filters_by_word_and_level(client):
    from app import db
    tags = [{"word": "tomato", "pos": "noun", "cefr": "A2", "point": [0.5, 0.5], "score": 0.9},
            {"word": "ripe", "pos": "adjective", "cefr": "B1", "point": [0.2, 0.2], "score": 0.8}]
    with db.session_scope() as s:
        a = _asset(s, tags)
        _asset(s, [], status="ready")
        for x in s.query(__import__("app.models", fromlist=["m"]).ImageAsset).all():
            x.tag_status = "done"
    r = client.get("/deck-images?word=toma", headers=H).json()
    assert [x["id"] for x in r] == [a] and r[0]["words"] == "tomato, ripe"
    assert client.get("/deck-images?cefr=B1", headers=H).json()[0]["at_level"] == 1
    assert client.get("/deck-images?cefr=C2", headers=H).json() == []
    assert client.get("/deck-images?word=zzz", headers=H).json() == []
