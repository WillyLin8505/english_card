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


# asset.error prefix for a ready file whose Commons credit could not be fetched
# (network, breaker, timeout).  ensure_audio retries these; never a fake licence.
META_PENDING = "授權待補："


def commons_meta(file_name: str | None, url: str) -> dict:
    """Per-file licence, author and page from the Wikimedia Commons API.
    On failure the dict has "error" and "retry" (True when worth trying again)."""
    if not file_name:
        m_ = re.search(r"/commons/(?:transcoded/)?[0-9a-f]/[0-9a-f]{2}/([^/]+)", url)
        file_name = urllib.parse.unquote(m_.group(1)) if m_ else None
    if not file_name:
        return {"error": "不是 Commons 檔案，無法查授權", "retry": False}
    page = f"https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(file_name)}"
    api = ("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "titles": f"File:{file_name}", "prop": "imageinfo",
        "iiprop": "extmetadata|url", "format": "json"}))
    try:
        data, _ = http.get("wikimedia_commons", file_name, api, timeout=20, retries=1)
    except http.SourceError as e:
        return {"page": page, "error": f"Commons 查詢失敗（{e}）", "retry": True}
    pages = (data or {}).get("query", {}).get("pages", {})
    info = next(iter(pages.values()), {}).get("imageinfo", [{}])[0] if pages else {}
    meta = info.get("extmetadata", {})
    if not meta:
        return {"page": info.get("descriptionurl") or page,
                "error": "Commons 查無此檔的授權資料", "retry": False}

    def v(k):
        return re.sub(r"<[^>]+>", "", (meta.get(k) or {}).get("value", "")).strip() or None

    return {"page": info.get("descriptionurl")
            or f"https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(file_name)}",
            "license": v("LicenseShortName"), "license_url": v("LicenseUrl"),
            "artist": v("Artist"), "attribution": v("Attribution") or v("Credit")}


def needs_meta(asset: m.AudioAsset) -> bool:
    """A ready file whose credit is still to be fetched (or an old placeholder)."""
    return asset.status == "ready" and (
        (asset.error or "").startswith(META_PENDING)
        or not asset.license or asset.license.startswith("Wikimedia Commons"))


def apply_meta(asset: m.AudioAsset, meta: dict) -> None:
    """Write Commons credit onto the asset; keep what we had when the lookup fails."""
    asset.license = meta.get("license") or (
        None if (asset.license or "").startswith("Wikimedia Commons") else asset.license)
    asset.attribution = meta.get("attribution") or meta.get("artist") or asset.attribution
    asset.speaker = meta.get("artist") or asset.speaker
    asset.source_page = meta.get("page") or asset.source_page
    if meta.get("error"):
        asset.error = (META_PENDING if meta.get("retry") else "") + meta["error"]
    else:
        asset.error = None


def lookup_meta(asset: m.AudioAsset, file_name: str | None = None) -> dict:
    """The Commons credit for one asset (network only, nothing written)."""
    if not file_name and asset.source_page and "File:" in asset.source_page:
        file_name = urllib.parse.unquote(asset.source_page.split("File:", 1)[1])
    meta = commons_meta(file_name, asset.source_url)
    if meta.get("error") and file_name:  # stored page name may be stale: try the URL
        by_url = commons_meta(None, asset.source_url)
        if not by_url.get("error"):
            meta = by_url
    return meta


def refresh_meta(asset: m.AudioAsset, file_name: str | None = None) -> bool:
    """Retry the Commons credit for one asset. True when the licence is now known."""
    meta = lookup_meta(asset, file_name)
    apply_meta(asset, meta)
    return not meta.get("error") and bool(asset.license)


def _ready(asset: m.AudioAsset | None) -> bool:
    return asset is not None and asset.status == "ready" and bool(asset.path) \
        and (config.MEDIA / asset.path).exists()


def _by_url(s: Session, url: str) -> m.AudioAsset | None:
    return s.execute(select(m.AudioAsset).where(m.AudioAsset.source_url == url)).scalar_one_or_none()


def fetch_audio(s: Session, language: str, item: dict) -> dict:
    """The network half of ensure_audio: download, check, hash and store the
    file, then look up its Commons credit.  Writes no rows (only reads), so it
    can run before a caller takes a lock (問題回報 #330).
    {"error": …} on failure, else the file's facts for _store."""
    url = item["url"]
    folder = config.MEDIA / "audio" / language
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".tmp-{uuid.uuid4().hex}.part"
    try:
        try:
            size, ctype = http.download("wikimedia_commons", url, tmp)
        except http.SourceError:
            if not item.get("fallback_url"):
                raise
            size, ctype = http.download("wikimedia_commons", item["fallback_url"], tmp)
        if size == 0 or size > MAX_BYTES:
            raise ValueError(f"檔案大小異常（{size} bytes）")
        with open(tmp, "rb") as fh:
            kind = sniff(fh.read(16))
        if kind is None:
            raise ValueError(f"不是音檔（Content-Type {ctype}）")
        mime, ext = kind
        digest = sha256_file(tmp)
        same = s.execute(select(m.AudioAsset.id).where(m.AudioAsset.sha256 == digest,
                                                       m.AudioAsset.source_url != url)).first()
        if same is not None:  # stored once already: no file, no credit lookup
            tmp.unlink(missing_ok=True)
            return {"sha256": digest}
        final = folder / f"{digest}.{ext}"
        os.replace(tmp, final)  # atomic on the same volume
        return {"sha256": digest, "mime": mime, "size": size,
                "path": final.relative_to(config.MEDIA).as_posix(),
                "info": audio_info(final), "meta": commons_meta(item.get("file"), url)}
    except (http.SourceError, ValueError, OSError) as e:
        tmp.unlink(missing_ok=True)
        return {"error": str(e)}


def prefetch_audio(s: Session, language: str, items: list[dict]) -> dict[str, dict]:
    """Network work for these audio items, done ahead (url → fetch_audio /
    {"credit": meta}).  Hand the result to ensure_audio(fetched=…) so the
    write phase makes no network calls."""
    out: dict[str, dict] = {}
    for it in items:
        url = it.get("url")
        if not url or it.get("tts") or url in out:
            continue
        asset = _by_url(s, url)
        if _ready(asset):
            if (asset.error or "").startswith(META_PENDING):
                out[url] = {"credit": lookup_meta(asset, it.get("file"))}
            continue
        out[url] = fetch_audio(s, language, it)
    return out


def ensure_audio(s: Session, language: str, item: dict, source: str = "kaikki",
                 fetched: dict[str, dict] | None = None) -> m.AudioAsset:
    """The audio asset for a resolved audio item, downloading it once.
    With `fetched` (prefetch_audio) the download is already done."""
    url = item["url"]
    got = (fetched or {}).get(url)
    asset = _by_url(s, url)
    if _ready(asset):
        if (asset.error or "").startswith(META_PENDING):
            if got and "credit" in got:
                apply_meta(asset, got["credit"])
            else:
                refresh_meta(asset, item.get("file"))
            s.flush()
        return asset
    if got is None or "credit" in got:
        got = fetch_audio(s, language, item)
    if asset is None:
        asset = m.AudioAsset(language=language, source=source, source_url=url)
        s.add(asset)
    asset.accent = (item.get("accent") or [None])[0]
    if "error" in got:
        asset.status, asset.error = "failed", got["error"]
        s.flush()
        return asset
    same = s.execute(select(m.AudioAsset).where(m.AudioAsset.sha256 == got["sha256"],
                                                m.AudioAsset.id != (asset.id or -1))
                     ).scalar_one_or_none()
    if same is not None:
        if asset.id is not None:
            s.delete(asset)
        else:
            s.expunge(asset)
        s.flush()
        return same
    if "path" not in got:  # its twin was gone by now: fetch the file after all
        got = fetch_audio(s, language, item)
        if "error" in got or "path" not in got:
            asset.status, asset.error = "failed", got.get("error") or "重複音檔已不存在"
            s.flush()
            return asset
    info = got["info"]
    asset.mime, asset.size_bytes, asset.sha256 = got["mime"], got["size"], got["sha256"]
    asset.path = got["path"]
    asset.license = asset.attribution = asset.speaker = asset.source_page = None
    asset.duration_s, asset.sample_rate, asset.channels = (
        info.get("duration_s"), info.get("sample_rate"), info.get("channels"))
    asset.status = "ready"
    apply_meta(asset, got["meta"])
    s.flush()
    return asset
