import sys
from pathlib import Path
from collections import Counter
ROOT = Path(r"D:\vibe_coding\english_card")
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
from app import db, models as m
from sqlalchemy import text

LEVELS = ["A1","A2","B1","B2","C1","C2"]

def band_counts(tags):
    c = Counter({lv: 0 for lv in LEVELS})
    for t in tags or []:
        level = str(t.get("cefr") or t.get("modelLevel") or "").upper()
        if level in c:
            c[level] += 1
    return dict(c)

def is_v3_complete(tags, per_level=3):
    bc = band_counts(tags)
    return all(bc.get(lv, 0) >= per_level for lv in LEVELS), bc

with db.SessionLocal() as s:
    sources = s.execute(text("SELECT source, count(*) FROM image_assets GROUP BY source")).all()
    print("sources", list(sources))
    status = s.execute(text("SELECT status, count(*) FROM image_assets GROUP BY status")).all()
    print("status", list(status))
    cat = s.execute(text("""
        SELECT a.id, a.path, a.source, a.tag_model
        FROM image_assets a
        WHERE a.status = 'ready' AND a.path IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM sense_images si
            WHERE si.image_asset_id = a.id AND si.review_status = 'approved'
          )
        ORDER BY a.id
    """)).all()
    all_ready = s.execute(text(
        "SELECT id, path, source, tag_model FROM image_assets WHERE status='ready' AND path IS NOT NULL ORDER BY id"
    )).all()
    print("catalog_approved", len(cat))
    print("all_ready", len(all_ready))

    def classify(rows, label):
        done, need, has_any_cefr = [], [], []
        for row in rows:
            asset = s.get(m.ImageAsset, row[0])
            ok, bc = is_v3_complete(asset.tags, 3)
            has_cefr = any(str(t.get("cefr") or t.get("modelLevel") or "") for t in (asset.tags or []))
            info = {
                "id": row[0],
                "path": row[1],
                "source": row[2],
                "tag_model": row[3],
                "n_tags": len(asset.tags or []),
                "bands": bc,
                "has_cefr": has_cefr,
            }
            if ok:
                done.append(info)
            else:
                need.append(info)
            if has_cefr:
                has_any_cefr.append(info)
        print(f"== {label} ==")
        print("v3_complete", len(done), "incomplete", len(need), "has_any_cefr_tag", len(has_any_cefr))
        print("-- incomplete --")
        for x in need:
            print(x)
        print("-- complete ids/paths --")
        for x in done:
            print({"id": x["id"], "path": x["path"], "n_tags": x["n_tags"], "bands": x["bands"], "tag_model": x["tag_model"]})
        return done, need

    classify(cat, "catalog")
    # user/album ready not in catalog
    cat_ids = {r[0] for r in cat}
    non_cat = [r for r in all_ready if r[0] not in cat_ids]
    print("non_catalog_ready", len(non_cat))
    classify(non_cat, "non_catalog_ready")
