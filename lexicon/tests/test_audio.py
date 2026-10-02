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
