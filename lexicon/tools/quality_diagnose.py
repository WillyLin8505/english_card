"""Read-only quality diagnostic: provenance and root-cause counts (no writes)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import db
from sqlalchemy import text

Q = {
 "lexemes_by_status_pos_unknown": "SELECT status, (pos='unknown') AS unk, count(*), count(cefr) FROM lexemes WHERE language='en' GROUP BY 1,2 ORDER BY 1,2",
 "stub_with_cefr": "SELECT count(*) FROM lexemes WHERE status='stub' AND cefr IS NOT NULL",
 "redirects": "SELECT count(*) FROM lexeme_redirects",
 "field_item_sources": """SELECT fv.field, it->>'source' AS src, coalesce(it->>'ai','false') AS ai, count(*)
    FROM field_values fv, jsonb_array_elements(fv.items::jsonb) it
    WHERE fv.target_language='en' AND fv.field IN ('definition','native_definition','examples','cefr','pos','ipa','images','audio')
    GROUP BY 1,2,3 ORDER BY 1,4 DESC""",
 "field_status": "SELECT field, status, count(*) FROM field_values WHERE target_language='en' AND field IN ('definition','native_definition','examples','ipa','cefr') GROUP BY 1,2 ORDER BY 1,3 DESC",
 "full_without_native": """SELECT count(*) FROM lexemes l WHERE l.status='full' AND NOT EXISTS
    (SELECT 1 FROM senses s JOIN sense_translations t ON t.sense_id=s.id WHERE s.lexeme_id=l.id)""",
 "senses_total_ai_none": """SELECT count(*), count(t.id), sum(CASE WHEN t.is_ai THEN 1 ELSE 0 END)
    FROM senses s JOIN lexemes l ON l.id=s.lexeme_id AND l.status='full' LEFT JOIN sense_translations t ON t.sense_id=s.id AND t.native_language='zh-TW'""",
 "first_sense_ai": """SELECT count(*) FROM senses s JOIN lexemes l ON l.id=s.lexeme_id AND l.status='full'
    JOIN sense_translations t ON t.sense_id=s.id WHERE s.ordinal=0 AND t.is_ai""",
 "stub_origin": "SELECT (EXISTS (SELECT 1 FROM lexeme_relations r WHERE lower(r.target_word)=l.normalized)) AS relation_target, (EXISTS (SELECT 1 FROM sense_images si JOIN senses s ON s.id=si.sense_id WHERE s.lexeme_id=l.id)) AS has_image, count(*) FROM lexemes l WHERE l.status='stub' GROUP BY 1,2",
 "example_sources": "SELECT source, count(*) FROM examples GROUP BY 1 ORDER BY 2 DESC",
 "image_sources": "SELECT source, status, count(*) FROM image_assets GROUP BY 1,2 ORDER BY 3 DESC",
 "sense_images_status": "SELECT review_status, count(*) FROM sense_images GROUP BY 1",
 "photos_tagged": """SELECT (tags IS NOT NULL AND tags::text NOT IN ('null','[]','{}')) AS tagged, count(*) FROM image_assets GROUP BY 1""",
 "approved_bindings_per_image": """SELECT n, count(*) FROM (SELECT image_asset_id, count(*) n FROM sense_images WHERE review_status='approved' GROUP BY 1) x GROUP BY 1 ORDER BY 1""",
 "binding_sense_ai_or_nonfirst": """SELECT sum(CASE WHEN t.id IS NULL THEN 1 ELSE 0 END) no_zh, sum(CASE WHEN t.is_ai THEN 1 ELSE 0 END) ai,
    sum(CASE WHEN s.ordinal>0 THEN 1 ELSE 0 END) nonfirst, count(*)
    FROM sense_images si JOIN senses s ON s.id=si.sense_id LEFT JOIN sense_translations t ON t.sense_id=s.id AND t.native_language='zh-TW'
    WHERE si.review_status='approved'""",
}

def main():
    out = {}
    with db.session_scope() as s:
        s.execute(text("SET TRANSACTION READ ONLY"))
        for k, q in Q.items():
            try:
                out[k] = [list(map(lambda v: v if isinstance(v, (int, float, str, type(None), bool)) else str(v), r)) for r in s.execute(text(q))]
            except Exception as e:  # report and continue; read-only
                s.rollback(); s.execute(text("SET TRANSACTION READ ONLY"))
                out[k] = f"ERR {type(e).__name__}: {str(e).splitlines()[0][:160]}"
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()