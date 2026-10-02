"""Kaikki/Wiktionary adapter — 首選 for 6 of the 12 categories (單字/釋義/
詞性, 音標, 單字真人發音, 詞形變化, 字根字尾) and 次選 for 3 more.

Kaikki has no stable public per-word API (kaikki.org is also blocked by
this sandbox's egress policy), so this adapter is offline-dump based:
point `dump_path` at the English extract you download yourself from
https://kaikki.org/dictionary/English/, or at a pre-filtered subset
built with `pipeline/download_data.py --filter-kaikki`.

Parses the documented Kaikki JSONL schema defensively (every lookup
uses .get(), never assumes a key is present) since Wiktionary entries
vary a lot in how complete they are.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .base import SourceAdapter


class KaikkiAdapter(SourceAdapter):
    name = "kaikki"

    def __init__(self, dump_path: str | Path):
        self.dump_path = Path(dump_path)
        self._index: Dict[str, List[dict]] = defaultdict(list)
        self._load()

    def _load(self) -> None:
        if not self.dump_path.exists():
            return
        with self.dump_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                w = entry.get("word")
                if w:
                    self._index[w.lower()].append(entry)

    def _entries(self, word: str) -> List[dict]:
        return self._index.get(word.lower(), [])

    def get_lexical(self, word: str) -> Optional[dict]:
        entries = self._entries(word)
        if not entries:
            return None
        defs = []
        for e in entries:
            pos = e.get("pos") or "?"
            for sense in e.get("senses", []):
                for g in sense.get("glosses") or sense.get("raw_glosses") or []:
                    defs.append({"pos": pos, "gloss": g})
        return {"definitions": defs} if defs else None

    def get_pronunciation(self, word: str) -> Optional[dict]:
        for e in self._entries(word):
            for sound in e.get("sounds", []):
                if sound.get("ipa"):
                    return {"ipa": sound["ipa"], "arpabet": None}
        return None

    def get_word_audio(self, word: str) -> Optional[dict]:
        for e in self._entries(word):
            for sound in e.get("sounds", []):
                url = sound.get("mp3_url") or sound.get("ogg_url") or sound.get("audio")
                if url:
                    return {"url": url}
        return None

    def get_synonyms(self, word: str, limit: int = 8) -> Optional[List[str]]:
        found: List[str] = []
        for e in self._entries(word):
            for syn in e.get("synonyms", []):
                w = syn.get("word")
                if w and w.lower() != word.lower() and w not in found:
                    found.append(w)
            for sense in e.get("senses", []):
                for syn in sense.get("synonyms", []):
                    w = syn.get("word")
                    if w and w.lower() != word.lower() and w not in found:
                        found.append(w)
        return found[:limit] or None

    def get_inflections(self, word: str) -> Optional[List[dict]]:
        found = []
        for e in self._entries(word):
            for form in e.get("forms", []):
                text = form.get("form")
                tags = form.get("tags") or []
                if not text or text.lower() == word.lower() or "table-tags" in tags:
                    continue
                found.append({"form": text, "label": " ".join(tags) or "form"})
        return found or None

    def get_derivations(self, word: str, limit: int = 8) -> Optional[List[dict]]:
        found = []
        for e in self._entries(word):
            for d in e.get("derived", []):
                w = d.get("word")
                if w and w.lower() != word.lower():
                    found.append({"word": w, "pos": None})
        return found[:limit] or None

    def get_morphology(self, word: str) -> Optional[dict]:
        for e in self._entries(word):
            root, affixes = None, []
            for t in e.get("etymology_templates") or []:
                name = t.get("name")
                args = t.get("args") or {}
                parts = [v for k, v in sorted(args.items()) if str(k).isdigit()]
                if not parts:
                    continue
                if name == "prefix":
                    affixes.append(parts[0] + "-")
                    root = parts[1] if len(parts) > 1 else root
                elif name == "suffix":
                    root = parts[0]
                    if len(parts) > 1:
                        affixes.append("-" + parts[1])
                elif name in ("affix", "confix"):
                    root = parts[0]
                    affixes.extend(parts[1:])
            etymology_text = e.get("etymology_text")
            if root or affixes or etymology_text:
                return {"root": root, "affixes": affixes, "etymology_text": etymology_text}
        return None

    def get_example_sentences(self, word: str, limit: int = 3) -> Optional[List[dict]]:
        found = []
        for e in self._entries(word):
            for sense in e.get("senses", []):
                for ex in sense.get("examples", []):
                    text = ex.get("text")
                    if text:
                        found.append({"en": text, "zh": None, "audio_url": None})
                        if len(found) >= limit:
                            return found
        return found or None
