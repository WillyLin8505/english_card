"""Datamuse adapter — 近義字 (補充), 同音字 (次選), 拼字相近 (次選).

NOTE: this sandbox's network policy blocks api.datamuse.com (confirmed:
CONNECT tunnel 403), so this adapter could not be exercised against a
live response from here. It's written to Datamuse's documented, stable
API (https://www.datamuse.com/api/) — run it from an environment with
normal internet access (your own machine, CI) and re-verify with a real
request before depending on it in production.
"""

from __future__ import annotations

from typing import List, Optional

import requests

DATAMUSE_URL = "https://api.datamuse.com/words"


class DatamuseAdapter:
    name = "datamuse"

    def __init__(self, session: Optional[requests.Session] = None, timeout: float = 8.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    def _query(self, params: dict) -> list:
        try:
            resp = self.session.get(DATAMUSE_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return []
        return data if isinstance(data, list) else []

    def get_synonyms(self, word: str, limit: int = 8) -> Optional[List[str]]:
        data = self._query({"rel_syn": word, "max": limit})
        words = [d["word"] for d in data if d.get("word")]
        return words or None

    def get_homophones(self, word: str, limit: int = 8) -> Optional[List[str]]:
        # Datamuse's rel_hom relation is literally "sounds alike, spelled
        # differently" — i.e. homophones.
        data = self._query({"rel_hom": word, "max": limit})
        words = [d["word"] for d in data if d.get("word")]
        return words or None

    def get_similar_spelling(self, word: str, limit: int = 8) -> Optional[List[str]]:
        # Datamuse has no direct "edit distance" relation; approximate it
        # with the "sp" spelled-like wildcard pattern, substituting one
        # character at a time (a lightweight edit-distance-1 sweep).
        found: List[str] = []
        seen = {word.lower()}
        for i in range(len(word)):
            pattern = word[:i] + "?" + word[i + 1 :]
            data = self._query({"sp": pattern, "max": limit})
            for d in data:
                w = d.get("word")
                if w and w.lower() not in seen:
                    seen.add(w.lower())
                    found.append(w)
            if len(found) >= limit:
                break
        return found[:limit] or None
