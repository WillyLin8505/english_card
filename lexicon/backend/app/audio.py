"""Word audio: download to a temp file, check the MIME by magic bytes,
hash (SHA-256), then move atomically to media/audio/{language}/.
One file per hash, shared by every lexeme that uses it."""

from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from . import models as m
from .adapters import http

MAGIC = [(b"ID3", "audio/mpeg", "mp3"), (b"\xff\xfb", "audio/mpeg", "mp3"),
         (b"\xff\xf3", "audio/mpeg", "mp3"), (b"\xff\xf2", "audio/mpeg", "mp3"),
         (b"OggS", "audio/ogg", "ogg"), (b"fLaC", "audio/flac", "flac")]
MAX_BYTES = 5 * 1024 * 1024


def sniff(head: bytes) -> tuple[str, str] | None:
    """(mime, extension) from the first bytes, or None if not audio."""
    for magic, mime, ext in MAGIC:
        if head.startswith(magic):
            return mime, ext
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav", "wav"
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 16):
            h.update(chunk)
    return h.hexdigest()


def audio_info(path: Path) -> dict:
    try:
        import mutagen
        f = mutagen.File(path)
        if f is None or f.info is None:
            return {}
        return {"duration_s": round(getattr(f.info, "length", 0) or 0, 3) or None,
                "sample_rate": getattr(f.info, "sample_rate", None),
                "channels": getattr(f.info, "channels", None)}
    except Exception:  # noqa: BLE001 — metadata is best effort
        return {}


def commons_meta(file_name: str | None, url: str) -> dict:
    """Per-file licence, author and page from the Wikimedia Commons API."""
    if not file_name:
        m_ = re.search(r"/commons/(?:transcoded/)?[0-9a-f]/[0-9a-f]{2}/([^/]+)", url)
        file_name = urllib.parse.unquote(m_.group(1)) if m_ else None
    if not file_name:
        return {}
    api = ("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "titles": f"File:{file_name}", "prop": "imageinfo",
        "iiprop": "extmetadata|url", "format": "json"}))
    try:
        data, _ = http.get("wikimedia", file_name, api, timeout=20, retries=1)
    except http.SourceError:
        return {"page": f"https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(file_name)}"}
    pages = (data or {}).get("query", {}).get("pages", {})
    info = next(iter(pages.values()), {}).get("imageinfo", [{}])[0] if pages else {}
    meta = info.get("extmetadata", {})

    def v(k):
        return re.sub(r"<[^>]+>", "", (meta.get(k) or {}).get("value", "")).strip() or None

    return {"page": info.get("descriptionurl")
            or f"https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(file_name)}",
            "license": v("LicenseShortName"), "license_url": v("LicenseUrl"),
            "artist": v("Artist"), "attribution": v("Attribution") or v("Credit")}


def ensure_audio(s: Session, language: str, item: dict, source: str = "kaikki") -> m.AudioAsset:
    """The audio asset for a resolved audio item, downloading it once."""
    url = item["url"]
    asset = s.execute(select(m.AudioAsset).where(m.AudioAsset.source_url == url)).scalar_one_or_none()
    if asset is not None and asset.status == "ready" and asset.path \
            and (config.MEDIA / asset.path).exists():
        return asset
    if asset is None:
        asset = m.AudioAsset(language=language, source=source, source_url=url)
        s.add(asset)
    accent = (item.get("accent") or [None])[0]
    asset.accent = accent
    folder = config.MEDIA / "audio" / language
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".tmp-{uuid.uuid4().hex}.part"
    try:
        try:
            size, ctype = http.download("wikimedia", url, tmp)
        except http.SourceError:
            if not item.get("fallback_url"):
                raise
            size, ctype = http.download("wikimedia", item["fallback_url"], tmp)
        if size == 0 or size > MAX_BYTES:
            raise ValueError(f"檔案大小異常（{size} bytes）")
        with open(tmp, "rb") as fh:
            kind = sniff(fh.read(16))
        if kind is None:
            raise ValueError(f"不是音檔（Content-Type {ctype}）")
        mime, ext = kind
        digest = sha256_file(tmp)
        same = s.execute(select(m.AudioAsset).where(m.AudioAsset.sha256 == digest,
                                                    m.AudioAsset.id != (asset.id or -1))
                         ).scalar_one_or_none()
        if same is not None:
            tmp.unlink(missing_ok=True)
            if asset.id is not None:
                s.delete(asset)
            else:
                s.expunge(asset)
            s.flush()
            return same
        final = folder / f"{digest}.{ext}"
        os.replace(tmp, final)  # atomic on the same volume
        meta = commons_meta(item.get("file"), url)
        info = audio_info(final)
        asset.mime, asset.size_bytes, asset.sha256 = mime, size, digest
        asset.path = final.relative_to(config.MEDIA).as_posix()
        asset.license = meta.get("license") or "Wikimedia Commons（依檔案授權）"
        asset.attribution = meta.get("attribution") or meta.get("artist")
        asset.speaker = meta.get("artist")
        asset.source_page = meta.get("page")
        asset.duration_s, asset.sample_rate, asset.channels = (
            info.get("duration_s"), info.get("sample_rate"), info.get("channels"))
        asset.status, asset.error = "ready", None
    except (http.SourceError, ValueError, OSError) as e:
        tmp.unlink(missing_ok=True)
        asset.status, asset.error = "failed", str(e)
    s.flush()
    return asset
