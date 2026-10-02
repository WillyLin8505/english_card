"""Resilient CEFR enrich batch: continues on errors, retries TaggerUnavailable."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from collections import Counter

ROOT = Path(r"D:\vibe_coding\english_card")
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
sys.path.insert(0, str(ROOT / "lexicon" / "tools"))

from app import db, models as m
from app.images import TaggerUnavailable, TAGS_MAX
from sqlalchemy import text, select
import enrich_cefr_tags as ect

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
LOG = ROOT / "logs" / "cefr_enrich_batch_06.log"
REPORT = ROOT / "logs" / "cefr_enrich_batch_06.json"
MAX_ASSETS = 40  # catalog never-enriched cap this run
RETRIES = 3


def never_enriched_ids(s, limit: int) -> list[int]:
    cat = [
        r[0]
        for r in s.execute(
            text(
                """
                SELECT a.id FROM image_assets a
                WHERE a.status='ready' AND a.path IS NOT NULL
                  AND EXISTS (
                    SELECT 1 FROM sense_images si
                    WHERE si.image_asset_id=a.id AND si.review_status='approved'
                  )
                ORDER BY (
                    SELECT count(*) FROM sense_images si
                    WHERE si.image_asset_id=a.id AND si.review_status='approved'
                ) ASC, a.id
                """
            )
        ).all()
    ]
    out = []
    for aid in cat:
        asset = s.get(m.ImageAsset, aid)
        tags = asset.tags or []
        if any(t.get("modelLevel") or t.get("cefr") for t in tags):
            continue
        if (asset.tag_model or "").startswith("cefr-enrich"):
            continue
        bc = ect.band_counts(s, tags)
        if all(bc.get(lv, 0) >= 3 for lv in LEVELS):
            continue
        out.append(aid)
        if len(out) >= limit:
            break
    return out


def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        print(msg, flush=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

    s = db.SessionLocal()
    rows = []
    try:
        ids = never_enriched_ids(s, MAX_ASSETS)
        log(f"enrich targets={len(ids)} TAGS_MAX={TAGS_MAX} ids={ids}")
        for i, aid in enumerate(ids, 1):
            asset = s.get(m.ImageAsset, aid)
            path = asset.path if asset else "?"
            ok_row = None
            last_err = None
            for attempt in range(1, RETRIES + 1):
                try:
                    ok_row = ect.enrich_asset(s, aid, per_level=3, dry_run=False, defer_score=True)
                    break
                except TaggerUnavailable as e:
                    last_err = e
                    s.rollback()
                    log(f"[{i}/{len(ids)}] asset={aid} TAGGER_UNAVAILABLE attempt={attempt}: {e}")
                    time.sleep(5 * attempt)
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    s.rollback()
                    log(f"[{i}/{len(ids)}] asset={aid} ERROR: {e}")
                    break
            if ok_row is None:
                rows.append({"asset_id": aid, "path": path, "error": str(last_err)})
                continue
            ok_row["path"] = path
            rows.append(ok_row)
            log(
                f"[{i}/{len(ids)}] asset={aid} path={path} "
                f"{ok_row['before_n']}->{ok_row['after_n']} +{ok_row['added']} "
                f"passed_new={ok_row['passed_new']} new={ok_row.get('new_words')} "
                f"bands {ok_row['before_bands']} -> {ok_row['after_bands']}"
            )
            # brief pause so workers can breathe
            time.sleep(1)
    finally:
        s.close()

    REPORT.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in rows if "error" not in r)
    v3 = 0
    for r in rows:
        if "error" in r:
            continue
        bc = r.get("after_bands") or {}
        if all(bc.get(lv, 0) >= 3 for lv in LEVELS):
            v3 += 1
    log(f"report -> {REPORT}")
    log(f"done ok={ok} failed={len(rows)-ok} v3_complete_in_batch={v3}")


if __name__ == "__main__":
    main()
