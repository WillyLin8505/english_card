"""CMUdict adapter — 發音音標／音素 (首選 ARPABET, since CMUdict is not IPA)
and 同音字／發音相近 (首選: exact-phoneme match).

Real, offline data: download cmudict.dict with pipeline/download_data.py
(or point CMUdictAdapter at any file in the same `word  PHONES` format).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .base import SourceAdapter

_VARIANT_RE = re.compile(r"\(\d+\)$")


class CMUdictAdapter(SourceAdapter):
    name = "cmudict"

    def __init__(self, dict_path: str | Path):
        self.dict_path = Path(dict_path)
        self._word_to_phones: Dict[str, List[str]] = defaultdict(list)
        self._phones_to_words: Dict[str, set] = defaultdict(set)
        self._load()

    def _load(self) -> None:
        with self.dict_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(";;;"):
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                raw_word, phones = parts
                base_word = _VARIANT_RE.sub("", raw_word).lower()
                self._word_to_phones[base_word].append(phones)
                self._phones_to_words[phones].add(base_word)

    def words(self) -> List[str]:
        """All base words in the dictionary — handy as a general-purpose
        English word list for the similar-spelling adapter."""
        return list(self._word_to_phones.keys())

    def get_pronunciation(self, word: str) -> Optional[dict]:
        phones_list = self._word_to_phones.get(word.lower())
        if not phones_list:
            return None
        return {"ipa": None, "arpabet": phones_list[0]}

    def get_homophones(self, word: str, limit: int = 8) -> Optional[List[str]]:
        phones_list = self._word_to_phones.get(word.lower())
        if not phones_list:
            return None
        found = set()
        for phones in phones_list:
            for w in self._phones_to_words.get(phones, ()):
                if w != word.lower():
                    found.add(w)
        return sorted(found)[:limit] if found else None
