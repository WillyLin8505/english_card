"""Source snapshots: download a versioned copy into raw-data/, record its
URL, SHA-256, size, licence and time, import it, and choose which one is
active (回復 = activate an older one). Run by the worker."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import catalog, config
from . import models as m
from .adapters import ADAPTERS


class SnapshotError(ValueError):
    pass


def request(s: Session, source: str, language: str) -> m.SourceSnapshot:
    if source not in catalog.SOURCES:
        raise SnapshotError(f"沒有來源 {source}")
    if not catalog.SOURCES[source].implemented:
        raise SnapshotError(f"{catalog.SOURCES[source].name} 的 adapter 尚未實作")
    snap = m.SourceSnapshot(source=source, language=language or "", status="queued",
                            license=catalog.SOURCES[source].license, details={})
    s.add(snap)
    s.flush()
    return snap


def claim(s: Session) -> m.SourceSnapshot | None:
    snap = s.execute(select(m.SourceSnapshot).where(m.SourceSnapshot.status == "queued")
                     .order_by(m.SourceSnapshot.id).limit(1).with_for_update(skip_locked=True)
                     ).scalar_one_or_none()
    if snap is not None:
        snap.status = "downloading"
        s.flush()
    return snap


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def run(s: Session, snap_id: int) -> m.SourceSnapshot:
    snap = s.get(m.SourceSnapshot, snap_id)
    adapter = ADAPTERS[snap.source]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = config.RAW_DATA / snap.source / (snap.language.replace(":", "-") or "all") / stamp
    folder.mkdir(parents=True, exist_ok=True)
    try:
        info = adapter.download_snapshot(snap.language, folder)
        files = [Path(f) for f in info.pop("files", [])]
        hashes = {f.name: {"sha256": _sha256(f), "bytes": f.stat().st_size}
                  for f in files if f.exists()}
        snap.version = str(info.get("version") or "")[:64]
        snap.url = info.get("url") or ""
        snap.path = str(info.get("path") or folder)
        snap.details = {**(info.get("details") or {}), "files": hashes}
        if hashes:
            combined = hashlib.sha256("".join(v["sha256"] for v in hashes.values()).encode())
            snap.sha256 = next(iter(hashes.values()))["sha256"] if len(hashes) == 1 \
                else combined.hexdigest()
            snap.size_bytes = sum(v["bytes"] for v in hashes.values())
        rows = info.get("row_count")
        if hasattr(adapter, "import_snapshot"):
            s.flush()
            rows = adapter.import_snapshot(s, snap.id, files)
        snap.row_count = rows
        snap.retrieved_at = datetime.now(timezone.utc)
        snap.status, snap.error = "ready", None
        activate(s, snap.id)
    except Exception as e:  # noqa: BLE001
        s.rollback()
        snap = s.get(m.SourceSnapshot, snap_id)
        snap.status, snap.error = "failed", f"{type(e).__name__}: {e}"[:2000]
    s.flush()
    return snap


def activate(s: Session, snap_id: int) -> m.SourceSnapshot:
    snap = s.get(m.SourceSnapshot, snap_id)
    if snap is None or snap.status != "ready":
        raise SnapshotError("只能啟用已完成的快照")
    s.execute(update(m.SourceSnapshot).where(m.SourceSnapshot.source == snap.source,
                                             m.SourceSnapshot.language == snap.language)
              .values(active=False))
    snap.active = True
    s.flush()
    return snap


def verify(s: Session, snap_id: int) -> dict:
    """Re-hash the files on disk and compare with what was recorded."""
    snap = s.get(m.SourceSnapshot, snap_id)
    files = (snap.details or {}).get("files", {})
    base = Path(snap.path or "")
    out = []
    for name, rec in files.items():
        p = base / name if base.is_dir() else base
        if not p.exists():
            out.append({"file": name, "ok": False, "reason": "檔案不見了"})
            continue
        got = _sha256(p)
        out.append({"file": name, "ok": got == rec["sha256"], "sha256": got,
                    "expected": rec["sha256"]})
    return {"id": snap.id, "ok": all(x["ok"] for x in out) if out else None, "files": out}


def compare(s: Session, a_id: int, b_id: int) -> dict:
    a, b = s.get(m.SourceSnapshot, a_id), s.get(m.SourceSnapshot, b_id)
    if a is None or b is None:
        raise SnapshotError("找不到快照")
    fa, fb = (a.details or {}).get("files", {}), (b.details or {}).get("files", {})
    return {
        "a": snapshot_dict(a), "b": snapshot_dict(b),
        "same_source": a.source == b.source and a.language == b.language,
        "rows_delta": (b.row_count or 0) - (a.row_count or 0),
        "bytes_delta": (b.size_bytes or 0) - (a.size_bytes or 0),
        "files": [{"file": k, "a": fa.get(k, {}).get("sha256"), "b": fb.get(k, {}).get("sha256"),
                   "changed": fa.get(k, {}).get("sha256") != fb.get(k, {}).get("sha256")}
                  for k in sorted(set(fa) | set(fb))],
    }


def snapshot_dict(r: m.SourceSnapshot) -> dict:
    src = catalog.SOURCES.get(r.source)
    return {"id": r.id, "source": r.source, "source_name": src.name if src else r.source,
            "language": r.language, "version": r.version, "url": r.url, "sha256": r.sha256,
            "size_bytes": r.size_bytes, "path": r.path, "license": r.license, "status": r.status,
            "active": r.active, "row_count": r.row_count, "details": r.details, "error": r.error,
            "retrieved_at": r.retrieved_at, "created_at": r.created_at}
