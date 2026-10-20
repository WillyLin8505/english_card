"""Label synonyms: other English words the vision model may use for a picture
word (card #329, 問題回報 #427).

``images.judge`` keeps a picture on a word only when the AI labels name the
word. The labels are free English: a picture of a father is labelled dad,
a fridge refrigerator, a movie film — so père / fridge / movie lost every
candidate although the picture was right. The owner-editable table
``lexicon/quality/label_synonyms.json`` lists the words that count as the
same thing:

    {"groups": [["father", "dad", "daddy", "papa"], ...],
     "implies": {"bedroom": ["headboard", "nightstand"], ...}}

``groups`` are symmetric (any member stands for any other); ``implies`` is
one-way: a label that practically entails the word (a headboard is in a
bedroom) without the word entailing the label. Applies to every language
(the label word is English for all of them). Re-read when the file changes.
"""
from __future__ import annotations

import json
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "quality" / "label_synonyms.json"

_cache: dict = {"mtime": None, "index": {}}


def _build(data: dict) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for group in data.get("groups") or []:
        words = [str(w).strip().lower() for w in group if str(w).strip()]
        for w in words:
            index.setdefault(w, set()).update(x for x in words if x != w)
    for word, labels in (data.get("implies") or {}).items():
        w = str(word).strip().lower()
        index.setdefault(w, set()).update(
            str(x).strip().lower() for x in labels or [] if str(x).strip())
    return index


def _load() -> dict[str, set[str]]:
    try:
        mtime = FILE.stat().st_mtime
    except OSError:
        _cache.update(mtime=None, index={})
        return {}
    if _cache["mtime"] != mtime:
        try:
            data = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _cache.update(mtime=mtime, index=_build(data if isinstance(data, dict) else {}))
    return _cache["index"]


def synonyms(word: str | None) -> set[str]:
    """The labels that count as naming ``word`` besides its own spellings."""
    if not word:
        return set()
    return set(_load().get(word.strip().lower(), ()))
