"""Fill in Commons credit (licence / speaker / attribution) for ready audio files
whose lookup failed at download time or that still carry the old placeholder
licence "Wikimedia Commons（依檔案授權）" (issue #272).

  python lexicon/tools/audio_meta_backfill.py                 # count only
  python lexicon/tools/audio_meta_backfill.py --apply --backup lexicon/logs/agents/x.json [--limit N]

--apply writes the affected rows' old values to --backup first.  Restore with
  python lexicon/tools/audio_meta_backfill.py --restore lexicon/logs/agents/x.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import or_, select  # noqa: E402

from app import db  # noqa: E402
from app import models as m  # noqa: E402
from app.audio import META_PENDING, needs_meta, refresh_meta  # noqa: E402

COLS = ("license", "speaker", "attribution", "source_page", "error")


def candidates(s):
    rows = s.execute(select(m.AudioAsset).where(m.AudioAsset.status == "ready", or_(
        m.AudioAsset.license.is_(None), m.AudioAsset.license.like("Wikimedia Commons%"),
        m.AudioAsset.error.like(META_PENDING + "%"))).order_by(m.AudioAsset.id)).scalars().all()
    return [a for a in rows if needs_meta(a)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    ap.add_argument("--restore")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    with db.SessionLocal() as s:
        if args.restore:
            rows = json.loads(Path(args.restore).read_text(encoding="utf-8"))
            for r in rows:
                a = s.get(m.AudioAsset, r["id"])
                for c in COLS:
                    setattr(a, c, r[c])
            s.commit()
            print("restored", len(rows))
            return 0
        rows = candidates(s)
        if args.limit:
            rows = rows[:args.limit]
        print("candidates", len(rows))
        if not args.apply:
            return 0
        if not args.backup:
            ap.error("--apply needs --backup")
        Path(args.backup).write_text(json.dumps(
            [{"id": a.id, **{c: getattr(a, c) for c in COLS}} for a in rows],
            ensure_ascii=False, indent=1), encoding="utf-8")
        stats = {"fixed": 0, "pending": 0, "no_meta": 0}
        for a in rows:
            if refresh_meta(a):
                stats["fixed"] += 1
            elif (a.error or "").startswith(META_PENDING):
                stats["pending"] += 1
            else:
                stats["no_meta"] += 1
        s.commit()
        print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
