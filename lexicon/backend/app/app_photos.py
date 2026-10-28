"""手機上傳的照片 (card #724, 問題回報 #853): photos taken in a developer build of the App
(owner decision 2026-10-28: only the owner's own dev phone uploads, automatically) are kept
here so 後台 can see the picture next to its labels. No database table: one JPEG plus one
JSON sidecar per photo under MEDIA/app_photos, newest upload first.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field as PField

from . import config

MAX_BYTES = 8 * 1024 * 1024
JPEG, PNG = b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"
SAFE_ID = re.compile(r"^[0-9a-f]{16}$")


def folder():
    path = config.MEDIA / "app_photos"
    path.mkdir(parents=True, exist_ok=True)
    return path


class PhotoBody(BaseModel):
    photo_id: str = PField(max_length=80)
    image_b64: str
    title: str | None = PField(default=None, max_length=200)
    device: str | None = PField(default=None, max_length=80)
    language: str | None = PField(default=None, max_length=12)
    labels: list[dict] = PField(default_factory=list, max_length=60)


def _clean_label(label: dict) -> dict:
    return {k: (str(label[k])[:80] if k != "point" else label[k])
            for k in ("word", "pos", "cefr", "meaning", "point") if label.get(k) is not None}


def store(body: PhotoBody) -> dict:
    try:
        data = base64.b64decode(body.image_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "image_b64 不是有效的 base64")
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "照片不能超過 8 MB")
    if not (data.startswith(JPEG) or data.startswith(PNG)):
        raise HTTPException(415, "只收 JPEG 或 PNG")
    # One entry per phone photo: a re-upload (new labels after a retag) replaces the sidecar.
    key = hashlib.sha256(f"{body.device or ''}|{body.photo_id}".encode()).hexdigest()[:16]
    ext = "jpg" if data.startswith(JPEG) else "png"
    root = folder()
    (root / f"{key}.{ext}").write_bytes(data)
    meta_path = root / f"{key}.json"
    first = None
    if meta_path.exists():
        first = json.loads(meta_path.read_text(encoding="utf-8")).get("first_uploaded_at")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {"id": key, "photo_id": body.photo_id, "title": body.title, "device": body.device,
            "language": body.language, "ext": ext, "size_bytes": len(data),
            "labels": [_clean_label(x) for x in body.labels if isinstance(x, dict) and x.get("word")],
            "first_uploaded_at": first or now, "uploaded_at": now}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def listing(limit: int = 200) -> list[dict]:
    rows = []
    for p in folder().glob("*.json"):
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    rows.sort(key=lambda r: r.get("uploaded_at") or "", reverse=True)
    return rows[:limit]


def register(app, auth):
    @app.post("/app-photos", dependencies=[auth], status_code=201)
    def upload(body: PhotoBody):
        meta = store(body)
        return {k: meta[k] for k in ("id", "labels", "uploaded_at")}

    @app.get("/app-photos", dependencies=[auth])
    def list_photos(limit: int = 200):
        rows = listing(max(1, min(limit, 1000)))
        return {"total": len(list(folder().glob("*.json"))), "photos": rows}

    @app.get("/app-photos/{key}/file")
    def photo_file(key: str):
        if not SAFE_ID.match(key):
            raise HTTPException(404, "找不到照片")
        for ext, mime in (("jpg", "image/jpeg"), ("png", "image/png")):
            path = folder() / f"{key}.{ext}"
            if path.is_file():
                return FileResponse(path, media_type=mime)
        raise HTTPException(404, "找不到照片")
