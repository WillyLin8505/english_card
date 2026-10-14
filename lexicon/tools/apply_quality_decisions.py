"""Apply owner decision 問題回報 #191 to the lexicon database, reversibly.

    python lexicon/tools/apply_quality_decisions.py            # backup + apply
    python lexicon/tools/apply_quality_decisions.py --dry-run  # counts only
    python lexicon/tools/apply_quality_decisions.py --restore <backup.json>

Input: quality/entry_flags.json (tools/lint_lexicon.py). For every flagged
lexeme:
  inflected_form           -> lexeme_redirects(old=form, new=lemma) and CEFR None
                              (the lexeme row stays; the pack makes it a pointer)
  person_name / proper_or_brand / abbreviation / phrase_fragment -> CEFR None
  cefr_above_list / common_word_too_hard / idiom_too_easy -> CEFR = suggestion
Writes quality/decisions.json, which app_pack/serve_app apply at pack time
(quality.apply_decisions) so a re-import can't bring the old values back.
The backup (every lexeme's cefr + the whole lexeme_redirects table) goes to
exports/quality/backup-<time>.json; --restore puts both back exactly."""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))
from sqlalchemy import text  # noqa: E402

from app import db, quality  # noqa: E402

EXCLUDE = ("person_name", "proper_or_brand", "abbreviation", "phrase_fragment")
LEVEL_RULES = ("cefr_above_list", "common_word_too_hard", "idiom_too_easy")
_FORM_POS = (("ing", "verb"), ("ed", "verb"), ("s", "noun"))


def suggested_level(rule: str, detail: str) -> tuple[str, bool]:
    """(level, ambiguous). '由 grass 衍生，建議 ≤B1' -> B1 (the ceiling)."""
    m = re.search(r"(A1|A2|B1|B2|C1|C2)", detail or "")
    level = m.group(1) if m else "B2"
    return level, rule == "common_word_too_hard" or "≤" in (detail or "")


def pick_base(rows: list[tuple], form: str, pos: str) -> int | None:
    """The lemma lexeme a form points at: same pos full entry, else the pos
    the ending implies (fleeing -> verb), else any full one, else any."""
    full = [r for r in rows if r[3] == "full"]
    for pool in (full, rows):
        if not pool:
            continue
        same = [r for r in pool if r[2] == pos]
        if same:
            return same[0][0]
        ending = next((p for end, p in _FORM_POS if form.endswith(end)), None)
        # No regular ending (tore, ran, children): irregular forms are mostly verbs.
        for p in (ending, "verb") if ending else ("verb",):
            hit = [r for r in pool if r[2] == p]
            if hit:
                return hit[0][0]
        return pool[0][0]
    return None


def plan(rows: list[tuple], flags: dict) -> tuple[dict, list[dict], collections.Counter]:
    """rows: (id, normalized, pos, status, cefr). Pure, for tests."""
    by_key = {f"{r[1]}|{r[2]}": r for r in rows}
    by_word = collections.defaultdict(list)
    for r in rows:
        by_word[r[1]].append(r)
    decisions = {"redirect": {}, "strip_cefr": [], "set_cefr": {}}
    log, counts = [], collections.Counter()
    for key, hit in sorted(flags.items()):
        r = by_key.get(key)
        if not r:
            counts["not_in_db"] += 1
            continue
        lid, word, pos, status, cefr = r
        if "inflected_form" in hit:
            base = pick_base(by_word.get(hit["inflected_form"], []), word, pos)
            if base and base != lid:
                decisions["redirect"][str(lid)] = base
                counts["redirect"] += 1
                log.append({"id": lid, "word": word, "pos": pos, "action": "redirect",
                            "to": base, "lemma": hit["inflected_form"], "cefr_before": cefr})
                continue
            counts["redirect_no_lemma_strip"] += 1  # lemma not in the lexicon
            decisions["strip_cefr"].append(lid)
            log.append({"id": lid, "word": word, "pos": pos, "action": "strip_cefr",
                        "why": "inflected_form without lemma entry", "cefr_before": cefr})
            continue
        if any(k in hit for k in EXCLUDE):
            decisions["strip_cefr"].append(lid)
            counts["strip_cefr"] += 1
            log.append({"id": lid, "word": word, "pos": pos, "action": "strip_cefr",
                        "rules": [k for k in hit if k in EXCLUDE], "cefr_before": cefr})
            continue
        for rule in LEVEL_RULES:
            if rule in hit:
                level, ambiguous = suggested_level(rule, hit[rule])
                decisions["set_cefr"][str(lid)] = level
                counts["set_cefr"] += 1
                counts["set_cefr_ambiguous"] += ambiguous
                log.append({"id": lid, "word": word, "pos": pos, "action": "set_cefr", "rule": rule,
                            "from": cefr, "to": level, "ambiguous": ambiguous, "detail": hit[rule]})
                break
    return decisions, log, counts


def main(argv: list[str]) -> None:
    out = HOME / "exports" / "quality"
    out.mkdir(parents=True, exist_ok=True)
    if "--restore" in argv:
        backup = json.loads(Path(argv[argv.index("--restore") + 1]).read_text(encoding="utf-8"))
        with db.session_scope() as s:
            s.execute(text("DELETE FROM lexeme_redirects"))
            for old, new in backup["lexeme_redirects"]:
                s.execute(text("INSERT INTO lexeme_redirects (old_id, new_id) VALUES (:o, :n)"),
                          {"o": old, "n": new})
            s.execute(text("UPDATE lexemes SET cefr = :c WHERE id = :i"),
                      [{"i": i, "c": c} for i, c in backup["lexeme_cefr"]])
        (quality.QUALITY_DIR / "decisions.json").unlink(missing_ok=True)
        print("restored", len(backup["lexeme_cefr"]), "lexemes,",
              len(backup["lexeme_redirects"]), "redirects; decisions.json removed")
        return
    flags = quality.load_json("entry_flags.json")
    with db.session_scope() as s:
        rows = [tuple(r) for r in s.execute(text(
            "SELECT id, normalized, pos, status, cefr FROM lexemes ORDER BY id"))]
        decisions, log, counts = plan(rows, flags)
        print(json.dumps(dict(counts), ensure_ascii=False))
        if "--dry-run" in argv:
            return
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = {"created": stamp, "lexeme_cefr": [[r[0], r[4]] for r in rows],
                  "lexeme_redirects": [list(r) for r in s.execute(
                      text("SELECT old_id, new_id FROM lexeme_redirects ORDER BY old_id"))]}
        bpath = out / f"backup-191-{stamp}.json"
        bpath.write_text(json.dumps(backup), encoding="utf-8")
        existing = {r[0] for r in backup["lexeme_redirects"]}
        new = [{"o": int(k), "n": v} for k, v in decisions["redirect"].items() if int(k) not in existing]
        if new:
            s.execute(text("INSERT INTO lexeme_redirects (old_id, new_id) VALUES (:o, :n)"), new)
        s.execute(text("UPDATE lexemes SET cefr = NULL WHERE id = ANY(:i)"),
                  {"i": [int(k) for k in decisions["redirect"]] + decisions["strip_cefr"]})
        for level in quality.LEVELS:
            ids = [int(k) for k, v in decisions["set_cefr"].items() if v == level]
            if ids:
                s.execute(text("UPDATE lexemes SET cefr = :c WHERE id = ANY(:i)"), {"c": level, "i": ids})
    (quality.QUALITY_DIR / "decisions.json").write_text(
        json.dumps(decisions, ensure_ascii=False, sort_keys=True, indent=0), encoding="utf-8")
    (out / f"decisions-191-{stamp}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=0), encoding="utf-8")
    print("backup:", bpath)


if __name__ == "__main__":
    main(sys.argv[1:])