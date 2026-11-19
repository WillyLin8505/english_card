"""Provider precedence, corpus selection and night gates; no live DB or synthesis."""
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.exporter import sentence_audio_asset, sentence_audio_url, sentence_audio_urls, SENTENCE_VOICES

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import card1227_piper_tts as fr


@pytest.mark.parametrize("azure_status,azure_path,winner", [
    ("ready", "a.mp3", "azure"), ("failed", "a.mp3", "piper"),
    ("pending", "a.mp3", "piper"), ("ready", None, "piper"),
])
def test_preferred_usable_provider(azure_status, azure_path, winner):
    azure, piper = sentence_audio_urls("fr", "h")
    assets = {azure: SimpleNamespace(status=azure_status, path=azure_path, name="azure"),
              piper: SimpleNamespace(status="ready", path="p.mp3", name="piper")}
    assert sentence_audio_asset(assets, "fr", "h").name == winner


def test_existing_producers_keep_primary_url():
    assert SENTENCE_VOICES["fr"] == "fr-FR-DeniseNeural"
    assert sentence_audio_url("fr", "h") == fr.AZURE + "h"
    assert sentence_audio_url("en", "h") == "piper-tts://piper-lessac-medium/s/h"
    assert sentence_audio_asset({}, "de", "h") is None


@pytest.mark.parametrize("hour,minute,ok", [(0,59,False),(1,0,True),(6,29,True),(6,30,False),(12,0,False)])
def test_night_window(hour, minute, ok):
    assert fr.in_window(datetime(2026, 11, 19, hour, minute, tzinfo=fr.TZ)) == ok


def test_no_night_work_before_listening(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "BASE", tmp_path)
    monkeypatch.setattr(fr, "in_window", lambda _: True)
    monkeypatch.setattr(fr, "batch", lambda **_: pytest.fail("must not synthesize"))
    assert fr.night_tick() == 3


def test_review_invalidated_by_changed_samples(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "BASE", tmp_path)
    monkeypatch.setattr(fr, "fingerprint", lambda: {"samples": "current"})
    fr.write_json(tmp_path / "listening_review.json", {"fingerprint": {"samples": "old"},
        "reviewer": "listener", "all_20": True, "elisions": True, "numbers": True, "abbreviations": True})
    assert not fr.reviewed()


def test_selection_skips_azure_and_uses_lowest_cefr(monkeypatch):
    # Compile DISTINCT ON against PostgreSQL via a recording session; SQL is also
    # exercised against the real read-only corpus during this card's measurement.
    calls = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, query, params):
            calls.append((str(query), params))
            return SimpleNamespace(mappings=lambda: [])
    monkeypatch.setattr(fr.db, "SessionLocal", Session)
    assert fr.pending(200) == []
    sql, params = calls[0]
    assert "NOT EXISTS" in sql and "DISTINCT ON (text_hash)" in sql
    assert "ORDER BY rank, text_hash LIMIT :limit" in sql
    assert params["azure"] == fr.AZURE and params["piper"] == fr.PREFIX


def test_rollback_preserves_english_azure_and_changed_rows(tmp_path, monkeypatch):
    from app import models as m
    engine = create_engine("sqlite://")
    m.AudioAsset.__table__.create(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(fr.db, "SessionLocal", factory)
    monkeypatch.setattr(fr, "BASE", tmp_path / "card1227")
    monkeypatch.setattr(fr.config, "MEDIA", tmp_path / "media")
    fr.BASE.mkdir()
    folder = fr.config.MEDIA / "audio/fr"
    folder.mkdir(parents=True)
    assets = [
        ("fr", fr.SPEAKER, fr.PREFIX + "mine", "mine"),
        ("fr", fr.SPEAKER, fr.PREFIX + "changed", "new"),
        ("fr", "Denise", fr.AZURE + "azure", "azure"),
        ("en", "lessac", "piper-tts://piper-lessac-medium/s/en", "english")]
    with factory() as s:
        for lang, speaker, url, digest in assets:
            (folder / (digest + ".mp3")).write_bytes(digest.encode())
            s.add(m.AudioAsset(language=lang, source="piper_tts_sentence", speaker=speaker,
                source_url=url, sha256=digest, path="audio/fr/" + digest + ".mp3"))
        s.commit()
    (fr.BASE / "insert_journal.jsonl").write_text("\n".join(json.dumps({
        "source_url": fr.PREFIX + name, "sha256": digest}) for name, digest in
        [("mine", "mine"), ("changed", "old")]), encoding="utf-8")
    fr.rollback()
    with factory() as s:
        assert s.query(m.AudioAsset).count() == 3
    assert not (folder / "mine.mp3").exists()
    assert (folder / "new.mp3").exists()
    backup = next(fr.BASE.glob("rollback_*"))
    assert (backup / "mine.mp3").read_bytes() == b"mine"
    assert json.loads((backup / "audio_assets.json").read_text())[0]["source_url"] == fr.PREFIX + "mine"
    assert (fr.BASE / "paused.json").exists()


def test_piper_gate_is_exclusive():
    from piper_slot import slot
    with slot() as first:
        assert first
        with slot() as second:
            assert not second
