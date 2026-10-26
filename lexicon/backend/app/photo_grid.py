"""Photo label grid (card #645, 問題回報 #731): part of speech x CEFR.

The vision model only says what is visible and where (the tags: word, pos,
point/box). Everything else comes from the word database: each visible word
is one *concept* (``concept_id``, sharing the tag's ``anchor``), and the
database's synonyms of that word at other levels join the same concept in
their own CEFR cell - happy A1 -> joyful B2 -> elated C1. A cell with
nothing for the photo stays empty; a word the photo does not show is never
added unless it is a database synonym of one that is shown.

grid = {"version": 1, "rows": [...], "levels": [...],
        "cells": [{"pos", "cefr", "words": [{"word", "concept_id", "anchor",
                                              "source": "photo" | "lexicon"}]}]}
"""
from __future__ import annotations

from sqlalchemy import select

from . import models as m

GRID_VERSION = 1
ROWS = ["verb", "noun", "adjective", "adverb", "phrase"]
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
CELL_MAX = 3
SYNONYMS_PER_CONCEPT = 3
# WordNet / Wiktionary links of strength >= 0.8 only: Datamuse and AI-guessed ones are loose.
MIN_STRENGTH = 0.8
SYNONYM_SOURCES = ("oewn", "kaikki")
_DB_POS = {"verb": "verb", "noun": "noun", "adjective": "adj", "adverb": "adv"}
_TAG_POS = {"n": "noun", "v": "verb", "a": "adjective", "adj": "adjective", "adv": "adverb",
            "d": "adverb", "p": "phrase"}


def _norm(word) -> str:
    return " ".join(str(word or "").strip().lower().split())


def row_of(tag: dict) -> str | None:
    """The grid row of a label; None for parts of speech the grid does not show."""
    word = _norm(tag.get("word"))
    if " " in word:
        return "phrase"
    pos = str(tag.get("pos") or "").strip().lower()
    pos = _TAG_POS.get(pos, pos)
    return pos if pos in ROWS else None


def _anchor(tag: dict) -> dict:
    return {"point": tag.get("point") or [], "box": tag.get("box")}


def _lexeme_ids(s, word: str, pos: str) -> list[int]:
    if pos == "phrase":
        return []
    return list(s.scalars(select(m.Lexeme.id).where(
        m.Lexeme.language == "en", m.Lexeme.normalized == word,
        m.Lexeme.pos == _DB_POS[pos], m.Lexeme.status == "full")))


def _synonyms(s, lexeme_ids: list[int], pos: str) -> list[tuple[str, str]]:
    """(word, cefr) of the database's synonyms of these lexemes: same part of
    speech, a CEFR level, a Chinese meaning - the entries the app can show."""
    if not lexeme_ids:
        return []
    db_pos = _DB_POS[pos]
    found: dict[str, tuple[float, str]] = {}
    forward = select(m.Lexeme, m.LexemeRelation.strength).join(
        m.LexemeRelation, m.LexemeRelation.target_lexeme_id == m.Lexeme.id).where(
        m.LexemeRelation.relation == "synonyms", m.LexemeRelation.lexeme_id.in_(lexeme_ids),
        m.LexemeRelation.strength >= MIN_STRENGTH, m.LexemeRelation.source.in_(SYNONYM_SOURCES))
    backward = select(m.Lexeme, m.LexemeRelation.strength).join(
        m.LexemeRelation, m.LexemeRelation.lexeme_id == m.Lexeme.id).where(
        m.LexemeRelation.relation == "synonyms", m.LexemeRelation.target_lexeme_id.in_(lexeme_ids),
        m.LexemeRelation.strength >= MIN_STRENGTH, m.LexemeRelation.source.in_(SYNONYM_SOURCES))
    candidates = {}
    for query in (forward, backward):
        for lex, strength in s.execute(query):
            if (lex.language == "en" and lex.status == "full" and lex.pos == db_pos
                    and lex.cefr in LEVELS and lex.id not in lexeme_ids):
                candidates[lex.id] = (lex, float(strength or 0))
    if not candidates:
        return []
    with_zh = set(s.scalars(select(m.Sense.lexeme_id).join(
        m.SenseTranslation, m.SenseTranslation.sense_id == m.Sense.id).where(
        m.Sense.lexeme_id.in_(list(candidates)), m.SenseTranslation.native_language == "zh-TW",
        m.SenseTranslation.text != "")))
    for lex_id, (lex, strength) in candidates.items():
        if lex_id in with_zh:
            word = lex.normalized
            if word not in found or strength > found[word][0]:
                found[word] = (strength, lex.cefr)
    return [(w, c) for w, (_, c) in sorted(found.items(), key=lambda kv: (-kv[1][0], kv[0]))]


def build_grid(s, tags: list[dict] | None) -> dict:
    """The grid of a photo's labels (``tags`` need word, pos, cefr, point/box)."""
    cells = {(r, c): [] for r in ROWS for c in LEVELS}
    taken: set[tuple[str, str]] = set()
    concepts = []
    ordered = sorted((t for t in tags or [] if isinstance(t, dict)),
                     key=lambda t: -(t.get("score") or 0))
    for tag in ordered:
        row, level, word = row_of(tag), str(tag.get("cefr") or "").upper(), _norm(tag.get("word"))
        if not row or level not in LEVELS or not word or (row, word) in taken:
            continue
        cell = cells[(row, level)]
        if len(cell) >= CELL_MAX:
            continue
        concept_id = f"c{len(concepts) + 1}"
        anchor = _anchor(tag)
        cell.append({"word": word, "concept_id": concept_id, "anchor": anchor, "source": "photo"})
        taken.add((row, word))
        concepts.append((concept_id, row, word, level, anchor))
    # Words the photo shows hold their cells first; synonyms only fill what is left.
    for concept_id, row, word, level, anchor in concepts:
        added = 0
        for syn, syn_level in _synonyms(s, _lexeme_ids(s, word, row), row):
            cell = cells[(row, syn_level)]
            if (row, syn) in taken or len(cell) >= CELL_MAX or any(
                    w["concept_id"] == concept_id for w in cell):
                continue
            cell.append({"word": syn, "concept_id": concept_id, "anchor": anchor,
                         "source": "lexicon"})
            taken.add((row, syn))
            added += 1
            if added >= SYNONYMS_PER_CONCEPT:
                break
    return {"version": GRID_VERSION, "rows": ROWS, "levels": LEVELS,
            "cells": [{"pos": r, "cefr": c, "words": cells[(r, c)]} for r in ROWS for c in LEVELS]}
