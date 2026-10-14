"""Claim the local GPU for quality work (decision 5).

The tags worker yields while `.runtime/qc_gpu_claim` is fresher than 10 min.
"""
from __future__ import annotations
import time
from pathlib import Path
CLAIM = Path(__file__).resolve().parents[3] / ".runtime" / "qc_gpu_claim"

def hold():
    CLAIM.parent.mkdir(parents=True, exist_ok=True)
    CLAIM.write_text(str(time.time()), encoding="utf-8")

def release():
    try: CLAIM.unlink()
    except OSError: pass
