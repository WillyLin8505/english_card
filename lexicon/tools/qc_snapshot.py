"""Guard: snapshot quality metrics + golden set for a pack; compare two.

    python lexicon/tools/qc_snapshot.py --pack FILE_OR_URL --out snap.json [--before old.json]
Exit code 1 when --before is given and anything regressed.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
from app import qc  # noqa: E402


def load(src: str) -> dict:
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=600) as r:
            return json.load(r)
    return json.loads(Path(src).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--before")
    a = ap.parse_args()
    snap = qc.snapshot(load(a.pack))
    Path(a.out).write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"metrics": snap["metrics"], "golden": snap["golden"]["rates"]}, ensure_ascii=False, indent=1))
    if a.before:
        bad = qc.compare(json.loads(Path(a.before).read_text(encoding="utf-8")), snap)
        print("REGRESSIONS:" if bad else "no regressions", *bad, sep="\n  ")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()