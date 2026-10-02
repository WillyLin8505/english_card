"""Test setup. Unit tests need nothing; integration tests use the
PostgreSQL database `lexicon_test` (LEXICON_TEST_DATABASE_URL, or the
lexicon/.env credentials) and skip when it isn't reachable. External
sources are never called: integration tests swap in fake adapters."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))

from app import catalog, config, db  # noqa: E402
from app.adapters import ADAPTERS, Candidate, SourceAdapter  # noqa: E402

TEST_URL = config.database_url(test=True)


def _reachable() -> bool:
    try:
        from sqlalchemy import create_engine, text
        e = create_engine(TEST_URL)
        with e.connect() as c:
            c.execute(text("SELECT 1"))
        e.dispose()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def pg():
    """The migrated test database (migrated once per session)."""
    if not _reachable():
        pytest.skip("PostgreSQL test database lexicon_test is not reachable")
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(HOME / "alembic.ini"))
    cfg.set_main_option("script_location", str(HOME / "migrations"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={TEST_URL}"]})()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    db.use_engine(TEST_URL)
    return cfg


@pytest.fixture
def session(pg):
    """A clean database for each test (all rows removed, then seeded)."""
    from sqlalchemy import text
    from app import models as m, policies
    with db.engine.begin() as c:
        names = ", ".join(t.name for t in m.Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    with db.session_scope() as s:
        policies.seed(s)
    s = db.SessionLocal()
    yield s
    s.rollback()
    s.close()


class FakeAdapter(SourceAdapter):
    """Returns canned values: data[field] = list of (value, key, slot)."""

    def __init__(self, key: str, data: dict | None = None, fail: set | None = None):
        self.key = key
        self.data = data or {}
        self.fail = fail or set()
        self.calls: list[tuple[str, str]] = []

    def lookup(self, field_key, ctx):
        from app.adapters import SourceError
        self.calls.append((ctx.lemma, field_key))
        if field_key in self.fail or "*" in self.fail:
            raise SourceError("network", f"{self.key} is down")
        rows = self.data.get(field_key, [])
        if callable(rows):
            rows = rows(ctx)
        out = []
        for value, key, slot in rows:
            c = Candidate(field_key, ctx.native if catalog.FIELD[field_key].scope == "native"
                          else ctx.target, dict(value), key, source=self.key, slot=slot)
            reason = self.validate(c, ctx)
            if reason:
                c.valid, c.invalid_reason = False, reason
            out.append(c)
        return out


@pytest.fixture
def fakes(monkeypatch):
    """Replace every adapter with an empty fake; tests fill in data."""
    made = {}
    for key in catalog.SOURCES:
        made[key] = FakeAdapter(key)
        monkeypatch.setitem(ADAPTERS, key, made[key])
    # Sense pictures are searched after a word is stored; never online in tests.
    from app import images
    monkeypatch.setattr(images, "auto_fetch",
                        lambda *a, **k: {"senses": 0, "images": 0, "errors": []})
    return made


def apple_data(fakes):
    """A small, consistent English headword across sources."""
    k = fakes["kaikki"]
    k.data = {
        "pos": [({"pos": "noun"}, "noun", "noun")],
        "definition": [({"pos": "noun", "gloss": "A round fruit.", "sense_key": "s1",
                         "gloss_language": "en"}, "s1", "noun"),
                       ({"pos": "noun", "gloss": "An apple tree.", "sense_key": "s2",
                         "gloss_language": "en"}, "s2", "noun")],
        "native_definition": [({"sense_key": "s1", "text": "蘋果"}, "s1", "s1")],
        "ipa": [({"ipa": "/ˈæp.əl/", "accent": ["US"]}, "/ˈæp.əl/", "")],
        "noun_plural": [({"form": "apples"}, "apples", "")],
        "verb_past": [({"form": "appled"}, "appled", "")],
        "synonyms": [({"word": "pome", "pos": "noun"}, "pome", "")],
        "etymology_text": [({"text": "From Old English æppel."}, "e", "")],
    }
    fakes["tatoeba"].data = {
        "example_sentences": [({"text": "I ate an apple today.", "tatoeba_id": 1,
                                 "sense_key": "s1"}, "ex1", ""),
                              ({"text": "The apple is red.", "tatoeba_id": 2,
                                 "sense_key": "s1"}, "ex2", "")],
        "example_translation": [({"example_key": "ex1", "text": "我今天吃了一顆蘋果。"}, "ex1",
                                 "ex1")],
    }
    fakes["oewn"].data = {"synonyms": [({"word": "orchard apple", "pos": "noun"}, "orchard apple",
                                        "")]}
    fakes["cmudict"].data = {"phonemes": [({"phonemes": "AE1 P AH0 L"}, "AE1 P AH0 L", "")]}
    fakes["cefrj"].data = {"cefr": [({"level": "A1", "by_pos": {"noun": "A1"}}, "A1", "")]}
    fakes["ai_translate"].data = {
        "native_definition": lambda ctx: [({"sense_key": s, "text": "蘋果樹", "ai": True}, s, s)
                                          for s in ctx.memo.get(("missing_slots",
                                                                 "native_definition")) or []],
    }
    return fakes
