"""Common adapter interface. Every source implements only the methods it
can actually answer for its data category (see spec-01-data-sources.html
section 3) and leaves the rest as the no-op default here, which
merge.resolve() treats as "no data, try the next source".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class SourceAdapter:
    name: str = "base"

    def get_lexical(self, word: str) -> Optional[Dict[str, Any]]:
        """-> {"definitions": [{"pos": str, "gloss": str}, ...]} or None."""
        return None

    def get_pronunciation(self, word: str) -> Optional[Dict[str, Any]]:
        """-> {"ipa": str | None, "arpabet": str | None} or None."""
        return None

    def get_word_audio(self, word: str) -> Optional[Dict[str, Any]]:
        """-> {"url": str} or None."""
        return None

    def get_synonyms(self, word: str) -> Optional[List[str]]:
        return None

    def get_homophones(self, word: str) -> Optional[List[str]]:
        return None

    def get_similar_spelling(self, word: str) -> Optional[List[str]]:
        return None

    def get_inflections(self, word: str) -> Optional[List[Dict[str, str]]]:
        """-> [{"form": str, "label": str}, ...] or None."""
        return None

    def get_derivations(self, word: str) -> Optional[List[Dict[str, str]]]:
        """-> [{"word": str, "pos": str | None}, ...] or None."""
        return None

    def get_morphology(self, word: str) -> Optional[Dict[str, Any]]:
        """-> {"root": str | None, "affixes": [str, ...]} or None."""
        return None

    def get_example_sentences(self, word: str) -> Optional[List[Dict[str, Any]]]:
        """-> [{"en": str, "zh": str | None, "audio_url": str | None,
        "id": Any | None}, ...] or None."""
        return None
