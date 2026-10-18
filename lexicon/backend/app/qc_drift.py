"""Database checks that the app pack cannot see (問題回報 #281).

materialize builds one full lexeme per part of speech from the adopted
`pos` / `definition` values. When the two disagree, the next re-run of the
word silently adds (or redirects) lexemes, e.g. a "new duplicate" marine.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import pos_exclusions


def pos_without_lexeme(s: Session, language: str = "en") -> dict[str, list[str]]:
    """lemma → parts of speech its values name but no full lexeme has.

    Only words that already have a full lexeme count (a word not yet
    materialized at all is an import gap, not drift)."""
    from .materialize import poses_with_senses
    values: dict[str, dict[str, list]] = defaultdict(lambda: {"pos": [], "definition": []})
    for lemma, field, items in s.execute(select(
            m.FieldValue.lemma, m.FieldValue.field, m.FieldValue.items).where(
            m.FieldValue.target_language == language,
            m.FieldValue.field.in_(("pos", "definition")))):
        values[lemma][field].extend(i for i in items or [] if isinstance(i, dict))
    want: dict[str, set[str]] = {}
    for lemma, by_field in values.items():
        gone = pos_exclusions.excluded(language, lemma)  # materialize skips them (#284)
        # … and builds no lexeme for a part of speech without senses (#303)
        want[lemma] = set(poses_with_senses(
            [i for i in by_field["pos"] if i.get("pos") not in gone],
            [i for i in by_field["definition"] if i.get("pos") not in gone]))
    have: dict[str, set[str]] = defaultdict(set)
    for norm, pos in s.execute(select(m.Lexeme.normalized, m.Lexeme.pos).where(
            m.Lexeme.language == language, m.Lexeme.status == "full")):
        have[norm].add(pos)
    return {w: sorted(p - have[w]) for w, p in sorted(want.items())
            if w in have and p - have[w]}


def excluded_pos_present(s: Session, language: str = "en") -> dict[str, list[str]]:
    """lemma → excluded parts of speech (quality/excluded_pos.json) that still
    have a full lexeme: the exclusion is not in effect for them yet."""
    rules = pos_exclusions.load().get(language, {})
    if not rules:
        return {}
    out: dict[str, list[str]] = defaultdict(list)
    for norm, pos in s.execute(select(m.Lexeme.normalized, m.Lexeme.pos).where(
            m.Lexeme.language == language, m.Lexeme.status == "full",
            m.Lexeme.normalized.in_(list(rules)))):
        if pos in rules[norm]:
            out[norm].append(pos)
    return {w: sorted(p) for w, p in sorted(out.items())}


def metrics(s: Session, language: str = "en") -> tuple[dict, dict]:
    """`v.*` counts for qc snapshots (a rise is a regression) and samples."""
    drift = pos_without_lexeme(s, language)
    shown = excluded_pos_present(s, language)
    return ({"v.entry.pos_not_materialized": len(drift),
             "v.entry.excluded_pos_present": len(shown)},
            {"entry.pos_not_materialized": list(drift.items())[:20],
             "entry.excluded_pos_present": list(shown.items())[:20]})
