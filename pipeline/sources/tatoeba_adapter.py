"""Tatoeba adapter — 英文例句 (首選), 例句中文翻譯 (首選), 整句真人發音 (首選).

NOTE: this sandbox's network policy blocks tatoeba.org (confirmed:
CONNECT tunnel 403), so this adapter could not be exercised against a
live response from here. It targets Tatoeba's documented api_v0 search
endpoint; Tatoeba has changed API shape before, so re-verify the field
names below against a real response (from your own machine / CI, where
tatoeba.org is reachable) before depending on it in production.
"""

from __future__ import annotations

from typing import List, Optional

import requests

TATOEBA_SEARCH_URL = "https://tatoeba.org/en/api_v0/search"
TATOEBA_AUDIO_URL = "https://audio.tatoeba.org/sentences/eng/{sentence_id}.mp3"


class TatoebaAdapter:
    name = "tatoeba"

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: float = 8.0,
        target_lang: str = "cmn",  # Mandarin Chinese
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.target_lang = target_lang

    def _search(self, word: str, limit: int) -> list:
        params = {"from": "eng", "to": self.target_lang, "query": word}
        try:
            resp = self.session.get(TATOEBA_SEARCH_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return []
        return (data.get("results") or [])[:limit]

    def get_example_sentences(self, word: str, limit: int = 3) -> Optional[List[dict]]:
        results = self._search(word, limit)
        found = []
        for r in results:
            en_text = r.get("text")
            if not en_text:
                continue
            sentence_id = r.get("id")
            zh_text = None
            for group in r.get("translations", []):
                for t in group:
                    if t.get("lang") == self.target_lang and t.get("text"):
                        zh_text = t["text"]
                        break
                if zh_text:
                    break
            audio_url = (
                TATOEBA_AUDIO_URL.format(sentence_id=sentence_id)
                if r.get("audios") and sentence_id is not None
                else None
            )
            found.append(
                {"en": en_text, "zh": zh_text, "audio_url": audio_url, "id": sentence_id}
            )
        return found or None
