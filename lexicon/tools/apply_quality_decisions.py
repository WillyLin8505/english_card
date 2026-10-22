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
import hashlib
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


def pick_base(rows: list[tuple], form: str, pos: str,
              eligible: set[int] | None = None) -> int | None:
    """Choose a full, eligible target, preferring matching/implied POS."""
    full = [r for r in rows if r[3] == "full" and (eligible is None or r[0] in eligible)]
    for pool in (full,):
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


def plan(rows: list[tuple], flags: dict, eligible: set[int] | None = None) -> tuple[dict, list[dict], collections.Counter]:
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
        # #194: a form with its own senses (arched 拱形的, weathered 飽經風霜的,
        # lying 說謊, found 創立) is a word of its own and never a pointer —
        # quality.inflection_base() now decides that per pos+Kaikki entry
        # (問題回報 #217/#222/#223), so a flag only reaches here when the
        # lexeme's own pos truly has no sense beyond the inflected one;
        # status=="full" is not that signal (brewed/glistening were status
        # full too) and is no longer checked.
        if "inflected_form" in hit:
            base = pick_base(by_word.get(hit["inflected_form"], []), word, pos, eligible)
            if base and base != lid:
                decisions["redirect"][str(lid)] = base
                counts["redirect"] += 1
                log.append({"id": lid, "word": word, "pos": pos, "action": "redirect",
                            "to": base, "lemma": hit["inflected_form"], "cefr_before": cefr})
                continue
            counts["redirect_no_lemma_strip"] += 1  # lemma not in the lexicon
            decisions["strip_cefr"].append(lid)
            # missing_lemma: no row at all. An existing but ineligible row
            # (stub / no Chinese) is not "待補" — the base is already here.
            log.append({"id": lid, "word": word, "pos": pos, "action": "strip_cefr",
                        "why": "inflected_form without lemma entry", "lemma": hit["inflected_form"],
                        "missing_lemma": not by_word.get(hit["inflected_form"]),
                        "cefr_before": cefr})
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


def missing_bases(log: list[dict], rows: list[tuple]) -> list[str]:
    """Base lemmas to mark 待補: the form was stripped because nothing by that
    spelling is in the lexicon. Does not invent a CEFR for the form."""
    have = {r[1] for r in rows}
    return sorted({e["lemma"] for e in log
                   if e.get("missing_lemma") and e.get("lemma") and e["lemma"] not in have})


def lint_scope(flags: dict, rows: list[tuple]) -> set[int]:
    """Legacy/stale flags cannot prove that an absent hit was evaluated."""
    scope = quality.load_json("entry_flags.scope.json")
    digest = hashlib.sha256(json.dumps(flags, sort_keys=True).encode()).hexdigest()
    if scope.get("flags_sha256") != digest:
        return set()
    keys = set(scope.get("keys", []))
    # A once-full entry may have become a stub since this export.
    # The live lint cannot establish a current negative finding for stubs.
    return {r[0] for r in rows if r[3] != "stub" and f"{r[1]}|{r[2]}" in keys}


def reconcile(s, decisions: dict, baseline: dict | None,
              evaluated_ids: set[int] | None = None,
              keep: set[int] | None = None) -> tuple[int, int]:
    """Reconcile only proven re-evaluations; carry unobserved decisions forward.

    A matching lint manifest can withdraw exclusion/inflection decisions, but
    absent level warnings cannot undo successful corrections. Redirect removal
    is limited to unchanged mappings owned by the previous decision file.
    ``keep``: lexemes whose decision belongs to another rule (card #318 spelling
    variants: calory → calorie, enquiry → inquiry) — the lint never plans them,
    so their absence from this plan is no evidence; carried forward untouched
    (card #523). Returns (cefr restored, redirects dropped); mutates decisions
    for persistence.
    """
    previous = quality.load_json("decisions.json")
    # Absence is evidence only within a verified lint scope. Persist carried
    # decisions too: otherwise the next run/re-import silently loses them.
    evaluated = (evaluated_ids or set()) - (keep or set())
    planned = ({int(k) for k in decisions["redirect"]} | set(decisions["strip_cefr"])
               | {int(k) for k in decisions["set_cefr"]})
    evaluated = evaluated | planned
    for kind in ("redirect", "strip_cefr", "set_cefr"):
        for key in previous.get(kind, [] if kind == "strip_cefr" else {}):
            # Level warnings disappear once the correction is applied. That
            # is success, not evidence that the old level should be restored.
            if int(key) in planned or (kind != "set_cefr" and int(key) in evaluated and baseline):
                continue
            if kind == "strip_cefr":
                if int(key) not in decisions[kind]:
                    decisions[kind].append(int(key))
            else:
                decisions[kind][str(key)] = previous[kind][key]
    if not baseline:
        return 0, 0
    base_cefr = {i: c for i, c in baseline["lexeme_cefr"]}
    base_red = {o for o, _ in baseline["lexeme_redirects"]}
    now = ({int(k) for k in decisions["redirect"]} | set(decisions["strip_cefr"])
           | {int(k) for k in decisions["set_cefr"]})
    before = ({int(k) for k in previous.get("redirect", {})} | set(previous.get("strip_cefr", []))
              | {int(k) for k in previous.get("set_cefr", {})})
    undo = sorted((before - now) & evaluated & base_cefr.keys())
    if undo:
        s.execute(text("UPDATE lexemes SET cefr = :c WHERE id = :i"),
                  [{"i": i, "c": base_cefr.get(i)} for i in undo if i in base_cefr])
    wanted = base_red | {int(k) for k in decisions["redirect"]}
    owned = {int(k): v for k, v in previous.get("redirect", {}).items()}
    drop = [o for o, n in s.execute(text("SELECT old_id, new_id FROM lexeme_redirects"))
            if o in evaluated and o not in wanted and owned.get(o) == n]
    if drop:
        s.execute(text("DELETE FROM lexeme_redirects WHERE old_id = ANY(:i)"), {"i": drop})
    return len(undo), len(drop)


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
        eligible = {r[0] for r in s.execute(text("""
            SELECT DISTINCT s.lexeme_id FROM senses s
            JOIN sense_translations t ON t.sense_id = s.id
            WHERE t.native_language = 'zh-TW' AND trim(t.text) <> ''
        """))}
        decisions, log, counts = plan(rows, flags, eligible)
        print(json.dumps(dict(counts), ensure_ascii=False))
        earliest = sorted(out.glob("backup-191-*.json"))
        baseline = json.loads(earliest[0].read_text(encoding="utf-8")) if earliest else None
        # Card #523: #318 spelling-variant decisions are not this lint's to withdraw.
        from card318_variants import candidates as variant_candidates  # noqa: E402 (circular at top)
        keep = {e["id"] for e in variant_candidates(s)}
        if "--dry-run" in argv:
            restored, unredirected = reconcile(s, decisions, baseline, lint_scope(flags, rows), keep)
            s.rollback()
            print(json.dumps({"restored_cefr": restored, "unredirected": unredirected,
                              "pending_base": len(missing_bases(log, rows))}))
            return
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = {"created": stamp, "lexeme_cefr": [[r[0], r[4]] for r in rows],
                  "lexeme_redirects": [list(r) for r in s.execute(
                      text("SELECT old_id, new_id FROM lexeme_redirects ORDER BY old_id"))]}
        bpath = out / f"backup-191-{stamp}.json"
        bpath.write_text(json.dumps(backup), encoding="utf-8")
        # Reconcile with the state before the first #191 run (the earliest
        # backup) so a narrower rule (#194) undoes what it no longer wants.
        restored, unredirected = reconcile(s, decisions, baseline, lint_scope(flags, rows), keep)
        counts["restored_cefr"], counts["unredirected"] = restored, unredirected
        existing = {r[0] for r in s.execute(text("SELECT old_id FROM lexeme_redirects"))}
        new = [{"o": int(k), "n": v} for k, v in decisions["redirect"].items() if int(k) not in existing]
        if new:
            s.execute(text("INSERT INTO lexeme_redirects (old_id, new_id) VALUES (:o, :n)"), new)
        s.execute(text("UPDATE lexemes SET cefr = NULL WHERE id = ANY(:i)"),
                  {"i": [int(k) for k in decisions["redirect"]] + decisions["strip_cefr"]})
        for level in quality.LEVELS:
            ids = [int(k) for k, v in decisions["set_cefr"].items() if v == level]
            if ids:
                s.execute(text("UPDATE lexemes SET cefr = :c WHERE id = ANY(:i)"), {"c": level, "i": ids})
        pending = missing_bases(log, rows)
        counts["pending_base"] = len(pending)
        if pending:
            have_req = {r[0] for r in s.execute(text(
                "SELECT lemma FROM missing_lexeme_requests WHERE target_language = 'en'"))}
            new_req = [{"lemma": w} for w in pending if w not in have_req]
            if new_req:
                s.execute(text(
                    "INSERT INTO missing_lexeme_requests "
                    "(target_language, lemma, pos, count, status) "
                    "VALUES ('en', :lemma, NULL, 1, 'open')"), new_req)
            counts["pending_base_inserted"] = len(new_req)
    (quality.QUALITY_DIR / "decisions.json").write_text(
        json.dumps(decisions, ensure_ascii=False, sort_keys=True, indent=0), encoding="utf-8")
    (out / f"decisions-191-{stamp}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=0), encoding="utf-8")
    print("backup:", bpath, json.dumps(dict(counts), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
