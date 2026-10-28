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
                                              "source": "photo" | "lexicon" | "related"}], "empty_reason"?}]}
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

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
# Card #722 (問題回報 #863): every cell should hold a word. Cells still empty after the
# synonyms are filled from the database's own word web around the shown words
# (hypernym / hyponym / related / derived / synonym links, up to FILL_HOPS steps away).
# Meaning links first; "related" and "derived_terms" are looser and only break ties last.
FILL_RELATIONS = {"synonyms": 0, "hypernyms": 1, "hyponyms": 1, "related": 2, "derived_terms": 3}
FILL_HOPS = 2
# hops + link kind above; looser chains (a related word of a related word) are not offered.
FILL_MAX_COST = 3
FILL_FANOUT = 400
EMPTY_REASON = "這張照片沒有合適的字"
# Card #722 (owner B): Qwen judges whether each "related" word fits the photo (yes/no answer
# probability, as the label scores). Below FIT_PASS the word goes back to an empty cell.
# Verdicts are cached per photo in FIT_PATH so opening the table never asks Qwen again.
FIT_PASS = 0.5
FIT_PATH = Path(os.environ.get("LEXICON_GRID_FIT_PATH") or Path(__file__).resolve().parents[2] / "state" / "photo_grid_fit.json")
_FIT_LOCK = threading.Lock()
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


def _cell_row(lex) -> str | None:
    """The grid row a database entry belongs in (multi-word entries are phrases)."""
    if " " in lex.normalized:
        return "phrase"
    return next((r for r, p in _DB_POS.items() if p == lex.pos), None)


def _fill_gaps(s, cells, taken, concepts) -> None:
    """Put one word of the right part of speech and level into each empty cell: the
    nearest database entry (fewest link steps, then strongest link) around a word the
    photo shows. The word keeps that concept's anchor; source is "related"."""
    empty = {k for k, v in cells.items() if not v}
    if not empty or not concepts:
        return
    seen: dict[int, tuple[int, float, tuple]] = {}  # lexeme id -> (hops, -strength, concept)
    for concept in concepts:
        _, row, word, _, _ = concept
        for lid in _lexeme_ids(s, word, row):
            seen[lid] = (0, 0.0, concept)
    best: dict[tuple[str, str], tuple[tuple, str, tuple]] = {}
    frontier = list(seen)
    for hop in range(1, FILL_HOPS + 1):
        if not frontier or not empty:
            break
        links = []
        for col, other in ((m.LexemeRelation.lexeme_id, m.LexemeRelation.target_lexeme_id),
                           (m.LexemeRelation.target_lexeme_id, m.LexemeRelation.lexeme_id)):
            links += s.execute(select(col, other, m.LexemeRelation.strength,
                                      m.LexemeRelation.relation).where(
                col.in_(frontier), m.LexemeRelation.relation.in_(list(FILL_RELATIONS))).limit(
                FILL_FANOUT * len(frontier))).all()
        found: dict[int, tuple[int, float, tuple]] = {}
        for src, dst, strength, relation in links:
            if dst in seen:
                continue
            cand = (hop + FILL_RELATIONS[relation], -float(strength or 0), seen[src][2])
            if cand[0] > FILL_MAX_COST:
                continue
            if dst not in found or cand[:2] < found[dst][:2]:
                found[dst] = cand
        if not found:
            break
        lexes = {l.id: l for l in s.scalars(select(m.Lexeme).where(
            m.Lexeme.id.in_(list(found)), m.Lexeme.language == "en", m.Lexeme.status == "full"))}
        with_zh = set(s.scalars(select(m.Sense.lexeme_id).join(
            m.SenseTranslation, m.SenseTranslation.sense_id == m.Sense.id).where(
            m.Sense.lexeme_id.in_(list(lexes)), m.SenseTranslation.native_language == "zh-TW",
            m.SenseTranslation.text != "")))
        for lid, cand in found.items():
            seen[lid] = cand
            lex = lexes.get(lid)
            if lex is None or lid not in with_zh or lex.cefr not in LEVELS:
                continue
            row = _cell_row(lex)
            key = (row, lex.cefr)
            if row is None or key not in empty or (row, lex.normalized) in taken:
                continue
            rank = (cand[0], cand[1], lex.normalized)
            if key not in best or rank < best[key][0]:
                best[key] = (rank, lex.normalized, cand[2])
        frontier = list(found)
        empty -= set(best)
    for (row, level), (_, word, concept) in best.items():
        cells[(row, level)].append({"word": word, "concept_id": concept[0], "anchor": concept[4],
                                    "source": "related"})
        taken.add((row, word))


def _fit_key(row: str, word: str) -> str:
    return f"{row}|{word}"


def load_fit(asset_id) -> dict[str, float]:
    """Cached Qwen photo-fit verdicts of one stored photo ("row|word" -> 0..1)."""
    try:
        data = json.loads(FIT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict((data.get(str(asset_id)) or {}).get("words") or {})


def save_fit(asset_id, verdicts: dict[str, float]) -> None:
    with _FIT_LOCK:
        try:
            data = json.loads(FIT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        entry = data.setdefault(str(asset_id), {"words": {}})
        entry["words"].update(verdicts)
        FIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = FIT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, FIT_PATH)


def related_words(grid: dict) -> list[tuple[str, str]]:
    """(row, word) of every word filled from the word web: the ones Qwen is asked about."""
    return [(c["pos"], w["word"]) for c in grid["cells"] for w in c["words"] if w.get("source") == "related"]


def _apply_fit(cells, fits) -> int:
    """Drop related words Qwen said do not fit; mark the kept ones with their score.
    Returns how many related words have no verdict yet."""
    unchecked = 0
    for (row, _), words in cells.items():
        for w in list(words):
            if w["source"] != "related":
                continue
            score = fits.get(_fit_key(row, w["word"]))
            if score is None:
                unchecked += 1
            elif score < FIT_PASS:
                words.remove(w)
            else:
                w["fit"] = round(float(score), 3)
    return unchecked


def build_grid(s, tags: list[dict] | None, fits: dict[str, float] | None = None) -> dict:
    """The grid of a photo's labels (``tags`` need word, pos, cefr, point/box).
    ``fits``: cached Qwen verdicts; related words scored below FIT_PASS are left out."""
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
    _fill_gaps(s, cells, taken, concepts)
    unchecked = _apply_fit(cells, fits or {})
    return {"version": GRID_VERSION, "rows": ROWS, "levels": LEVELS, "fit_unchecked": unchecked,
            "cells": [{"pos": r, "cefr": c, "words": cells[(r, c)],
                       **({} if cells[(r, c)] else {"empty_reason": EMPTY_REASON})}
                      for r in ROWS for c in LEVELS]}
