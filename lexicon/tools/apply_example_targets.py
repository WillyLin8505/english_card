"""Apply the per-level example targets to stored values (問題回報 #21).

Since 2026-10-14 an A1/A2 headword needs example sentences for A1–B2 only
(pipeline.expected_slots). Values resolved before keep C1/C2 in their
missing levels and stay 「缺漏」; this drops those levels from `missing` and
marks a value complete when nothing else is missing. Sentences are not
touched, nothing is fetched and no AI is called. A snapshot is written
first; --restore puts it back.

    python tools/apply_example_targets.py --dry-run
    python tools/apply_example_targets.py
    python tools/apply_example_targets.py --restore raw-data/snapshots/<file>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))

from sqlalchemy import select  # noqa: E402

from app import db, models as m  # noqa: E402
from app.adapters import Context  # noqa: E402
from app.pipeline import expected_slots  # noqa: E402

SNAPSHOTS = HOME / "raw-data" / "snapshots"
UNFINISHED = {"short", "partial", "missing"}


def run(target: str, dry_run: bool) -> None:
    with db.SessionLocal() as s:
        snapshot, changes = [], Counter()
        values = s.execute(select(m.FieldValue).where(
            m.FieldValue.target_language == target,
            m.FieldValue.field == "example_sentences",
            m.FieldValue.status.in_(sorted(UNFINISHED)))).scalars().all()
        for fv in values:
            ctx = Context(target, fv.native_language, fv.lemma, fv.lemma)
            for row in s.execute(select(m.FieldValue).where(
                    m.FieldValue.target_language == target, m.FieldValue.lemma == fv.lemma,
                    m.FieldValue.field == "cefr")).scalars():
                ctx.resolved["cefr"] = row.items
            wanted = expected_slots("example_sentences", ctx)
            missing = [x for x in (fv.missing or []) if x in wanted]
            if missing == list(fv.missing or []):
                continue
            status = fv.status if missing else "complete"
            snapshot.append({"id": fv.id, "lemma": fv.lemma, "status": fv.status,
                             "missing": fv.missing})
            changes[f"{fv.status}→{status}"] += 1
            if not dry_run:
                fv.missing, fv.status = missing, status
        if not dry_run and snapshot:
            SNAPSHOTS.mkdir(parents=True, exist_ok=True)
            path = SNAPSHOTS / f"example_targets_{datetime.now():%Y%m%d-%H%M%S}.json"
            path.write_text(json.dumps({"target": target, "values": snapshot},
                                       ensure_ascii=False), encoding="utf-8")
            s.commit()
            print(f"snapshot: {path}")
        print(f"{len(snapshot)} values {'would change' if dry_run else 'changed'}: "
              f"{dict(changes)}")


def restore(path: Path) -> None:
    saved = json.loads(path.read_text(encoding="utf-8"))
    with db.SessionLocal() as s:
        for v in saved["values"]:
            fv = s.get(m.FieldValue, v["id"])
            if fv is not None:
                fv.status, fv.missing = v["status"], v["missing"]
        s.commit()
    print(f"restored {len(saved['values'])} values")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", default="en")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", type=Path)
    args = ap.parse_args()
    if args.restore:
        restore(args.restore)
    else:
        run(args.target, args.dry_run)


if __name__ == "__main__":
    main()
