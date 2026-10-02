"""Local wordlist adapter — 拼字相近 (首選: "Kaikki 字表＋自行比對").

Takes any flat English word list (e.g. CMUdict's ~135k word forms, or a
real Kaikki word list if you have one) and finds near-spellings by edit
distance, batch-computable offline with no network — exactly what the
spec's "本地字表可批次計算拼字距離" line describes.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from .base import SourceAdapter


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


class LocalWordlistAdapter(SourceAdapter):
    name = "kaikki_wordlist"

    def __init__(self, words: Iterable[str]):
        self.words = sorted({w.lower() for w in words if w.isalpha()})

    def get_similar_spelling(
        self, word: str, max_distance: int = 1, limit: int = 8
    ) -> Optional[List[str]]:
        word = word.lower()
        candidates = []
        for w in self.words:
            if w == word:
                continue
            if abs(len(w) - len(word)) > max_distance:
                continue
            if _levenshtein(word, w) <= max_distance:
                candidates.append(w)
        candidates.sort(key=lambda w: (_levenshtein(word, w), w))
        return candidates[:limit] or None
