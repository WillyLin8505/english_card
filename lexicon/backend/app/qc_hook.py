"""Automatic qc triggers (import / tagging / pack), debounced and detached.

`trigger(kind)` starts `qc run --trigger kind` in the background at most once
per QC_DEBOUNCE_S (default 30 min) and never from inside a qc run. A pack
build only records metrics (no fixes), so serving never waits on fixes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STAMP = ROOT / ".runtime" / "qc_last_trigger"
DEBOUNCE_S = int(os.environ.get("QC_DEBOUNCE_S", "1800"))


def trigger(kind: str) -> bool:
    if os.environ.get("QC_RUNNING") or os.environ.get("QC_DISABLE") or "pytest" in sys.modules:
        return False
    try:
        if time.time() - STAMP.stat().st_mtime < DEBOUNCE_S:
            return False
    except OSError:
        pass
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(kind, encoding="utf-8")
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([sys.executable, str(ROOT / "lexicon" / "tools" / "qc.py"), "run", "--trigger", kind],
                     cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, env={**os.environ, "QC_RUNNING": "1"})
    return True


def record_pack_metrics(pack: dict) -> None:
    """Pack trigger: validators + metrics only, written for the dashboard."""
    if "pytest" in sys.modules:
        return
    try:
        from . import qc
        out = ROOT / "lexicon" / "exports" / "quality" / "qc"
        out.mkdir(parents=True, exist_ok=True)
        snap = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "metrics": qc.metrics(pack)}
        (out / "pack-latest.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass  # metrics must never break serving the pack