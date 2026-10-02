"""Wikidata + Wikimedia Commons: sense images and word recordings.

Pictures bind to sense ids, which exist only once a word is stored, so the
field pipeline asks nothing here for them: pipeline.process_word runs
images.auto_fetch after materializing the word.

Recordings: Commons files named the Wiktionary way (En-uk-word.ogg,
En-us-word.ogg) that the word's Wiktionary page doesn't link. Asked only for
the accents Kaikki left missing (one request per word, cached).
"""

from __future__ import annotations

import urllib.parse

from . import http
from .base import Candidate, Context, SourceAdapter
from .kaikki import audio_slot, file_accent

API = "https://commons.wikimedia.org/w/api.php"
AUDIO_TITLES = ("En-uk-{}.ogg", "En-gb-{}.ogg", "En-uk-{}.wav", "En-gb-{}.wav", "En-uk-{}.oga",
                "En-us-{}.ogg", "En-us-{}.wav", "En-us-{}.oga")


def mp3_url(url: str) -> str:
    """Commons' MP3 rendering of a recording (plays everywhere)."""
    if url.lower().endswith(".mp3") or "/wikipedia/commons/" not in url:
        return url
    head, _, name = url.rpartition("/")
    return head.replace("/wikipedia/commons/", "/wikipedia/commons/transcoded/", 1) \
        + f"/{name}/{name}.mp3"


class WikimediaCommons(SourceAdapter):
    key = "wikimedia_commons"

    def lookup(self, field_key: str, ctx: Context):
        return super().lookup(field_key, ctx) if field_key == "audio" else []

    def fetch(self, ctx: Context):
        if ctx.target != "en":
            return None
        word = (ctx.display or ctx.lemma).strip()
        url = API + "?" + urllib.parse.urlencode({
            "action": "query", "format": "json", "formatversion": 2,
            "titles": "|".join("File:" + t.format(word) for t in AUDIO_TITLES),
            "prop": "imageinfo", "iiprop": "url|mime"})
        data, _ = http.get(self.key, word, url, timeout=ctx.timeout, retries=ctx.retries,
                           refresh=ctx.refresh)
        return data

    def normalize(self, field_key, raw, ctx):
        if field_key != "audio" or not raw:
            return []
        out = []
        for page in (raw.get("query") or {}).get("pages", []):
            info = (page.get("imageinfo") or [None])[0]
            if page.get("missing") or not info or not info.get("url"):
                continue
            name = page["title"].split(":", 1)[1]
            acc = file_accent(name)
            url = mp3_url(info["url"])
            out.append(Candidate("audio", ctx.target, {
                "url": url, "file": name, "accent": acc, "fallback_url": info["url"]},
                url, slot=audio_slot(acc), source_record_id=name))
        return out
