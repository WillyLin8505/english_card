"""Open English WordNet adapter — 近義字 (首選), 釋義/詞性 (次選),
詞性衍生 (次選), 英文例句 (補充).

Practical note: Open English WordNet's own XML database is not fetchable
from this sandbox's network policy (en-word.net and the GitHub release
tarball are both blocked). NLTK's mirror of Princeton WordNet *is*
fetchable (raw.githubusercontent.com is allow-listed) and is the dataset
Open English WordNet itself forked from, so this adapter reads it via
NLTK's corpus reader as the practical, license-compatible stand-in. If
you obtain the official Open English WordNet WN-LMF file separately,
swap the loader below for `wn.download('oewn:2024')` (the `wn` package)
without changing this adapter's public methods.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base import SourceAdapter

_POS_MAP = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}


class WordNetAdapter(SourceAdapter):
    name = "wordnet"

    def __init__(self, nltk_data_path: Optional[str] = None):
        import nltk  # local import so this module is optional at install time

        if nltk_data_path and nltk_data_path not in nltk.data.path:
            nltk.data.path.insert(0, nltk_data_path)
        from nltk.corpus import wordnet as wn

        self.wn = wn

    def get_lexical(self, word: str) -> Optional[Dict]:
        syns = self.wn.synsets(word)
        if not syns:
            return None
        defs, seen = [], set()
        for s in syns:
            pos = _POS_MAP.get(s.pos(), s.pos())
            key = (pos, s.definition())
            if key in seen:
                continue
            seen.add(key)
            defs.append({"pos": pos, "gloss": s.definition()})
        return {"definitions": defs} if defs else None

    def get_synonyms(self, word: str, limit: int = 8) -> Optional[List[str]]:
        syns = self.wn.synsets(word)
        if not syns:
            return None
        found, seen = [], set()
        for s in syns:
            for lemma in s.lemmas():
                name = lemma.name().replace("_", " ")
                if name.lower() == word.lower() or name.lower() in seen:
                    continue
                seen.add(name.lower())
                found.append(name)
                if len(found) >= limit:
                    return found
        return found or None

    def get_derivations(self, word: str, limit: int = 8) -> Optional[List[Dict]]:
        syns = self.wn.synsets(word)
        if not syns:
            return None
        found, seen = [], set()
        for s in syns:
            for lemma in s.lemmas():
                if lemma.name().lower() != word.lower():
                    continue
                for related in lemma.derivationally_related_forms():
                    name = related.name().replace("_", " ")
                    if name.lower() == word.lower() or name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    pos = _POS_MAP.get(related.synset().pos(), related.synset().pos())
                    found.append({"word": name, "pos": pos})
                    if len(found) >= limit:
                        return found
        return found or None

    def get_example_sentences(self, word: str, limit: int = 3) -> Optional[List[Dict]]:
        syns = self.wn.synsets(word)
        if not syns:
            return None
        found = []
        for s in syns:
            for ex in s.examples():
                found.append({"en": ex, "zh": None, "audio_url": None})
                if len(found) >= limit:
                    return found
        return found or None
