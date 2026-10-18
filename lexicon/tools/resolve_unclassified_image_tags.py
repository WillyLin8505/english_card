"""Resolve image-label CEFR by forms/phrases and quarantine unresolved labels.

This intentionally implements cleanup steps 2-4 only. A single-word exact
lexeme match is left untouched unless it is needed as a component of a phrase.

Usage:
  python tools/resolve_unclassified_image_tags.py          # preview
  python tools/resolve_unclassified_image_tags.py --apply  # commit
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


def clean_asset(s, asset: m.ImageAsset) -> Counter:
    stats = Counter()
    kept, quarantined = [], list(asset.dropped_tags or [])
    for original in asset.tags or []:
        if images.tag_level(original):
            kept.append(original)
            continue
        resolved = images.classify_tag_cefr(s, original, include_exact=False)
        if images.tag_level(resolved):
            kept.append(resolved)
            stats[f"resolved_{resolved.get('cefrSource', 'unknown')}"] += 1
        else:
            item = dict(original)
            item['dropReason'] = '無可靠 CEFR 等級，等待人工審核'
            item['reviewStatus'] = 'pending_cefr'
            quarantined.append(item)
            stats['quarantined'] += 1

    # Add level metadata to rejected labels for reviewers, but never promote
    # them: their visual score or other validation already failed.
    reviewed_dropped = []
    for original in quarantined:
        if images.tag_level(original):
            reviewed_dropped.append(original)
            continue
        resolved = images.classify_tag_cefr(s, original, include_exact=False)
        if images.tag_level(resolved):
            reviewed_dropped.append(resolved)
            stats[f"dropped_{resolved.get('cefrSource', 'unknown')}"] += 1
        else:
            item = dict(resolved)
            previous_reason = item.get('dropReason')
            if previous_reason and previous_reason != '無可靠 CEFR 等級，等待人工審核':
                item['validationReason'] = previous_reason
            item['dropReason'] = '無可靠 CEFR 等級，等待人工審核'
            item['reviewStatus'] = 'pending_cefr'
            reviewed_dropped.append(item)

    # A formal image contains only classified labels. Completion still requires
    # three verified labels in every band.
    kept, overflow = images._select_cefr_tags(kept)
    for item in overflow:
        item.setdefault('dropReason', '該等級已滿 3 個')
    asset.tags = kept
    asset.dropped_tags = [*reviewed_dropped, *overflow]
    asset.tag_status = 'done' if images.cefr_complete(kept) else 'pending'
    stats['assets'] += 1
    if asset.tag_status == 'pending':
        stats['assets_pending'] += 1
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    total = Counter()
    with db.SessionLocal() as s:
        query = select(m.ImageAsset).where(m.ImageAsset.status == 'ready').order_by(m.ImageAsset.id)
        if args.limit:
            query = query.limit(args.limit)
        for asset in s.scalars(query):
            total.update(clean_asset(s, asset))
        if args.apply:
            s.commit()
        else:
            s.rollback()
    print(('APPLIED' if args.apply else 'PREVIEW'), dict(sorted(total.items())))


if __name__ == '__main__':
    main()
