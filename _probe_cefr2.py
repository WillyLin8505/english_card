import sys
from pathlib import Path
from collections import Counter
ROOT = Path(r"D:\vibe_coding\english_card")
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
from app import db, models as m, config
from app.images import TAGS_MAX, TAG_PASS
from sqlalchemy import select, text

print("TAGS_MAX", TAGS_MAX, "TAG_PASS", TAG_PASS, "AI_URL", config.AI_URL, "AI_KEY_set", bool(config.AI_KEY))
print("MEDIA", config.MEDIA)

LEVELS = ["A1","A2","B1","B2","C1","C2"]

def cefr_for_word(s, word):
    w = word.strip().lower()
    lx = s.scalars(
        select(m.Lexeme).where(m.Lexeme.normalized == w, m.Lexeme.language == "en", m.Lexeme.status == "full").order_by(m.Lexeme.id)
    ).first()
    return (lx.cefr or None) if lx else None

def band_counts(s, tags):
    c = Counter({lv: 0 for lv in LEVELS})
    for t in tags or []:
        word = str(t.get("word", "")).strip()
        if not word:
            continue
        level = cefr_for_word(s, word) or str(t.get("cefr") or t.get("modelLevel") or "").upper()
        if level in c:
            c[level] += 1
    return dict(c)

with db.SessionLocal() as s:
    cat = [r[0] for r in s.execute(text("""
        SELECT a.id FROM image_assets a
        WHERE a.status='ready' AND a.path IS NOT NULL
          AND EXISTS (SELECT 1 FROM sense_images si WHERE si.image_asset_id=a.id AND si.review_status='approved')
        ORDER BY a.id
    """)).all()]
    complete = []
    incomplete_no_cefr_model = []
    incomplete_partial = []
    for aid in cat:
        asset = s.get(m.ImageAsset, aid)
        bc = band_counts(s, asset.tags)
        ok = all(bc.get(lv,0) >= 3 for lv in LEVELS)
        has_cefr = any(t.get("modelLevel") or t.get("cefr") for t in (asset.tags or []))
        started = (asset.tag_model or "").startswith("cefr-enrich")
        if ok:
            complete.append(aid)
        elif has_cefr or started:
            incomplete_partial.append((aid, bc, asset.tag_model, len(asset.tags or [])))
        else:
            incomplete_no_cefr_model.append((aid, bc, asset.tag_model, len(asset.tags or [])))
    print("lexicon_aware_v3_complete", len(complete))
    print("incomplete_never_enriched", len(incomplete_no_cefr_model))
    print("incomplete_partial_or_started", len(incomplete_partial))
    print("sample never", incomplete_no_cefr_model[:10])
    print("sample partial", incomplete_partial[:10])
    # how many meet >=1 and >=2 per level
    for thr in (1,2,3):
        n = 0
        for aid in cat:
            asset = s.get(m.ImageAsset, aid)
            bc = band_counts(s, asset.tags)
            if all(bc.get(lv,0) >= thr for lv in LEVELS):
                n += 1
        print(f"meet>={thr}_per_level", n)
