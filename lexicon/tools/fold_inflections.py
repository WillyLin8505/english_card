"""Fold inflected forms into their words (問題回報 #51).

Photo words such as runs, climbs or stands were imported as headwords of
their own, with "third-person singular of run" as their only meaning and no
Chinese. The pipeline now imports run instead (adapters.base.
inflection_bases), and a form that is also a word of its own (lying 說謊的,
tethered) loses only its form-only part of speech (adapters.kaikki.
inflection_only_pos). This applies both to stored headwords:

- a pure form (runs) is removed, and its word (run) is imported if it is
  still only a stub;
- a form that is also a word (lying) has its parts of speech, definitions and
  example senses resolved again from the local Kaikki index, and its word (lie)
  is imported if it is still a stub.

Words are imported without AI (ai_translate is left out, so those gaps stay
open for a later 缺值補齊) and without pictures. A snapshot of every row
touched is written first; --restore puts it back.

    python tools/fold_inflections.py --dry-run
    python tools/fold_inflections.py --words runs,lying
    python tools/fold_inflections.py --restore raw-data/snapshots/<file>.json
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

from app import catalog, db, kaikki_index, models as m  # noqa: E402
from app.adapters import ADAPTERS  # noqa: E402
from app.adapters.base import inflection_bases, zipf  # noqa: E402
from app.adapters.kaikki import inflection_only_pos  # noqa: E402
from app.materialize import materialize  # noqa: E402
from app.pipeline import AUTO_IMAGE_FIELDS, field_order, process_word, remove_word  # noqa: E402

SNAPSHOTS = HOME / "raw-data" / "snapshots"
TABLES = (m.FieldValue, m.FieldCandidate, m.SourceLookup, m.MissingLexemeRequest)
NO_AI = [k for k in catalog.SOURCES if k != "ai_translate"]
AI_CALLS = []


def _no_ai():
    ai = ADAPTERS["ai_translate"]
    ai.lookup = lambda field_key, ctx: AI_CALLS.append((ctx.lemma, field_key)) or []
    ai.prefetch = lambda ctx, fields: AI_CALLS.append((ctx.lemma, tuple(fields))) or 0


def _plain(row) -> dict:
    return {c.name: (v.isoformat() if hasattr(v, "isoformat") else v)
            for c in row.__table__.columns for v in [getattr(row, c.name)]}


def _snapshot(s, target: str, lemma: str) -> dict:
    out = {"lexemes": [_plain(r) for r in s.execute(select(m.Lexeme).where(
        m.Lexeme.language == target, m.Lexeme.normalized == lemma)).scalars()]}
    for model in TABLES:
        out[model.__tablename__] = [_plain(r) for r in s.execute(select(model).where(
            model.target_language == target, model.lemma == lemma)).scalars()]
    out["wordlists"] = [wl.id for wl in s.execute(select(m.Wordlist).where(
        m.Wordlist.language == target)).scalars() if lemma in wl.words]
    return out


def _full(s, target: str, lemma: str) -> bool:
    return s.execute(select(m.Lexeme.id).where(
        m.Lexeme.language == target, m.Lexeme.normalized == lemma,
        m.Lexeme.status == "full")).first() is not None


def _summary(s, target: str, lemma: str) -> str:
    rows = s.execute(select(m.Lexeme.pos, m.Lexeme.status).where(
        m.Lexeme.language == target, m.Lexeme.normalized == lemma)).all()
    return ", ".join(f"{p}:{st}" for p, st in rows) or "—"


def plan(s, target: str, words: set[str] | None) -> tuple[list, list, list]:
    """(pure forms with their words, forms that are also words with the
    words of their form-only parts of speech, words to import)."""
    q = select(m.Lexeme.normalized).where(m.Lexeme.language == target,
                                          m.Lexeme.status == "full").distinct()
    pure, mixed, imports = [], [], []
    for w in sorted(set(s.execute(q).scalars())):
        if " " in w or (words and w not in words):
            continue
        bases = inflection_bases(w, target)
        if bases:
            pure.append((w, bases))
            imports += [b for b in bases if not _full(s, target, b)]
            continue
        entries = [e for e in kaikki_index.lookup(target, w) or []
                   if str(e.get("word", "")).lower() == w]
        only = inflection_only_pos(entries)
        poses = set(s.execute(select(m.Lexeme.pos).where(
            m.Lexeme.language == target, m.Lexeme.normalized == w,
            m.Lexeme.status == "full")).scalars())
        if only & poses:
            of = [str(f.get("word") or "") for e in entries if e.get("pos") in only
                  for sense in e.get("senses") or [] for f in sense.get("form_of") or []]
            # In use (lie, not lye: lying is also lye's rare past participle).
            of = [b for b in dict.fromkeys(of)
                  if b and b == b.lower() and b != w and zipf(b, target) >= 3.5]
            mixed.append((w, sorted(only & poses), of))
            imports += [b for b in of if not _full(s, target, b)]
    return pure, mixed, list(dict.fromkeys(imports))


def run(target: str, native: str, words: set[str] | None, dry_run: bool) -> None:
    _no_ai()
    with db.SessionLocal() as s:
        pure, mixed, imports = plan(s, target, words)
        print(f"pure forms ({len(pure)}): {pure}")
        print(f"forms that are also words ({len(mixed)}): {mixed}")
        print(f"words to import ({len(imports)}): {imports}")
        if dry_run:
            return
        snapshot = {"target": target, "made_at": datetime.now().isoformat(), "lemmas": {
            w: _snapshot(s, target, w)
            for w in [*(p for p, _ in pure), *(x for x, *_ in mixed), *imports]}}
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        path = SNAPSHOTS / f"fold_inflections_{datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"snapshot: {path}", flush=True)
        fields = [f for f in field_order(target) if f not in AUTO_IMAGE_FIELDS]
        for base in imports:
            process_word(s, target, native, base, fields, "fill_missing", sources=NO_AI,
                         as_inflection=False)
            s.commit()
            print(f"imported {base}: {_summary(s, target, base)}", flush=True)
        for w, _ in pure:
            s.execute(text("SELECT pg_advisory_xact_lock(770000002)"))
            remove_word(s, target, w)
            s.commit()
            print(f"removed {w}", flush=True)
        for w, *_ in mixed:
            # Forms too: standing the verb listed stands, which belongs to stand.
            process_word(s, target, native, w,
                         ["pos", "definition", "example_sense", *catalog.FORM_FIELDS],
                         "force_refresh", sources=["kaikki", "local_calc"], as_inflection=False)
            s.commit()
            print(f"{w}: {_summary(s, target, w)}", flush=True)
    print(f"AI requests: {len(AI_CALLS)}")


def _when(v):
    return datetime.fromisoformat(v) if isinstance(v, str) and len(v) >= 19 and v[4] == "-" \
        else v


def restore(path: Path) -> None:
    saved = json.loads(path.read_text(encoding="utf-8"))
    target = saved["target"]
    with db.SessionLocal() as s:
        s.execute(text("SELECT pg_advisory_xact_lock(770000002)"))
        for lemma, rows in saved["lemmas"].items():
            remove_word(s, target, lemma)
            s.flush()
            for model in TABLES:
                for r in rows[model.__tablename__]:
                    s.add(model(**{k: _when(v) if k.endswith("_at") else v
                                   for k, v in r.items()}))
            for r in rows["lexemes"]:
                s.add(m.Lexeme(**{k: _when(v) if k.endswith("_at") else v for k, v in r.items()}))
            s.flush()
            for wl in s.execute(select(m.Wordlist).where(
                    m.Wordlist.id.in_(rows["wordlists"]))).scalars():
                if lemma not in wl.words:
                    wl.words = [*wl.words, lemma]
            materialize(s, target, lemma)
        s.commit()
    print(f"restored {len(saved['lemmas'])} headwords")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", default="en")
    ap.add_argument("--native", default="zh-TW")
    ap.add_argument("--words", help="comma-separated headwords (default: all)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", type=Path)
    args = ap.parse_args()
    if args.restore:
        restore(args.restore)
        return
    words = {w.strip().lower() for w in args.words.split(",")} if args.words else None
    run(args.target, args.native, words, args.dry_run)


if __name__ == "__main__":
    main()
