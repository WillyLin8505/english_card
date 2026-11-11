"""Gap list for the night card #1065 (card #1070, issue #1579): counts what is missing per language, no LLM, < 2 min.

  python lexicon/tools/gap_report.py [--json]

Columns it counts are only those #1065 may fill (picture, audio, example via Tatoeba, native translation of the word).
IPA, example/related/etymology Chinese are left to day cards (#828 #831 #832 #1058) and are listed "info" only.
Prints the gaps largest first, with the 'night_can_fill' flag; the first line of 'NEXT' is what #1065 should work on.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
sys.path.insert(0, str(ROOT / "lexicon" / "tools"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from sqlalchemy import text  # noqa: PLC0415
    from app import db  # noqa: PLC0415
    import goal_check  # noqa: PLC0415

    np_ids = goal_check.no_picture_ids() or [0]
    words = list(goal_check.basic_words())
    img = ("EXISTS (SELECT 1 FROM sense_images si JOIN senses s ON s.id=si.sense_id "
           "WHERE s.lexeme_id=l.id AND si.review_status='approved')")
    audio = "EXISTS (SELECT 1 FROM pronunciations p WHERE p.lexeme_id=l.id AND p.audio_asset_id IS NOT NULL)"
    ipa = "EXISTS (SELECT 1 FROM pronunciations p WHERE p.lexeme_id=l.id AND p.kind='ipa')"
    ex = "EXISTS (SELECT 1 FROM examples e WHERE e.lexeme_id=l.id)"
    native = {"fr": "en", "en": "zh-TW"}
    out: list[dict] = []
    with db.SessionLocal() as s:
        def n(sql, **p):
            return int(s.execute(text(sql), p).scalar() or 0)
        for lang in ("fr", "en"):
            base = f"FROM lexemes l WHERE l.language='{lang}' AND l.status='full'"
            tr = (f"EXISTS (SELECT 1 FROM senses s JOIN sense_translations t ON t.sense_id=s.id "
                  f"AND t.native_language='{native[lang]}' WHERE s.lexeme_id=l.id)")
            a12 = "AND l.cefr IN ('A1','A2')"
            noun = "AND l.pos='noun' AND l.id <> ALL(:np)"
            rows = [
                ("A1/A2 名詞缺核准配圖", n(f"SELECT count(*) {base} {a12} {noun} AND NOT {img}", np=np_ids), True),
                ("其他名詞缺核准配圖（B1+/無等級）", n(f"SELECT count(*) {base} AND (l.cefr IS NULL OR l.cefr NOT IN ('A1','A2')) {noun} AND NOT {img}", np=np_ids), True),
                ("A1/A2 缺音檔", n(f"SELECT count(*) {base} {a12} AND NOT {audio}"), lang == "fr"),
                ("全部缺音檔", n(f"SELECT count(*) {base} AND NOT {audio}"), False),
                ("沒有任何例句（找 Tatoeba）", n(f"SELECT count(*) {base} AND NOT {ex}"), True),
                (f"詞義缺 {native[lang]} 翻譯（Qwen 標 AI）", n(f"SELECT count(*) {base} AND NOT {tr}"), True),
                ("缺 IPA（#1058 / 不編）", n(f"SELECT count(*) {base} AND NOT {ipa}"), False),
            ]
            for name, c, can in rows:
                out.append({"lang": lang, "gap": name, "count": c, "night_can_fill": can})
        fr_present = n("SELECT count(DISTINCT lemma) FROM lexemes WHERE language='fr' AND lemma = ANY(:w)", w=words)
        out.append({"lang": "fr", "gap": f"D1 基礎表字不在詞庫（{len(words)} 字）", "count": len(words) - fr_present, "night_can_fill": True})
    out.sort(key=lambda r: (not r["night_can_fill"], -r["count"]))
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    for r in out:
        print(f"{'+' if r['night_can_fill'] else '-'} {r['lang']}  {r['count']:>7,}  {r['gap']}")
    top = next((r for r in out if r["night_can_fill"] and r["count"] > 0), None)
    print("NEXT:", f"{top['lang']} {top['gap']} ({top['count']:,})" if top else "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
