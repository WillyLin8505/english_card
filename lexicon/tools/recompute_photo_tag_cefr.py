"""Re-run images.classify_tag_cefr over every stored photo label (tags and
dropped_tags) and update cefr/cefrSource/cefrLemma/cefrCoreWord in place.

Why: a bug in images.py's _list_level (問題回報 #198) let a wrong part of
speech from the tagger (furniture tagged "adjective", number "adverb", ...)
fall through to a letter-split guess instead of the list's real, easy level
for that word. The fix only changes new labels going forward; this tool
lets the owner re-grade labels already stored in the database. It never
calls the vision model, never adds or removes a label, and never moves a
label between kept and dropped — it only rewrites the level fields, so it
is safe to re-run (idempotent: a second run changes nothing).

It does NOT re-run the "up to 3-4 per CEFR band" selection in images.tag_asset
(_select_cefr_tags): if a label's band changes, an image that was complete
may need that recomputed too. This tool reports how many images would
change band membership so the owner can decide whether to also re-tag those
with lexicon/tools/resolve_unclassified_image_tags.py or a full re-tag.

Usage:
  python lexicon/tools/recompute_photo_tag_cefr.py             # preview (dry-run)
  python lexicon/tools/recompute_photo_tag_cefr.py --apply     # write changes
  python lexicon/tools/recompute_photo_tag_cefr.py --limit 50  # smaller preview
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from sqlalchemy import select  # noqa: E402
from app import db, images, models as m  # noqa: E402

FIELDS = ('cefr', 'cefrSource', 'cefrLemma', 'cefrCoreWord')


def recompute_list(s, tag_list: list[dict] | None) -> tuple[list[dict], int]:
    out, changed = [], 0
    for original in tag_list or []:
        resolved = images.classify_tag_cefr(s, original)
        if any(resolved.get(f) != original.get(f) for f in FIELDS):
            changed += 1
        out.append(resolved)
    return out, changed


def process_asset(s, asset: m.ImageAsset, stats: Counter) -> None:
    before_bands = images.cefr_counts(asset.tags)
    new_tags, changed_tags = recompute_list(s, asset.tags)
    new_dropped, changed_dropped = recompute_list(s, asset.dropped_tags)
    stats['labels_changed'] += changed_tags + changed_dropped
    stats['labels_seen'] += len(asset.tags or []) + len(asset.dropped_tags or [])
    if changed_tags or changed_dropped:
        stats['assets_changed'] += 1
        after_bands = images.cefr_counts(new_tags)
        if before_bands != after_bands:
            stats['assets_band_shifted'] += 1
        asset.tags = new_tags
        asset.dropped_tags = new_dropped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    stats = Counter()
    with db.SessionLocal() as s:
        query = select(m.ImageAsset).order_by(m.ImageAsset.id)
        if args.limit:
            query = query.limit(args.limit)
        for asset in s.scalars(query):
            process_asset(s, asset, stats)
            stats['assets_seen'] += 1
        if args.apply:
            s.commit()
        else:
            s.rollback()
    print(('APPLIED' if args.apply else 'PREVIEW'), dict(sorted(stats.items())))


if __name__ == '__main__':
    main()
