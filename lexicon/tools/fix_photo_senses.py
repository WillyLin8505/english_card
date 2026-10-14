"""Bind every approved photo tag to the sense that fits the photo (#195).

    python lexicon/tools/fix_photo_senses.py [--dry-run] [--qwen N] [--restore backup.json]

For each approved sense_images row (a photo tag), candidates are all senses
of the full lexemes spelled like the tag's word. quality.choose_sense picks
one by the tagger's part of speech, the other tags on the same photo (and
their main definitions), concreteness, dictionary order, and skips low
priority / Chinese-less senses. With --qwen N, up to N close calls are asked
to local Qwen (skipped when it does not answer within 45 s). The chosen sense
is stored on the binding (sense_images.sense_id, and the lexeme follows when
the part of speech changes). Backup first: exports/quality/backup-195-*.json;
--restore puts every binding's sense back."""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))
from sqlalchemy import text  # noqa: E402

from app import db, quality  # noqa: E402

OUT = HOME / "exports" / "quality"


def ask_qwen(word: str, photo_words: list[str], options: list[dict]) -> int | None:
    listing = "\n".join(f"{i + 1}. {o['definition'][:120]}" for i, o in enumerate(options))
    prompt = (f'A photo is tagged with: {", ".join(photo_words[:15])}. Which meaning of "{word}" '
              f'is shown in this photo?\n{listing}\nAnswer with the number only.')
    body = json.dumps({"model": "qwen3-vl:4b-instruct-q4_K_M", "prompt": prompt, "stream": False,
                       "options": {"temperature": 0, "num_predict": 4}}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "http://127.0.0.1:11434/api/generate", body,
                {"Content-Type": "application/json"}), timeout=45) as r:
            ans = json.loads(r.read())["response"]
    except OSError:
        return None
    digits = "".join(ch for ch in ans if ch.isdigit())
    return int(digits) - 1 if digits and 0 < int(digits) <= len(options) else None



def _sync_field_values(s, lemma: str, sense_key: str, *, gloss: str | None = None,
                       native: str | None = None, pos: str = "noun") -> int:
    """The pack is exported from field_values, so curated senses and Chinese
    are written there too (source "user" = reviewed override). Idempotent."""
    n = 0
    for field in ("definition", "native_definition"):
        row = s.execute(text("SELECT id, items FROM field_values WHERE target_language='en' AND lemma=:l "
                             "AND native_language='zh-TW' AND field=:f"), {"l": lemma, "f": field}).first()
        if row is None:
            continue
        items = list(row[1] or [])
        hit = next((i for i in items if i.get("sense_key") == sense_key), None)
        if field == "definition":
            if gloss is None or hit is not None:
                continue
            items.append({"key": sense_key, "pos": pos, "slot": pos, "gloss": gloss, "labels": [],
                          "source": "user", "sense_key": sense_key, "confidence": 1.0, "gloss_language": "en"})
        else:
            if native is None or (hit is not None and hit.get("text") == native):
                continue
            new = {"key": sense_key, "slot": sense_key, "text": native, "source": "user",
                   "sense_key": sense_key, "confidence": 1.0}
            items = [new if i is hit else i for i in items] if hit is not None else items + [new]
        s.execute(text("UPDATE field_values SET items=CAST(:i AS json) WHERE id=:id"),
                  {"i": json.dumps(items, ensure_ascii=False), "id": row[0]})
        n += 1
    return n


SCREEN_GLOSS = "A flat electronic panel that shows pictures or text, such as a monitor, TV or phone screen."


def ensure_critical_senses(s) -> int:
    """Add senses the photo simulator needs that Kaikki has but we never
    materialised (screen = electronic display)."""
    n = 0
    lid = s.execute(text("SELECT id FROM lexemes WHERE normalized='screen' AND pos='noun' AND status='full'")).scalar()
    if lid:
        has = s.execute(text(
            "SELECT 1 FROM senses se JOIN definitions d ON d.sense_id=se.id "
            "WHERE se.lexeme_id=:l AND (d.text ILIKE '%information%display%' OR se.sense_key='photo-screen-display')"),
            {"l": lid}).first()
        if not has:
            sid = s.execute(text(
                "INSERT INTO senses (lexeme_id, sense_key, ordinal, labels) VALUES "
                "(:l, 'photo-screen-display', "
                "(SELECT coalesce(max(ordinal), -1) + 1 FROM senses WHERE lexeme_id=:l), "
                "CAST('[]' AS json)) RETURNING id"), {"l": lid}).scalar()
            s.execute(text(
                "INSERT INTO definitions (sense_id, language, text, source) VALUES "
                "(:s, 'en', 'A flat electronic panel that shows pictures or text, such as a monitor, TV or phone screen.', 'manual-195')"),
                {"s": sid})
            s.execute(text(
                "INSERT INTO sense_translations (sense_id, native_language, text, source, is_ai, is_override) VALUES "
                "(:s, 'zh-TW', '螢幕、畫面', 'manual-195', false, false)"), {"s": sid})
            n += 1
    # Careful Chinese corrections for senses photos use (only when the old
    # value is the known-wrong one).
    for sid, old, new in ((7193, "黑人、黑色", "黑色"),):
        r = s.execute(text("UPDATE sense_translations SET text=:n, source='manual-195' "
                           "WHERE sense_id=:s AND native_language='zh-TW' AND text=:o"),
                      {"s": sid, "o": old, "n": new})
        n += r.rowcount
    # Reviewed translations replacing an AI paraphrase on the common sense.
    for sid, old, new in ((3884, "接收或發送電磁波的裝置", "天線"),):
        r = s.execute(text("UPDATE sense_translations SET text=:n, source='manual-195', is_ai=false "
                           "WHERE sense_id=:s AND native_language='zh-TW' AND text=:o"),
                      {"s": sid, "o": old, "n": new})
        n += r.rowcount
    n += _sync_field_values(s, "screen", "photo-screen-display", gloss=SCREEN_GLOSS, native="螢幕、畫面")
    n += _sync_field_values(s, "antenna", "20855d577f56", native="天線")
    n += _sync_field_values(s, "black", "8e7ccb988f94", native="黑色")
    return n



def main(argv: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if "--restore" in argv:
        rows = json.loads(Path(argv[argv.index("--restore") + 1]).read_text(encoding="utf-8"))
        with db.session_scope() as s:
            s.execute(text("UPDATE sense_images SET sense_id = :s WHERE id = :i"),
                      [{"i": i, "s": sid} for i, sid, _ in rows["sense_images"]])
        print("restored", len(rows["sense_images"]))
        return
    qwen_budget = int(argv[argv.index("--qwen") + 1]) if "--qwen" in argv else 0
    overrides = quality.load_json("overrides.json")
    low_ids = {int(x) for x in overrides.get("low_priority_senses", [])}
    with db.session_scope() as s:
        counts = collections.Counter()
        counts["senses_added"] = ensure_critical_senses(s)
        curated = {r[0] for r in s.execute(text("SELECT id FROM senses WHERE sense_key LIKE 'photo-%'"))}
        senses = collections.defaultdict(list)  # normalized -> candidates
        sense_word = {}
        for r in s.execute(text(
                "SELECT se.id, se.ordinal, se.labels, l.id, l.normalized, l.pos, d.text, t.text, t.is_ai"
                " FROM senses se JOIN lexemes l ON l.id = se.lexeme_id AND l.status = 'full'"
                " LEFT JOIN definitions d ON d.sense_id = se.id"
                " LEFT JOIN sense_translations t ON t.sense_id = se.id AND t.native_language = 'zh-TW'"
                " ORDER BY l.id, se.ordinal")):
            sid, ordn, labels, lid, word, pos, definition, native, is_ai = r
            senses[word].append({"id": sid, "ordinal": ordn, "labels": labels or [], "lexeme_id": lid,
                                 "lexeme_pos": pos, "definition": definition or "", "native": native,
                                 "native_ai": bool(is_ai)})
            sense_word[sid] = word
        # Low priority as in the pack: labels, AI after a dictionary sense, overrides.
        for word, cands in senses.items():
            seen = collections.defaultdict(bool)
            for c in cands:
                c["low"] = (quality.sense_is_low(c, seen[c["lexeme_id"]]) or c["id"] in low_ids)
                if not c["low"] and c["native"] and not c["native_ai"]:
                    seen[c["lexeme_id"]] = True
        main_def = {w: next((c["definition"] for c in cs if not c["low"]), cs[0]["definition"])
                    for w, cs in senses.items() if cs}
        bindings = s.execute(text(
            "SELECT si.id, si.sense_id, si.image_asset_id, si.review_status, a.tags FROM sense_images si"
            " JOIN image_assets a ON a.id = si.image_asset_id WHERE si.review_status = 'approved'")).all()
        per_image = collections.defaultdict(list)
        for b in bindings:
            if b[1] in sense_word:
                per_image[b[2]].append(sense_word[b[1]])
        backup = {"created": dt.datetime.now().isoformat(),
                  "sense_images": [[b[0], b[1], b[3]] for b in bindings]}
        changes, log = [], []
        taken = {(b[1], b[2]) for b in bindings}
        for bid, sid, img, _, raw in bindings:
            word = sense_word.get(sid)
            if not word:
                counts["not_full"] += 1
                continue
            counts["tags"] += 1
            others = [w for w in per_image[img] if w != word]
            context = set()
            for w in others:
                context |= quality.tokens(w) | quality.tokens(main_def.get(w))
            tag_pos = next((t.get("pos") for t in raw or [] if str(t.get("word", "")).lower() == word), None)
            cur = next((c for c in senses[word] if c["id"] == sid), None)
            # Stay in the bound lexeme (its part of speech) unless the tagger
            # said another part of speech that has a full entry.
            want = {"adjective": "adj", "adverb": "adv"}.get(tag_pos or "", tag_pos)
            pool = [c for c in senses[word] if c["lexeme_pos"] == want] if want else []
            if not pool:
                pool = [c for c in senses[word] if c["lexeme_id"] == (cur or {}).get("lexeme_id")]
            best, top, second = quality.choose_sense(pool, context, sid, tag_pos)
            cur_ok = bool(cur and (cur.get("native") or "").strip() and not cur.get("low")
                          and cur in pool)
            if best and cur_ok and best["id"] != sid:
                cur_score = quality.choose_sense([cur], context, sid, tag_pos)[1]
                # Only a clearly better fit that the photo itself supports (its
                # definition shares a word with the other tags) replaces a usable sense.
                overlap = quality.tokens(best["definition"]) & (context | {"picture", "scene"})
                if top - cur_score < (1.0 if best["id"] in curated else 3.0) or not overlap:
                    best = cur
            if not best:
                counts["no_chinese_anywhere"] += 1
                continue
            via = "rules"
            if qwen_budget and top - second < 1.0:
                opts = [c for c in senses[word] if (c["native"] or "").strip() and not c["low"]][:8]
                if len(opts) > 1:
                    qwen_budget -= 1
                    pick = ask_qwen(word, others, opts)
                    counts["qwen_asked"] += 1
                    if pick is not None:
                        best, via = opts[pick], "qwen"
                        counts["qwen_answered"] += 1
            if cur and cur.get("low"):
                counts["was_low"] += 1
            if cur and not (cur.get("native") or "").strip():
                counts["was_no_chinese"] += 1
            if best["id"] == sid:
                continue
            if (best["id"], img) in taken:
                counts["skip_duplicate"] += 1
                continue
            taken.add((best["id"], img))
            changes.append({"i": bid, "s": best["id"]})
            counts["changed"] += 1
            counts["changed_lexeme"] += best["lexeme_id"] != (cur or {}).get("lexeme_id")
            log.append({"binding": bid, "image": img, "word": word, "via": via,
                        "from": [sid, (cur or {}).get("native")], "to": [best["id"], best["native"]],
                        "context": others[:10]})
        print(json.dumps(dict(counts), ensure_ascii=False))
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        (OUT / f"photo-senses-195-{stamp}.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=0), encoding="utf-8")
        if "--dry-run" in argv:
            s.rollback()
            return
        (OUT / f"backup-195-{stamp}.json").write_text(json.dumps(backup), encoding="utf-8")
        if changes:
            s.execute(text("UPDATE sense_images SET sense_id = :s WHERE id = :i"), changes)
        print("backup:", OUT / f"backup-195-{stamp}.json")


if __name__ == "__main__":
    main(sys.argv[1:])