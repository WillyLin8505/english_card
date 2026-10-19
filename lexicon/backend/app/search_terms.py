"""Reviewed English search terms for non-English senses (card #384, 問題回報 #379).

``images.english_search_term`` cuts a sense's English meaning to its first
item. For a French sense that item is sometimes a synonym or an explanatory
noun that does not name what the French word means — chef1 「article,
principal point」 → article, croix1 「a representation of a cross」 →
representation, corne1 「corn (callus)」 → corn — and no string rule can tell
those from chat 「cat (feline)」 → cat. The semantic call is made once per
sense (AI or owner) and recorded in ``lexicon/quality/search_terms.json``:

    {"fr": {"<lemma>|<pos>|<sense_key>": {"term": "callus" | null,
                                          "auto": "corn", "meaning": "...",
                                          "why": "...", "by": "..."}}}

``term`` null means "no English word pictures this sense": no picture is
fetched for it and no photo label maps to it. A sense without an entry keeps
the automatic term. Keys use the lemma's normalized form, the POS and the
sense_key (a hash of pos + gloss, stable across re-imports; see text.sense_key),
so a rerun of the lexicon keeps the decisions. The file is re-read when it
changes, so long-running workers see an edit without a restart.
"""
from __future__ import annotations

import json
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "quality" / "search_terms.json"

_cache: dict = {"mtime": None, "data": {}}


def _load() -> dict:
    try:
        mtime = FILE.stat().st_mtime
    except OSError:
        _cache.update(mtime=None, data={})
        return {}
    if _cache["mtime"] != mtime:
        try:
            data = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _cache.update(mtime=mtime, data=data if isinstance(data, dict) else {})
    return _cache["data"]


def key_for(lemma: str, pos: str | None, sense_key: str | None) -> str:
    return f"{(lemma or '').lower()}|{pos or ''}|{sense_key or ''}"


def reviewed(language: str, lemma: str, pos: str | None, sense_key: str | None):
    """(True, term-or-None) when the sense was reviewed; (False, None) otherwise."""
    if language == "en":
        return False, None
    entry = _load().get(language, {}).get(key_for(lemma, pos, sense_key))
    if not isinstance(entry, dict):
        return False, None
    term = entry.get("term")
    return True, (str(term).strip().lower() or None) if term else None


def sense_label_terms(language, lemma, pos, sense_key, meaning, gloss=None) -> list[str]:
    """images.english_label_terms for a sense, honouring its reviewed term:
    [term] when one was chosen, [] when the sense was reviewed as having no
    picture word, else the automatic items."""
    from .images import english_label_terms
    found, term = reviewed(language, lemma, pos, sense_key)
    if found:
        return [term] if term else []
    return english_label_terms(meaning, gloss)


def sense_search_term(language, lemma, pos, sense_key, meaning, gloss=None) -> str | None:
    """images.english_search_term for a sense, honouring its reviewed term."""
    from .images import english_search_term
    found, term = reviewed(language, lemma, pos, sense_key)
    if found:
        return term
    return english_search_term(meaning, gloss)
