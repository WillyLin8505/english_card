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


def test_post_qc_failure_rolls_back_only_batch_even_after_window(tmp_path, monkeypatch):
    from contextlib import nullcontext
    monkeypatch.setattr(fr, "BASE", tmp_path)
    monkeypatch.setattr(fr, "slot", lambda: nullcontext(True))
    monkeypatch.setattr(fr, "english_running", lambda: False)
    monkeypatch.setattr(fr, "resource_ok", lambda: True)
    monkeypatch.setattr(fr, "in_window", lambda _: False)
    monkeypatch.setattr(fr, "qc_step", lambda *args: 1)
    rolled_back = []
    monkeypatch.setattr(fr, "rollback", lambda urls: rolled_back.append(urls))
    fr.write_json(tmp_path / "night_phase.json", {"phase": "after", "hashes": ["only-this"]})
    assert fr.night_tick() == 0
    assert rolled_back == [{fr.PREFIX + "only-this"}]


def test_incomplete_post_qc_retries_without_starting_another_batch(tmp_path, monkeypatch):
    from contextlib import nullcontext
    monkeypatch.setattr(fr, "BASE", tmp_path)
    monkeypatch.setattr(fr, "slot", lambda: nullcontext(True))
    monkeypatch.setattr(fr, "english_running", lambda: False)
    monkeypatch.setattr(fr, "resource_ok", lambda: True)
    monkeypatch.setattr(fr, "qc_step", lambda *args: 2)
    monkeypatch.setattr(fr, "batch", lambda **_: pytest.fail("must finish QC first"))
    fr.write_json(tmp_path / "night_phase.json", {"phase": "after", "hashes": ["h"]})
    fr.night_tick()
    assert json.loads((tmp_path / "night_phase.json").read_text())["phase"] == "after"


@pytest.mark.parametrize("azure_status,expected", [(None, 2), ("ready", 1), ("failed", 2)])
def test_french_pack_links_real_sentence_audio(tmp_path, monkeypatch, azure_status, expected):
    import sqlite3
    from app import exporter, views, models as m
    from app.text import text_hash, example_key
    engine = create_engine("sqlite://")
    # No shared PostgreSQL test database; omit unrelated PostgreSQL FTS indexes.
    m.Base.metadata.create_all(engine, tables=[t for t in m.Base.metadata.sorted_tables
                                              if not t.name.startswith("tatoeba_")])
    monkeypatch.setattr(exporter, "_images", lambda *args: [])
    monkeypatch.setattr(views, "word_images", lambda *args: {})
    sentence = "La pomme est rouge."
    h, k = text_hash(sentence), example_key(sentence)
    with sessionmaker(engine)() as s:
        s.add(m.Lexeme(id=1, language="fr", lemma="pomme", normalized="pomme", pos="noun", status="full", cefr="A1"))
        s.add(m.Sense(id=1, lexeme_id=1, sense_key="fruit", ordinal=0))
        s.add(m.Example(id=1, lexeme_id=1, language="fr", text=sentence, text_hash=h,
                        source="tatoeba", ordinal=0))
        fields = {"definition": [{"sense_key": "fruit", "gloss": "fruit du pommier", "source": "kaikki"}],
                  "native_definition": [{"sense_key": "fruit", "text": "apple"}],
                  "example_sentences": [{"text": sentence, "key": k, "sense_key": "fruit", "source": "tatoeba"}]}
        for i, (field, items) in enumerate(fields.items(), 1):
            s.add(m.FieldValue(id=i, target_language="fr", native_language="en", lemma="pomme",
                              field=field, status="complete", items=items))
        s.add(m.AudioAsset(id=2, language="fr", source="piper_tts_sentence", source_url=fr.PREFIX+h,
                          path="audio/fr/piper.mp3", sha256="piper", status="ready", speaker=fr.SPEAKER))
        if azure_status:
            s.add(m.AudioAsset(id=1, language="fr", source="azure_tts_sentence", source_url=fr.AZURE+h,
                              path="audio/fr/azure.mp3", sha256="azure", status=azure_status))
        s.commit()
        assert views.word(s, "fr", "en", "pomme")["examples"][0]["audio"]["id"] == expected
        db_path = tmp_path / "pack.sqlite"
        exporter._build(s, db_path, "fr", "en", None, False, tmp_path, copy_media=False)
        with sqlite3.connect(db_path) as con:
            assert con.execute("SELECT audio_id FROM examples").fetchone() == (expected,)
            assert con.execute("SELECT source_url FROM audio").fetchone()[0] == (fr.AZURE if expected == 1 else fr.PREFIX) + h


def test_audio_search_finds_sentence_older_than_2000_assets(tmp_path, monkeypatch):
    from app import views, models as m
    engine = create_engine("sqlite://")
    for cls in (m.AudioAsset, m.Lexeme, m.Pronunciation, m.FieldValue):
        cls.__table__.create(engine)
    monkeypatch.setattr(views.config, "MEDIA", tmp_path)
    with sessionmaker(engine)() as s:
        s.add(m.AudioAsset(id=1, language="fr", source="piper_tts_sentence", source_url=fr.PREFIX + "old-sentence"))
        s.add_all([m.AudioAsset(id=i, language="en", source="other", source_url=f"other://{i}") for i in range(2, 2004)])
        s.commit()
        result = views.audio_library(s, q="old-sentence")
        assert [a["id"] for a in result["assets"]] == [1]


def test_legacy_english_rollback_keeps_french_piper(tmp_path, monkeypatch):
    import card879_piper_tts as en
    from app import models as m
    engine = create_engine("sqlite://")
    m.AudioAsset.__table__.create(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(en.db, "SessionLocal", factory)
    monkeypatch.setattr(en.config, "MEDIA", tmp_path)
    with factory() as s:
        for i, language in enumerate(("en", "fr"), 1):
            (tmp_path / (language + ".mp3")).write_bytes(language.encode())
            s.add(m.AudioAsset(id=i, language=language, source="piper_tts_sentence",
                              source_url=language, path=language + ".mp3"))
        s.commit()
    en.rollback()
    with factory() as s:
        assert [a.language for a in s.query(m.AudioAsset)] == ["fr"]
    assert (tmp_path / "fr.mp3").exists()


def test_production_requires_quality_gate_even_after_listening(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "BASE", tmp_path)
    monkeypatch.setattr(fr, "in_window", lambda _: True)
    monkeypatch.setattr(fr, "reviewed", lambda: True)
    monkeypatch.setattr(fr, "batch", lambda **_: pytest.fail("QC not complete"))
    assert fr.night_tick() == 3


@pytest.mark.parametrize("dry, french_exit, en_launches", [(True,0,0),(False,0,0),(False,3,1),(False,1,0)])
def test_dispatch_reserves_tick_for_french_and_uses_bounded_runner(tmp_path, monkeypatch, dry, french_exit, en_launches):
    import dispatch_tick as dt
    for name in ("card879_piper_tts.py", "card1227_piper_tts.py", "card1227_run_bounded.py"):
        (tmp_path / name).touch()
    monkeypatch.setattr(dt, "TOOLS", tmp_path)
    monkeypatch.setattr(dt, "python_exe", lambda: sys.executable)
    monkeypatch.setattr(dt, "log", lambda *_: None)
    runs, launches = [], []
    def run(cmd, **kw):
        runs.append(cmd)
        return SimpleNamespace(returncode=french_exit, stderr="failure" if french_exit == 1 else "")
    monkeypatch.setattr(dt.subprocess, "run", run)
    monkeypatch.setattr(dt.subprocess, "Popen", lambda cmd, **kw: launches.append(cmd))
    tick = object.__new__(dt.Tick)
    tick.dry = dry
    tick.sentence_audio_night()
    assert len(launches) == en_launches
    assert len(runs) == (0 if dry else 1)
    if runs:
        assert Path(runs[0][1]).name == "card1227_run_bounded.py"
