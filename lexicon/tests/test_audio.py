"""Audio: MIME by magic bytes, SHA-256 dedupe, atomic placement."""

import hashlib

from app import audio as audio_mod, config
from app import models as m
from app.adapters import http

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 200


def test_sniff():
    assert audio_mod.sniff(MP3) == ("audio/mpeg", "mp3")
    assert audio_mod.sniff(b"OggS\x00\x02") == ("audio/ogg", "ogg")
    assert audio_mod.sniff(b"RIFF\x00\x00\x00\x00WAVEfmt ") == ("audio/wav", "wav")
    assert audio_mod.sniff(b"<html>") is None


def _fake_download(content_by_url):
    def download(source, url, dest, timeout=60):
        data = content_by_url[url]
        with open(dest, "wb") as fh:
            fh.write(data)
        return len(data), "audio/mpeg"
    return download


def test_same_file_from_two_urls_is_stored_once(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    monkeypatch.setattr(audio_mod.config, "MEDIA", tmp_path)
    monkeypatch.setattr(http, "download", _fake_download({"https://a/1.mp3": MP3,
                                                          "https://b/2.mp3": MP3}))
    monkeypatch.setattr(audio_mod, "commons_meta", lambda f, u: {"license": "CC BY-SA 4.0",
                                                                 "artist": "Speaker"})
    a1 = audio_mod.ensure_audio(session, "en", {"url": "https://a/1.mp3", "accent": ["US"]})
    a2 = audio_mod.ensure_audio(session, "en", {"url": "https://b/2.mp3", "accent": ["US"]})
    assert a1.id == a2.id
    assert a1.sha256 == hashlib.sha256(MP3).hexdigest()
    assert a1.path == f"audio/en/{a1.sha256}.mp3"
    assert (tmp_path / a1.path).read_bytes() == MP3
    assert session.query(m.AudioAsset).count() == 1
    assert not list((tmp_path / "audio" / "en").glob(".tmp-*"))  # no temp files left


def test_non_audio_is_rejected(session, tmp_path, monkeypatch):
    monkeypatch.setattr(audio_mod.config, "MEDIA", tmp_path)
    monkeypatch.setattr(http, "download", _fake_download({"https://a/x.mp3": b"<html>nope"}))
    a = audio_mod.ensure_audio(session, "en", {"url": "https://a/x.mp3"})
    assert a.status == "failed" and "不是音檔" in a.error
    assert not any((tmp_path / "audio" / "en").iterdir())


def test_commons_failure_leaves_no_fake_licence_and_retries(session, tmp_path, monkeypatch):
    """#272: a failed Commons lookup marks the credit as pending, never a placeholder;
    the next ensure_audio retries and fills it in."""
    monkeypatch.setattr(audio_mod.config, "MEDIA", tmp_path)
    monkeypatch.setattr(http, "download", _fake_download({"https://a/r.mp3": MP3}))

    def down(source, key, url, timeout=20, retries=1):
        raise http.SourceError("network", "commons is down")
    monkeypatch.setattr(http, "get", down)
    item = {"url": "https://a/r.mp3", "file": "En-us-ooze.ogg"}
    a = audio_mod.ensure_audio(session, "en", item)
    assert a.status == "ready" and a.license is None and a.speaker is None
    assert a.error.startswith(audio_mod.META_PENDING)
    assert a.source_page.endswith("File:En-us-ooze.ogg")
    assert audio_mod.needs_meta(a)

    monkeypatch.setattr(http, "get", lambda *a_, **k: ({"query": {"pages": {"1": {"imageinfo": [{
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:En-us-ooze.ogg",
        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "Artist": {"value": "<a>Speaker</a>"}}}]}}}}, None))
    b = audio_mod.ensure_audio(session, "en", item)
    assert b.id == a.id
    assert (b.license, b.speaker, b.attribution, b.error) == ("CC BY-SA 4.0", "Speaker", "Speaker", None)
    assert not audio_mod.needs_meta(b)


def test_commons_missing_file_is_not_retried(session, tmp_path, monkeypatch):
    monkeypatch.setattr(audio_mod.config, "MEDIA", tmp_path)
    monkeypatch.setattr(http, "download", _fake_download({"https://a/m.mp3": MP3}))
    monkeypatch.setattr(http, "get", lambda *a_, **k: ({"query": {"pages": {"-1": {"missing": ""}}}}, None))
    a = audio_mod.ensure_audio(session, "en", {"url": "https://a/m.mp3", "file": "Gone.ogg"})
    assert a.status == "ready" and a.license is None
    assert a.error == "Commons 查無此檔的授權資料"   # no pending prefix: not retried on every build


def test_refresh_replaces_old_placeholder():
    a = m.AudioAsset(language="en", source="kaikki", status="ready", license="Wikimedia Commons（依檔案授權）",
                     source_url="https://upload.wikimedia.org/wikipedia/commons/transcoded/f/f4/En-us-ooze.ogg/En-us-ooze.ogg.mp3")
    assert audio_mod.needs_meta(a)
    audio_mod.apply_meta(a, {"page": "p", "error": "x", "retry": True})
    assert a.license is None and a.error == audio_mod.META_PENDING + "x"
