"""Take proper nouns out of stored relation words (問題回報 #22).

base.validate now rejects a relation word that the Kaikki index lists only as
a name (brett-like people, places such as Antarctica, brands). This applies
the same rule to words already stored, without re-resolving anything: no
source is asked again and no AI is called.

For each affected headword it removes those words from the relation field
values, marks the matching candidates invalid (so later runs keep them out)
and refreshes the headword's projection (materialize). A snapshot of every
changed row is written first; --restore puts it back.

    python tools/remove_proper_noun_relations.py --dry-run
    python tools/remove_proper_noun_relations.py --words bread,terrace
    python tools/remove_proper_noun_relations.py            # every headword
    python tools/remove_proper_noun_relations.py --restore raw-data/snapshots/<file>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))

from sqlalchemy import select, text  # noqa: E402

from app import catalog, db, models as m  # noqa: E402
from app.adapters.base import is_proper_noun  # noqa: E402
from app.materialize import materialize  # noqa: E402

FIELDS = [*catalog.RELATION_FIELDS, "derived_terms"]
REASON = "專有名詞（人名、地名、品牌），不收為關係詞"
SNAPSHOTS = HOME / "raw-data" / "snapshots"


def _display(s, target: str, lemma: str) -> str:
    row = s.execute(select(m.Lexeme.lemma).where(
        m.Lexeme.language == target, m.Lexeme.normalized == lemma).limit(1)).first()
    return row[0] if row else lemma


def _counts(s, target: str, lemma: str) -> dict:
    return dict(s.execute(text("""
        SELECT 'relations', count(*) FROM lexeme_relations r JOIN lexemes l ON l.id = r.lexeme_id
         WHERE l.language = :t AND l.normalized = :w
        UNION ALL
        SELECT 'translations', count(*) FROM relation_translations rt
          JOIN lexeme_relations r ON r.id = rt.relation_id JOIN lexemes l ON l.id = r.lexeme_id
         WHERE l.language = :t AND l.normalized = :w"""), {"t": target, "w": lemma}).all())


def affected(s, target: str, words: set[str] | None) -> dict[str, list[m.FieldValue]]:
    out: dict[str, list[m.FieldValue]] = {}
    query = select(m.FieldValue).where(m.FieldValue.target_language == target,
                                       m.FieldValue.field.in_(FIELDS))
    if words:
        query = query.where(m.FieldValue.lemma.in_(sorted(words)))
    for fv in s.execute(query).scalars():
        if any(is_proper_noun(str(i.get("word", "")), target) for i in fv.items or []):
            out.setdefault(fv.lemma, []).append(fv)
    return out


def run(target: str, words: set[str] | None, dry_run: bool) -> None:
    with db.SessionLocal() as s:
        found = affected(s, target, words)
        snapshot = {"target": target, "made_at": datetime.now().isoformat(), "values": [],
                    "candidates": []}
        removed_total = 0
        for lemma, values in sorted(found.items()):
            before = _counts(s, target, lemma)
            removed = []
            if not dry_run:
                # The same lock as pipeline.process_word's projection phase.
                s.execute(text("SELECT pg_advisory_xact_lock(770000002)"))
            for fv in values:
                snapshot["values"].append({"id": fv.id, "lemma": lemma, "field": fv.field,
                                           "items": fv.items, "status": fv.status})
                keep = [i for i in fv.items if not is_proper_noun(str(i.get("word", "")), target)]
                removed += [(fv.field, i.get("word")) for i in fv.items if i not in keep]
                if not dry_run:
                    fv.items = keep
            for c in s.execute(select(m.FieldCandidate).where(
                    m.FieldCandidate.target_language == target, m.FieldCandidate.lemma == lemma,
                    m.FieldCandidate.field.in_(FIELDS), m.FieldCandidate.valid.is_(True))).scalars():
                if is_proper_noun(str((c.value or {}).get("word", "")), target):
                    snapshot["candidates"].append({"id": c.id, "valid": c.valid,
                                                   "invalid_reason": c.invalid_reason})
                    if not dry_run:
                        c.valid, c.invalid_reason = False, REASON
            removed_total += len(removed)
            if not dry_run:
                s.flush()
                materialize(s, target, lemma, _display(s, target, lemma))
                s.commit()
            after = _counts(s, target, lemma) if not dry_run else before
            print(f"{lemma}: -{len(removed)} {sorted({w for _, w in removed})[:8]} "
                  f"relations {before.get('relations')}→{after.get('relations')} "
                  f"translations {before.get('translations')}→{after.get('translations')}",
                  flush=True)
        print(f"{len(found)} headwords, {removed_total} relation words "
              f"{'would be ' if dry_run else ''}removed")
        if not dry_run and found:
            SNAPSHOTS.mkdir(parents=True, exist_ok=True)
            path = SNAPSHOTS / f"proper_noun_relations_{datetime.now():%Y%m%d-%H%M%S}.json"
            path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            print(f"snapshot: {path}")


def restore(path: Path) -> None:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    target = snapshot["target"]
    with db.SessionLocal() as s:
        s.execute(text("SELECT pg_advisory_xact_lock(770000002)"))
        lemmas = set()
        for v in snapshot["values"]:
            fv = s.get(m.FieldValue, v["id"])
            if fv is not None:
                fv.items, fv.status = v["items"], v["status"]
                lemmas.add(v["lemma"])
        for c in snapshot["candidates"]:
            row = s.get(m.FieldCandidate, c["id"])
            if row is not None:
                row.valid, row.invalid_reason = c["valid"], c["invalid_reason"]
        s.flush()
        for lemma in sorted(lemmas):
            materialize(s, target, lemma, _display(s, target, lemma))
        s.commit()
    print(f"restored {len(snapshot['values'])} values, {len(snapshot['candidates'])} candidates")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", default="en")
    ap.add_argument("--words", help="comma-separated headwords (default: all)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", type=Path)
    args = ap.parse_args()
    if args.restore:
        restore(args.restore)
        return
    words = {w.strip().lower() for w in args.words.split(",")} if args.words else None
    run(args.target, words, args.dry_run)


if __name__ == "__main__":
    main()
