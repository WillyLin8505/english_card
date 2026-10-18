"""問題回報 #187: 中文翻譯夾雜英文／殘字，或完全沒有翻譯 — root cause + fix.

Root cause: adapters/base.py's shared validate() accepted any zh-TW candidate
with at least one CJK character, never checking for stray Latin letters
alongside it. An AI answer that leaked an English word (table「背gammon遊戲」)
or left an abbreviation residue (ship「船、船舶、CP」) passed as a normal
translation. qc.py now reports every such sense under sense.native_has_latin
/ sense.native_empty (every sense, not only the main one shown on the card),
and validate() rejects a new candidate with the same problem — so re-running
this can't reproduce it.

This tool clears the existing bad ai_translate candidates (the dictionaries
never had these senses — see scan's "no dictionary alternative" count: a
word-level dictionary can't tell which sense a meaning belongs to, so there
is no deterministic substitute) and lets the ordinary pipeline re-resolve
them: dictionaries first, then one AI batch request per headword for
whatever is still missing. Small batches by default, resumable, so it never
ties down the Ollama GPU the tags worker is using.

    python lexicon/tools/fix_native_quality.py scan                      # read-only
    python lexicon/tools/fix_native_quality.py fix --limit 5             # small trial
    python lexicon/tools/fix_native_quality.py fix --words table,mirror,pot,ship,hose
    python lexicon/tools/fix_native_quality.py fix --limit 50 --resume   # next 50, skips done ones
    python lexicon/tools/fix_native_quality.py fix --limit 0 --resume    # the rest, no cap (long: avoid while tagging)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))

from sqlalchemy import text  # noqa: E402

from app import adapters, db, pipeline  # noqa: E402
from app.text import native_latin_issue  # noqa: E402

SNAPSHOTS = HOME / "raw-data" / "snapshots"
PROGRESS = HOME / "raw-data" / "fix_native_quality_progress.json"

SCAN_SQL = """
SELECT l.normalized AS lemma, s.sense_key, st.text, st.source, st.is_ai
FROM senses s
JOIN lexemes l ON l.id = s.lexeme_id
LEFT JOIN sense_translations st ON st.sense_id = s.id AND st.native_language = 'zh-TW'
WHERE l.status = 'full'
"""


def targets(s) -> dict[str, dict[str, list[str]]]:
    """{lemma: {"latin": [sense_key...], "empty": [sense_key...]}} — every
    sense of a full entry whose zh-TW translation is missing, or has Latin
    outside the parenthetical/abbreviation exceptions (text.native_latin_issue)."""
    out: dict[str, dict[str, list[str]]] = {}
    for lemma, sense_key, native_text, source, is_ai in s.execute(text(SCAN_SQL)).all():
        if native_text is None:
            kind = "empty"
        elif native_latin_issue(native_text):
            kind = "latin"
        else:
            continue
        out.setdefault(lemma, {}).setdefault(kind, []).append(sense_key)
    return out


def overridden(s, lemmas: list[str]) -> set[str]:
    """Lemmas with a user_overrides row for native_definition: never touched
    (user values always win — pipeline.resolve_field short-circuits on them
    too, but we also skip them here so we never even snapshot/invalidate)."""
    rows = s.execute(text(
        "SELECT lemma FROM user_overrides WHERE target_language = 'en' "
        "AND native_language = 'zh-TW' AND field = 'native_definition' "
        "AND lemma = ANY(:l)"), {"l": lemmas}).scalars().all()
    return set(rows)


def scan() -> None:
    with db.session_scope() as s:
        s.execute(text("SET TRANSACTION READ ONLY"))
        found = targets(s)
        skip = overridden(s, list(found))
    n_latin = sum(len(v.get("latin", [])) for v in found.values())
    n_empty = sum(len(v.get("empty", [])) for v in found.values())
    print(f"senses with Latin-mixed/residue native: {n_latin} "
          f"({sum(1 for v in found.values() if v.get('latin'))} headwords)")
    print(f"senses with no native at all: {n_empty} "
          f"({sum(1 for v in found.values() if v.get('empty'))} headwords)")
    print(f"headwords total needing a pass: {len(found)} "
          f"(user_overrides protect {len(skip)} of them — skipped)")
    print("sample (lemma: kinds):")
    for lemma, kinds in list(found.items())[:20]:
        tag = "/".join(k for k in ("latin", "empty") if kinds.get(k))
        print(f"  {lemma}: {tag} ({sum(len(v) for v in kinds.values())} 個義項)")


def _display(s, lemma: str) -> str:
    row = s.execute(text("SELECT lemma FROM lexemes WHERE language = 'en' "
                         "AND normalized = :n LIMIT 1"), {"n": lemma}).scalar()
    return row or lemma


def _snapshot_rows(s, lemma: str) -> dict:
    fv = [dict(r._mapping) for r in s.execute(text(
        "SELECT * FROM field_values WHERE target_language = 'en' AND lemma = :l "
        "AND native_language = 'zh-TW' AND field = 'native_definition'"), {"l": lemma})]
    fc = [dict(r._mapping) for r in s.execute(text(
        "SELECT * FROM field_candidates WHERE target_language = 'en' AND lemma = :l "
        "AND native_language = 'zh-TW' AND field = 'native_definition'"), {"l": lemma})]
    st = [dict(r._mapping) for r in s.execute(text(
        "SELECT st.* FROM sense_translations st JOIN senses se ON se.id = st.sense_id "
        "JOIN lexemes l ON l.id = se.lexeme_id "
        "WHERE l.normalized = :l AND l.language = 'en' AND st.native_language = 'zh-TW'"),
        {"l": lemma})]
    return {"field_values": fv, "field_candidates": fc, "sense_translations": st}


def _load_progress() -> set[str]:
    if PROGRESS.exists():
        return set(json.loads(PROGRESS.read_text(encoding="utf-8")))
    return set()


def _save_progress(done: set[str]) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


def fix(words: list[str] | None, limit: int | None, resume: bool) -> None:
    with db.session_scope() as s:
        s.execute(text("SET TRANSACTION READ ONLY"))
        found = targets(s)
    if words:
        found = {w: found[w] for w in words if w in found}
        missing = [w for w in words if w not in found]
        if missing:
            print("no bad sense found for:", missing)
    done = _load_progress() if resume else set()
    todo = [lemma for lemma in found if lemma not in done]
    if limit:
        todo = todo[:limit]
    if not todo:
        print("nothing to do (", len(done), "already done )")
        return
    snapshot = {"made_at": datetime.now().isoformat(), "lemmas": {}}
    fixed_slots = skipped_override = 0
    for lemma in todo:
        with db.session_scope() as s:
            if overridden(s, [lemma]):
                print(f"{lemma}: user_overrides 保護，略過")
                skipped_override += 1
                done.add(lemma)
                continue
            snapshot["lemmas"][lemma] = _snapshot_rows(s, lemma)
            latin_keys = found[lemma].get("latin", [])
            invalidated = 0
            if latin_keys:
                # Any source, not only ai_translate: 2 of the 255 came from
                # kaikki's translation table and 2 from ecdict (same gap in
                # the old validate(), a Latin-tagged "Mandarin" entry).
                for sk in latin_keys:
                    for row in s.execute(text(
                            "SELECT id, value FROM field_candidates WHERE target_language = 'en' "
                            "AND lemma = :l AND native_language = 'zh-TW' AND field = 'native_definition' "
                            "AND slot = :sk AND valid = true"),
                            {"l": lemma, "sk": sk}).all():
                        reason = native_latin_issue((row.value or {}).get("text") or "")
                        if not reason:
                            continue
                        s.execute(text(
                            "UPDATE field_candidates SET valid = false, "
                            "invalid_reason = :r WHERE id = :id"),
                            {"r": f"夾雜拉丁字母／殘字：{reason}（qc 回填 #187）", "id": row.id})
                        invalidated += 1
            display = _display(s, lemma)
            adapters.configure(s)
            reports = pipeline.process_word(s, "en", "zh-TW", display, ["native_definition"],
                                            "reresolve")
        status = next((r.status for r in reports if r.field == "native_definition"), "?")
        fixed_slots += invalidated
        done.add(lemma)
        print(f"{lemma}: {len(latin_keys)} latin 失效、"
              f"{len(found[lemma].get('empty', []))} 空缺 -> reresolve status={status}")
    _save_progress(done)
    if snapshot["lemmas"]:
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        path = SNAPSHOTS / f"native_quality_{datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"snapshot: {path}")
    print(f"processed {len(todo)} headwords ({skipped_override} 受 user_overrides 保護略過), "
          f"invalidated {fixed_slots} bad ai_translate candidates; "
          f"{len(found) - len(done)} headwords left ({PROGRESS})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    f = sub.add_parser("fix")
    f.add_argument("--words", help="comma-separated headwords (default: every bad one found)")
    f.add_argument("--limit", type=int, default=5,
                   help="max headwords this run processes (0 = no cap); default 5, a small trial")
    f.add_argument("--resume", action="store_true",
                   help="skip headwords already done per raw-data/fix_native_quality_progress.json")
    a = ap.parse_args()
    if a.cmd == "scan":
        scan()
        return
    words = [w.strip().lower() for w in a.words.split(",")] if a.words else None
    fix(words, a.limit or None, a.resume)


if __name__ == "__main__":
    main()
