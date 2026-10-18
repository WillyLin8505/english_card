"""Give back translations wrongly rejected as Simplified (問題回報 #24).

text.looks_simplified compared a whole OpenCC conversion character by
character, so Traditional text OpenCC would respell (工作台, 岩壁, 染污, 家具)
counted as Simplified and the translation was dropped. The rule now goes by
OpenCC's character tables; this applies it to candidates already stored.

Surgical, like a manual edit: each candidate rejected as 「簡體字」 that the
current rules accept is marked valid (its text in Taiwan usage), and fills
its slot only where the stored value has none (a related word, sense or
example still without Chinese). Slots already filled stay exactly as they
are, nothing is fetched and no AI is called; then the headword's projection
is refreshed. A snapshot of every row it changes is written first; --restore
puts it back.

    python tools/revalidate_taiwan_text.py --dry-run
    python tools/revalidate_taiwan_text.py --words spotted,bench
    python tools/revalidate_taiwan_text.py            # every headword
    python tools/revalidate_taiwan_text.py --restore raw-data/snapshots/<file>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))

from sqlalchemy import delete, select, text  # noqa: E402

from app import db, models as m, policies  # noqa: E402
from app.adapters import ADAPTERS, Candidate, Context  # noqa: E402
from app.adapters.base import localize  # noqa: E402
from app.materialize import materialize  # noqa: E402
from app.pipeline import expected_slots, item_of, load_existing  # noqa: E402

SNAPSHOTS = HOME / "raw-data" / "snapshots"
COLUMNS = {model: [c.name for c in model.__table__.columns]
           for model in (m.FieldValue, m.FieldCandidate, m.FieldProvenance, m.SourceLookup)}
DONE = {"partial", "missing", "short"}


def _display(s, target: str, lemma: str) -> str:
    row = s.execute(select(m.Lexeme.lemma).where(
        m.Lexeme.language == target, m.Lexeme.normalized == lemma).limit(1)).first()
    return row[0] if row else lemma


def _native(row) -> str:
    return row.native_language if row.native_language != "*" else "zh-TW"


def _plain(row) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in ((c, getattr(row, c)) for c in COLUMNS[type(row)])}


def _candidate(r) -> Candidate:
    return Candidate(r.field, r.language, dict(r.value or {}), r.item_key, source=r.source,
                     slot=r.slot, confidence=r.confidence, snapshot_id=r.snapshot_id)


def fixable(s, target: str, words: set[str] | None) -> dict[str, dict[str, list]]:
    """{lemma: {field: [(row, localized candidate)]}} the current rules accept."""
    query = select(m.FieldCandidate).where(
        m.FieldCandidate.target_language == target, m.FieldCandidate.valid.is_(False),
        m.FieldCandidate.invalid_reason.like("簡體字%")).order_by(m.FieldCandidate.id)
    if words:
        query = query.where(m.FieldCandidate.lemma.in_(sorted(words)))
    out: dict[str, dict[str, list]] = {}
    for r in s.execute(query).scalars():
        ctx = Context(target, _native(r), r.lemma, r.lemma)
        c = _candidate(r)
        localize(c, ctx)
        if r.source in ADAPTERS and ADAPTERS[r.source].validate(c, ctx) is None:
            out.setdefault(r.lemma, {}).setdefault(r.field, []).append((r, c))
    return out


def run(target: str, words: set[str] | None, dry_run: bool) -> None:
    with db.SessionLocal() as s:
        found = fixable(s, target, words)
        run_policies: dict[str, dict] = {}
        snapshot = {"target": target, "made_at": datetime.now().isoformat(), "lemmas": {}}
        made_valid = filled = 0
        for lemma, by_field in sorted(found.items()):
            native = _native(next(iter(by_field.values()))[0][0])
            if native not in run_policies:
                run_policies[native] = policies.load_for_run(s, target, native)
            ctx = Context(target, native, lemma, _display(s, target, lemma), session=s)
            load_existing(s, ctx)
            saved = snapshot["lemmas"][lemma] = {"values": [], "candidates": [], "provenance": []}
            report = []
            for field, rows in sorted(by_field.items()):
                fv = s.execute(select(m.FieldValue).where(
                    m.FieldValue.target_language == target, m.FieldValue.lemma == lemma,
                    m.FieldValue.native_language == native, m.FieldValue.field == field)
                ).scalar_one_or_none()
                saved["candidates"] += [_plain(r) for r, _ in rows]
                if fv is not None:
                    saved["values"].append(_plain(fv))
                    saved["provenance"] += [_plain(p) for p in s.execute(select(
                        m.FieldProvenance).where(m.FieldProvenance.field_value_id == fv.id)
                    ).scalars()]
                policy, steps = run_policies[native].get(field, (None, []))
                position = {st.source: st.position for st in steps}
                expected = expected_slots(field, ctx)
                have = {i.get("slot") for i in (fv.items if fv else [])}
                items, added = list(fv.items) if fv else [], {}
                for r, c in sorted(rows, key=lambda rc: (position.get(rc[0].source, 99999),
                                                         rc[0].id)):
                    made_valid += 1
                    if not dry_run:
                        r.valid, r.invalid_reason = True, None
                        r.value, r.item_key = c.value, c.key[:500]
                    slot_free = c.slot not in have or added.get(c.slot) == r.source
                    if fv is None or not slot_free or (expected is not None
                                                       and c.slot not in expected):
                        continue  # the slot is filled already, or no longer wanted
                    if any(i.get("key") == c.key and i.get("slot") == c.slot for i in items):
                        continue
                    added[c.slot] = r.source
                    items.append(item_of(c))
                    report.append(f"{field}[{c.slot}] {c.value.get('text') or c.value.get('gloss')}")
                    if not dry_run:
                        s.add(m.FieldProvenance(
                            field_value_id=fv.id, candidate_id=r.id, source=r.source,
                            item_key=c.key[:500], snapshot_id=r.snapshot_id,
                            strategy=policy.strategy if policy else "",
                            position=position.get(r.source, 0)))
                if added and not dry_run:
                    fv.items = items
                    fv.missing = [x for x in (fv.missing or []) if x not in added]
                    if fv.status in DONE and not fv.missing:
                        fv.status = "complete"
                filled += len(added)
            print(f"{lemma}: {sum(map(len, by_field.values()))} 筆恢復有效，補上 {len(report)} 個空位 "
                  f"{report[:4]}", flush=True)
            if not dry_run:
                s.flush()
                s.execute(text("SELECT pg_advisory_xact_lock(770000002)"))
                materialize(s, target, lemma, _display(s, target, lemma))
                s.commit()
        print(f"{len(found)} headwords: {made_valid} candidates "
              f"{'would be ' if dry_run else ''}made valid, {filled} empty slots filled")
        if not dry_run and found:
            SNAPSHOTS.mkdir(parents=True, exist_ok=True)
            path = SNAPSHOTS / f"taiwan_text_{datetime.now():%Y%m%d-%H%M%S}.json"
            path.write_text(json.dumps(snapshot, ensure_ascii=False, default=str),
                            encoding="utf-8")
            print(f"snapshot: {path}")


def _when(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def restore(path: Path) -> None:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    target = snapshot["target"]
    with db.SessionLocal() as s:
        s.execute(text("SELECT pg_advisory_xact_lock(770000002)"))
        run_policies: dict[str, dict] = {}
        for lemma, saved in snapshot["lemmas"].items():
            fields = {c["field"] for c in saved["candidates"]}
            if "provenance" not in saved:
                # An early snapshot (whole fields re-resolved): the fields'
                # candidates come back whole and provenance is rebuilt below.
                s.execute(delete(m.FieldCandidate).where(
                    m.FieldCandidate.target_language == target, m.FieldCandidate.lemma == lemma,
                    m.FieldCandidate.field.in_(sorted(fields))))
                s.flush()
            for c in saved["candidates"]:
                c = {**c, "retrieved_at": _when(c.get("retrieved_at"))}
                row = s.get(m.FieldCandidate, c["id"])
                if row is None:
                    s.add(m.FieldCandidate(**c))
                else:
                    for k, v in c.items():
                        setattr(row, k, v)
            for lk in saved.get("lookups", []):
                row = s.execute(select(m.SourceLookup).where(
                    m.SourceLookup.target_language == target, m.SourceLookup.lemma == lemma,
                    m.SourceLookup.native_language == lk["native_language"],
                    m.SourceLookup.field == lk["field"],
                    m.SourceLookup.source == lk["source"])).scalar_one_or_none()
                if row is not None:
                    row.status, row.count, row.error = lk["status"], lk["count"], lk["error"]
            s.flush()
            for v in saved["values"]:
                fv = s.get(m.FieldValue, v["id"])
                if fv is None or v["field"] not in fields:
                    continue
                fv.items, fv.status, fv.missing = v["items"], v["status"], v["missing"]
                s.execute(delete(m.FieldProvenance).where(
                    m.FieldProvenance.field_value_id == fv.id))
                if "provenance" in saved:
                    for p in saved["provenance"]:
                        if p["field_value_id"] == fv.id:
                            s.add(m.FieldProvenance(**{**p, "processed_at": _when(
                                p.get("processed_at"))}))
                    continue
                native = fv.native_language
                if native not in run_policies:
                    run_policies[native] = policies.load_for_run(s, target, native)
                policy, steps = run_policies[native].get(fv.field, (None, []))
                position = {st.source: st.position for st in steps}
                for item in fv.items or []:
                    cand = s.execute(select(m.FieldCandidate).where(
                        m.FieldCandidate.target_language == target,
                        m.FieldCandidate.lemma == lemma, m.FieldCandidate.field == fv.field,
                        m.FieldCandidate.source == item.get("source"),
                        m.FieldCandidate.item_key == str(item.get("key", ""))[:500])
                    ).scalars().first()
                    s.add(m.FieldProvenance(
                        field_value_id=fv.id, candidate_id=cand.id if cand else None,
                        source=item.get("source", ""), item_key=str(item.get("key", ""))[:500],
                        snapshot_id=cand.snapshot_id if cand else None,
                        strategy=policy.strategy if policy else "",
                        position=position.get(item.get("source"), 0)))
            s.flush()
            materialize(s, target, lemma, _display(s, target, lemma))
        s.commit()
    print(f"restored {len(snapshot['lemmas'])} headwords")


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
