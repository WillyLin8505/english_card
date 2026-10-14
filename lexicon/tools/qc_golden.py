"""Build golden set v1 (50 photos + 300 words) and its review file.

Words: 50 per CEFR level from the CEFR-J / Octanove list (an independent
source, not the pack), restricted to single-POS-level, common words that
the pack has as full entries. Photos: the photos from #195's checks plus a
spread over the catalog. The review file lists what the pack shows today so
the owner can mark wrong rows.

    python lexicon/tools/qc_golden.py --pack %TEMP%\\lex.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
from app import qc  # noqa: E402

KNOWN = {  # reviewed in #195 (photo id -> word -> expected Chinese substring)
    71: {"screen": "螢幕", "antenna": "天線", "display": "顯示", "phone": ""},
    26: {"background": "背景", "vein": "葉脈", "leaf": "葉"},
    85: {"black": "黑色", "car": "車", "headlight": "燈"},
    702: {"sign": "標牌"},
    680: {"arched": "拱"},
    723: {"weathered": "風雨"},
    616: {"illuminated": "光", "window": "窗"},
}


def build(pack: dict) -> dict:
    cefr = json.loads((ROOT / "app" / "assets" / "cefr_en.json").read_text(encoding="utf-8"))["words"]
    full = {}
    for lx in pack["lexemes"]:
        if lx.get("status") == "full":
            full.setdefault(lx["normalized"], []).append(lx)
    words = []
    for lv in qc.LEVELS:
        pool = []
        for w, hit in cefr.items():
            if not w.isalpha() or w not in full or not hit or not hit[1]:
                continue
            levels = set(hit[1].values())
            if levels != {lv}:
                continue
            pos = next(iter(hit[1]))
            pool.append((-(hit[0] or 0), w, pos))
        pool.sort()
        step = max(1, len(pool) // 50)
        for _, w, pos in pool[::step][:50]:
            words.append({"word": w, "pos": {"adjective": "adj", "adverb": "adv"}.get(pos, pos), "cefr": lv})
    images = sorted(pack.get("catalog_images") or [], key=lambda im: im["id"])
    chosen = [im["id"] for im in images if im["id"] in KNOWN]
    rest = [im["id"] for im in images if im["id"] not in KNOWN and len(im.get("tags") or []) >= 3]
    step = max(1, len(rest) // (50 - len(chosen)))
    chosen += rest[::step][: 50 - len(chosen)]
    photos = [{"id": i, "expect": {k: v for k, v in KNOWN.get(i, {}).items() if v}, "min_tags": 3}
              for i in sorted(chosen)]
    return {"version": "v1", "note": "Owner spot-check: QUALITY_SYSTEM_DESIGN.md decision 4.",
            "photos": photos, "words": words}


def review(pack: dict, golden: dict) -> str:
    by_id, redirects = qc._index(pack)
    images = {im["id"]: im for im in pack.get("catalog_images") or []}
    full = {}
    for lx in pack["lexemes"]:
        if lx.get("status") == "full":
            full.setdefault(lx["normalized"], []).append(lx)
    out = ["# 黃金集 v1 抽審表", "",
           "請在「OK?」欄填 ✗ 並寫正確答案；空白視為正確。修改後告訴我，我會更新 v1.json 的 expect。", "",
           "## 照片（50 張）", "", "| 照片 | 標籤（顯示的中文義項｜等級） | OK? |", "|---|---|---|"]
    for p in golden["photos"]:
        im = images.get(p["id"]) or {}
        cells = []
        for t in im.get("tags") or []:
            lx = by_id.get(redirects.get(t.get("lexeme_id"), t.get("lexeme_id"))) or {}
            s = next((x for x in lx.get("senses") or [] if x.get("id") == t.get("sense_id")), {}) or {}
            cells.append(f"{lx.get('lemma')}={s.get('native') or '∅'}｜{t.get('cefr') or '-'}")
        out.append(f"| [{p['id']}](http://127.0.0.1:8123/api/image?id={p['id']}) | {'；'.join(cells)} | |")
    out += ["", "## 單字（300 個，等級＝CEFR-J／Octanove 清單）", "",
            "| 單字 | 詞性 | 期望等級 | 目前等級 | 主義項中文 | OK? |", "|---|---|---|---|---|---|"]
    for w in golden["words"]:
        es = full.get(w["word"], [])
        lx = next((e for e in es if e.get("pos") == w["pos"]), es[0] if es else {})
        ms = qc.main_sense(lx) if lx else None
        out.append(f"| {w['word']} | {w['pos']} | {w['cefr']} | {lx.get('cefr') or '-'} | "
                   f"{(ms or {}).get('native') or '∅'} | |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    a = ap.parse_args()
    pack = json.loads(Path(a.pack).read_text(encoding="utf-8"))
    qc.GOLDEN.mkdir(parents=True, exist_ok=True)
    g = build(pack)
    (qc.GOLDEN / "v1.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    (qc.GOLDEN / "v1_review.md").write_text(review(pack, g), encoding="utf-8")
    print(len(g["photos"]), "photos", len(g["words"]), "words ->", qc.GOLDEN)


if __name__ == "__main__":
    main()