"""Excluded parts of speech (問題回報 #284, card #283).

Some words carry a part of speech the lexicon should not show (card #167:
its main sense has no Chinese). Deleting the lexeme is not enough: the
`pos` / `definition` values and the sources' candidates still name it, so
the next materialize or force_refresh / reresolve builds it again.

The decision lives in lexicon/quality/excluded_pos.json instead:

    {"en": {"marine": {"verb": "card #167: main sense has no Chinese"}}}

`pipeline.resolve_field` never adopts a `pos` / `definition` candidate of
an excluded part of speech (the candidate stays stored as source evidence),
and `materialize` never builds a lexeme for one. Remove the entry and
re-resolve the word to bring the part of speech back."""

from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "quality" / "excluded_pos.json"
# Fields whose items' "pos" is the headword's own part of speech.
FIELDS = ("pos", "definition")
REASON = "已排除的詞性（quality/excluded_pos.json）"

_cache: tuple[tuple[int, int], dict] | None = None


def load() -> dict[str, dict[str, dict[str, str]]]:
    """language → lemma → {pos: reason}; re-read when the file changes."""
    global _cache
    try:
        st = PATH.stat()
    except FileNotFoundError:
        return {}
    stamp = (st.st_mtime_ns, st.st_size)
    if _cache is None or _cache[0] != stamp:
        data = json.loads(PATH.read_text(encoding="utf-8"))
        _cache = (stamp, {k: v for k, v in data.items() if not k.startswith("_")})
    return _cache[1]


def excluded(language: str, lemma: str) -> set[str]:
    return set(load().get(language, {}).get(lemma, {}))


def drop_candidates(cands, language: str, lemma: str, field_key: str) -> int:
    """Mark candidates of an excluded part of speech invalid; returns how many."""
    if field_key not in FIELDS:
        return 0
    bad = excluded(language, lemma)
    if not bad:
        return 0
    n = 0
    for c in cands:
        if c.valid and isinstance(c.value, dict) and c.value.get("pos") in bad:
            c.valid, c.invalid_reason = False, REASON
            n += 1
    return n
