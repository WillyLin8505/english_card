"""Enrich lexicon ImageAsset tags with ~3 concrete labels per CEFR band.

Uses local Qwen via the tagging API:
  POST http://127.0.0.1:8765/tag?mode=cefr&lang=en&per_level=3

Merges into existing asset.tags (does not wipe prior labels). By default defers the second /score vision pass for grounded CEFR labels (provisional TAG_PASS; use --score to force). Keeps --skip-enriched. Then share() so approved catalog photos pick up new dictionary bindings.

Usage (from repo root, lexicon venv / deps available):
  python lexicon/tools/enrich_cefr_tags.py --limit 20 --catalog-only
  python lexicon/tools/enrich_cefr_tags.py --asset-id 1
  python lexicon/tools/enrich_cefr_tags.py --limit 50 --catalog-only --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))

from app import config, db, models as m  # noqa: E402
from app.images import (  # noqa: E402
    TAG_PASS,
    TAGS_MAX,
    TaggerUnavailable,
    score_tags,
    share,
    _settle,
)
from sqlalchemy import select, text  # noqa: E402

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


def _cefr_for_word(s, word: str) -> str | None:
    w = word.strip().lower()
    lx = s.scalars(
        select(m.Lexeme)
        .where(
            m.Lexeme.normalized == w,
            m.Lexeme.language == "en",
            m.Lexeme.status == "full",
        )
        .order_by(m.Lexeme.id)
    ).first()
    return (lx.cefr or None) if lx else None


def band_counts(s, tags: list[dict]) -> dict[str, int]:
    c = Counter({lv: 0 for lv in LEVELS})
    for t in tags or []:
        word = str(t.get("word", "")).strip()
        if not word:
            continue
        # Prefer lexicon CEFR; fall back to model band stored on the tag.
        level = _cefr_for_word(s, word) or str(t.get("cefr") or t.get("modelLevel") or "").upper()
        if level in c:
            c[level] += 1
    return dict(c)


def catalog_asset_ids(s, limit: int | None = None) -> list[int]:
    q = text(
        """
        SELECT a.id
        FROM image_assets a
        WHERE a.status = 'ready'
          AND a.path IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM sense_images si
            WHERE si.image_asset_id = a.id AND si.review_status = 'approved'
          )
        ORDER BY (
            SELECT count(*) FROM sense_images si
            WHERE si.image_asset_id = a.id AND si.review_status = 'approved'
        ) ASC, a.id
        """
        + (" LIMIT :lim" if limit else "")
    )
    params = {"lim": limit} if limit else {}
    return [row[0] for row in s.execute(q, params).all()]


def ask_cefr(data: bytes, mime: str | None, exclude: list[str], per_level: int) -> list[dict]:
    qs = urllib.parse.urlencode(
        {
            "mode": "cefr",
            "lang": "en",
            "native": "zh-TW",
            "per_level": str(per_level),
            **({"exclude": ",".join(exclude[:60])} if exclude else {}),
        }
    )
    req = urllib.request.Request(
        config.AI_URL.rstrip("/") + "/tag?" + qs,
        data=data,
        method="POST",
        headers={
            "X-API-Key": config.AI_KEY,
            "Content-Type": mime or "image/jpeg",
        },
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        out = json.loads(resp.read())
    return list(out.get("candidates") or [])


def enrich_asset(s, asset_id: int, per_level: int = 3, dry_run: bool = False,
                 defer_score: bool = True) -> dict:
    asset = s.get(m.ImageAsset, asset_id)
    if not asset or asset.status != "ready" or not asset.path:
        raise ValueError(f"asset {asset_id} not ready")
    path = config.MEDIA / asset.path
    if not path.is_file():
        raise ValueError(f"missing file {path}")
    data = path.read_bytes()
    existing = list(asset.tags or [])
    before = band_counts(s, existing)
    seen = [str(t.get("word", "")).strip().lower() for t in existing if str(t.get("word", "")).strip()]

    try:
        raw = ask_cefr(data, asset.mime, seen, per_level)
        if not raw and seen:
            # Retry once without exclude so CEFR bands can still fill gaps
            # when the model only echoed existing labels.
            raw = ask_cefr(data, asset.mime, [], per_level)
    except urllib.error.HTTPError as e:
        raise ValueError(f"tagger HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise TaggerUnavailable(str(e)) from e

    new = []
    for c in raw:
        word = str(c.get("word", "")).strip()
        if not word or word.lower() in {w.lower() for w in seen}:
            continue
        seen.append(word)
        tag = {
            "word": word,
            "pos": c.get("pos") or "noun",
            "point": c.get("point"),
            "box": c.get("box"),
        }
        model_cefr = str(c.get("cefr") or c.get("modelLevel") or "").upper()
        if model_cefr in LEVELS:
            tag["cefr"] = model_cefr
            tag["modelLevel"] = model_cefr
        new.append(tag)

    if new:
        # Safe skip/defer: already-scored tags untouched; defer_score avoids a
        # second VL pass when CEFR bands + point/box ground the label. Disk
        # cache on /tag and /score remains authoritative when --score is used.
        score_tags(data, new, asset.mime, defer=defer_score)
    passed_new = [t for t in new if (t.get("score") or 0) >= TAG_PASS]
    dropped_new = [t for t in new if (t.get("score") or 0) < TAG_PASS]

    # Keep existing tags; append passing newcomers up to TAGS_MAX.
    merged = []
    for t in existing:
        item = dict(t)
        if item.get("score") is None:
            item["score"] = float(TAG_PASS)  # already on the picture; keep
        merged.append(item)
    for t in sorted(passed_new, key=lambda x: -(x.get("score") or 0)):
        if len(merged) >= TAGS_MAX:
            break
        if str(t.get("word", "")).lower() in {
            str(x.get("word", "")).lower() for x in merged
        }:
            continue
        merged.append(t)

    after_preview = band_counts(s, merged)
    result = {
        "asset_id": asset_id,
        "before_n": len(existing),
        "after_n": len(merged),
        "added": len(merged) - len(existing),
        "proposed": len(new),
        "passed_new": len(passed_new),
        "dropped_new": len(dropped_new),
        "before_bands": before,
        "after_bands": after_preview,
        "new_words": [t["word"] for t in passed_new],
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    # Preserve previous dropped_tags and append newly failed ones.
    dropped = list(asset.dropped_tags or []) + dropped_new
    _settle(s, asset, merged, dropped, "cefr-enrich+qwen3-vl", done=True)
    # _settle re-sorts/truncates via TAGS_MAX; ensure cefr fields survive by
    # re-attaching model bands onto the settled tags when words match.
    by_word = {str(t.get("word", "")).lower(): t for t in merged}
    settled = []
    for t in asset.tags or []:
        src = by_word.get(str(t.get("word", "")).lower())
        if src and src.get("cefr") and not t.get("cefr"):
            t = dict(t)
            t["cefr"] = src["cefr"]
            t["modelLevel"] = src.get("modelLevel") or src["cefr"]
        settled.append(t)
    asset.tags = settled
    share(s, asset)
    s.commit()
    result["after_n"] = len(asset.tags or [])
    result["after_bands"] = band_counts(s, asset.tags or [])
    from sqlalchemy import func
    result["approved_bindings"] = s.scalar(
        select(func.count())
        .select_from(m.SenseImage)
        .where(
            m.SenseImage.image_asset_id == asset_id,
            m.SenseImage.review_status == "approved",
        )
    )
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=20, help="max assets to process")
    ap.add_argument("--catalog-only", action="store_true", help="only approved catalog photos")
    ap.add_argument("--asset-id", type=int, action="append", default=[], help="specific asset id(s)")
    ap.add_argument("--per-level", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-enriched", action="store_true",
                    help="skip assets that already have CEFR-band tags (modelLevel/cefr on tags)")
    ap.add_argument("--score", dest="force_score", action="store_true",
                    help="run second /score vision pass (default: defer — provisional TAG_PASS for grounded CEFR tags)")
    ap.add_argument("--report", type=Path, default=ROOT / "Downloads" / "english_card_probe" / "cefr_enrich_report.json")
    args = ap.parse_args()

    # Ensure Downloads probe folder exists when defaulting there.
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        args.report = Path.cwd() / "cefr_enrich_report.json"

    if not config.AI_KEY:
        sys.exit("LEXICON_AI_KEY / tagger key missing in lexicon/.env")

    s = db.SessionLocal()
    try:
        if args.asset_id:
            ids = args.asset_id
        elif args.catalog_only:
            ids = catalog_asset_ids(s, args.limit)
        else:
            ids = [
                a.id
                for a in s.scalars(
                    select(m.ImageAsset)
                    .where(m.ImageAsset.status == "ready", m.ImageAsset.path.is_not(None))
                    .order_by(m.ImageAsset.id)
                    .limit(args.limit)
                ).all()
            ]
        if args.skip_enriched:
            kept = []
            for aid in ids:
                asset = s.get(m.ImageAsset, aid)
                tags = (asset.tags or []) if asset else []
                if any(t.get("modelLevel") or t.get("cefr") for t in tags):
                    continue
                if (asset.tag_model or "").startswith("cefr-enrich"):
                    continue
                kept.append(aid)
            print(f"skip-enriched: {len(ids)} -> {len(kept)}")
            ids = kept
        print(f"enrich targets={len(ids)} dry_run={args.dry_run} per_level={args.per_level} TAGS_MAX={TAGS_MAX} defer_score={not args.force_score}")
        rows = []
        for i, aid in enumerate(ids, 1):
            try:
                row = enrich_asset(s, aid, per_level=args.per_level, dry_run=args.dry_run,
                                   defer_score=not args.force_score)
                rows.append(row)
                print(
                    f"[{i}/{len(ids)}] asset={aid} {row['before_n']}->{row['after_n']} "
                    f"+{row['added']} passed_new={row['passed_new']} "
                    f"bands {row['before_bands']} -> {row['after_bands']}"
                )
            except TaggerUnavailable as e:
                print(f"[{i}/{len(ids)}] asset={aid} TAGGER_UNAVAILABLE: {e}")
                rows.append({"asset_id": aid, "error": "tagger_unavailable", "detail": str(e)})
                break
            except Exception as e:  # noqa: BLE001 — continue batch
                s.rollback()
                print(f"[{i}/{len(ids)}] asset={aid} ERROR: {e}")
                rows.append({"asset_id": aid, "error": str(e)})
        args.report.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report -> {args.report}")
        ok = sum(1 for r in rows if "error" not in r)
        print(f"done ok={ok} failed_or_stopped={len(rows) - ok}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
