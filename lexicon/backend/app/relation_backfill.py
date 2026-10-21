"""Relation-word meanings filled after the related word enters the lexicon
(問題回報 #462, card #468).

A headword's ``*_native`` value (related_native, synonyms_native …,
derived_native_meaning) takes each relation word's Chinese from
LexiconLookup. When the relation word was not a full entry yet, its slot
stayed in ``missing`` for good: the headword's value was never recomputed
once the word came in (secrete → secret, cold → could).

- ``backfill_for_word`` runs from ``pipeline.process_word`` right after a
  word is materialized: every headword still waiting for that word gets
  its slot filled (field_values + relation_translations, no AI).
- ``backfill_all`` / ``sync_relation_translations`` are the one-off sweep
  (``lexicon/tools/card468_backfill.py``).
"""
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from . import catalog
from . import models as m
from .adapters import Context
from .adapters.local import LexiconLookup
from .text import normalize_lemma

FIELDS = {**catalog.RELATION_NATIVE, "derived_native_meaning": "derived_terms"}


def _postgres(s: Session) -> bool:
    return s.bind is not None and s.bind.dialect.name == "postgresql"


def waiting_rows(s: Session, target: str, keys: set[str] | None = None):
    """``*_native`` rows whose ``missing`` still names a relation word (all of
    them, or only the words in [keys] — slots are the word lowercased)."""
    q = """SELECT id, lemma, native_language, field, status, items, missing FROM field_values
           WHERE target_language = :t AND field = ANY(:f)
             AND jsonb_array_length(COALESCE(missing, '[]'::jsonb)) > 0"""
    p: dict = {"t": target, "f": list(FIELDS)}
    if keys is not None:
        q += " AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(missing) e" \
             " WHERE lower(e) = ANY(:k))"
        p["k"] = sorted(keys)
    return s.execute(sql_text(q), p).all()


def _relation_item(s: Session, target: str, head: str, rel: str, word: str) -> dict:
    """The headword's own relation item for [word] (its part of speech picks
    the lexeme, as resolve_field would)."""
    for fv in s.execute(select(m.FieldValue).where(
            m.FieldValue.target_language == target, m.FieldValue.lemma == head,
            m.FieldValue.field == rel)).scalars():
        for it in fv.items or []:
            if (it.get("word") or "").lower() == word.lower():
                return dict(it)
    return {"word": word}


def fill_row(s: Session, target: str, row, is_full, lookup: LexiconLookup | None = None,
             backup: dict | None = None, write: bool = True) -> list[dict]:
    """Fill the slots of one ``*_native`` row whose words [is_full] says are
    entries now. Returns the items added; with [write] they go into the row
    (status / missing recomputed) and into relation_translations. [backup]
    collects the row's old value and the inserted translation ids."""
    from . import pipeline
    lookup = lookup or LexiconLookup()
    rel = FIELDS[row.field]
    words = [str(w) for w in (row.missing or []) if is_full(str(w))]
    if not words:
        return []
    ctx = Context(target, row.native_language, row.lemma, row.lemma, session=s, resolved={
        rel: [_relation_item(s, target, row.lemma, rel, w) for w in words]})
    new = [dict(c.value, key=c.value["slot"], source="lexicon", confidence=1.0)
           for c in lookup.normalize(row.field, None, ctx)]
    added = [{"head": row.lemma, "native": row.native_language, "field": row.field,
              "word": i["word"], "text": i["text"]} for i in new]
    if not new or not write:
        return added
    items = list(row.items or []) + new
    status, missing = pipeline.drop_filled_missing(row.field, row.status, list(row.missing or []),
                                                   items)
    if backup is not None:
        backup.setdefault("field_values", []).append(
            {"id": row.id, "items": row.items, "status": row.status, "missing": row.missing})
    s.execute(update(m.FieldValue).where(m.FieldValue.id == row.id)
              .values(items=items, status=status, missing=missing))
    for i in new:
        for rel_id in s.execute(
                select(m.LexemeRelation.id)
                .join(m.Lexeme, m.Lexeme.id == m.LexemeRelation.lexeme_id)
                .where(m.Lexeme.language == target, m.Lexeme.normalized == row.lemma,
                       m.LexemeRelation.relation == rel,
                       func.lower(m.LexemeRelation.target_word) == i["word"].lower())).scalars():
            if s.execute(select(m.RelationTranslation.id).where(
                    m.RelationTranslation.relation_id == rel_id,
                    m.RelationTranslation.native_language == row.native_language)).first():
                continue
            rt = m.RelationTranslation(relation_id=rel_id, native_language=row.native_language,
                                       text=i["text"], source="lexicon", is_ai=False)
            s.add(rt)
            s.flush()
            if backup is not None:
                backup.setdefault("inserted_rt", []).append(rt.id)
    return added


def backfill_for_word(s: Session, target: str, lemma: str) -> list[dict]:
    """After [lemma] (normalized) became a full entry: fill the slot of every
    headword whose relation meaning was still waiting for it."""
    if not _postgres(s):
        return []
    if not s.execute(select(m.Lexeme.id).where(
            m.Lexeme.language == target, m.Lexeme.normalized == lemma,
            m.Lexeme.status == "full")).first():
        return []
    rows = waiting_rows(s, target, {lemma.lower()})
    if not rows:
        return []
    lookup, out = LexiconLookup(), []
    for row in rows:
        out += fill_row(s, target, row, lambda w: normalize_lemma(w, target) == lemma, lookup)
    return out


def backfill_all(s: Session, target: str, backup: dict | None = None,
                 write: bool = True) -> list[dict]:
    """The sweep: every waiting slot whose word is a full entry now."""
    full = {r[0] for r in s.execute(select(m.Lexeme.normalized).where(
        m.Lexeme.language == target, m.Lexeme.status == "full").distinct())}
    lookup, out = LexiconLookup(), []
    for row in waiting_rows(s, target):
        out += fill_row(s, target, row, lambda w: normalize_lemma(w, target) in full, lookup,
                        backup, write)
    return out


def sync_relation_translations(s: Session, target: str, native: str,
                               backup: dict | None = None, write: bool = True) -> list[dict]:
    """Relations of full headwords whose field_values item has the Chinese but
    whose relation_translations row is missing (the row is written only when
    the headword is materialized again): insert it."""
    gaps = s.execute(sql_text("""
        SELECT lr.id, l.normalized AS head, lr.relation, lower(lr.target_word) AS w
        FROM lexeme_relations lr JOIN lexemes l ON l.id = lr.lexeme_id
        LEFT JOIN relation_translations rt ON rt.relation_id = lr.id AND rt.native_language = :n
        WHERE l.language = :t AND l.status = 'full' AND rt.id IS NULL"""),
        {"t": target, "n": native}).all()
    if not gaps:
        return []
    from .adapters.ai import same_gloss_key
    rel_field = {v: k for k, v in FIELDS.items()}
    want, head_zh = {}, {}
    for fv in s.execute(sql_text("""
            SELECT lemma, field, items FROM field_values
            WHERE target_language = :t AND native_language = :n
              AND (field = ANY(:f) OR field = 'native_definition') AND lemma = ANY(:h)"""),
            {"t": target, "n": native, "f": list(FIELDS),
             "h": sorted({g.head for g in gaps})}):
        if fv.field == "native_definition":
            head_zh[fv.lemma] = {same_gloss_key(i.get("text")) for i in fv.items or []} - {""}
            continue
        for it in fv.items or []:
            if (it.get("text") or "").strip():
                want[(fv.lemma, FIELDS[fv.field], (it.get("word") or it.get("slot") or "").lower())] = it
    out = []
    for g in gaps:
        it = want.get((g.head, g.relation, g.w))
        # A meaning copied from the headword (beef → kick 牛肉) is wrong data,
        # not a translation to spread (#447); left for the exporter to hide.
        if it is None or same_gloss_key(it["text"]) in head_zh.get(g.head, set()):
            continue
        out.append({"head": g.head, "native": native, "field": rel_field[g.relation],
                    "word": it.get("word"), "text": it["text"]})
        if not write:
            continue
        rt = m.RelationTranslation(relation_id=g.id, native_language=native, text=it["text"],
                                   source=it.get("source") or "", is_ai=bool(it.get("ai")))
        s.add(rt)
        s.flush()
        if backup is not None:
            backup.setdefault("inserted_rt", []).append(rt.id)
    return out
