"""Datamuse API (English only): related words, sound-alikes and spell-alikes.
Cached, rate limited and retried by adapters.http."""

from __future__ import annotations

import math
import urllib.parse

from . import http
from .base import Candidate, Context, SourceAdapter, by_frequency, zipf

BASE = "https://api.datamuse.com/words?"
QUERIES = {"synonyms": "rel_syn", "antonyms": "rel_ant", "hypernyms": "rel_spc",
           "hyponyms": "rel_gen", "related": "ml", "homophones": "rel_hom",
           "near_homophones": "sl", "similar_spelling": "sp"}


# Datamuse's part-of-speech tags → the dictionary's.
_POS = {"n": "noun", "v": "verb", "adj": "adj", "adv": "adv"}


class Datamuse(SourceAdapter):
    key = "datamuse"

    def ask(self, ctx: Context, params: dict) -> list[dict]:
        url = BASE + urllib.parse.urlencode(params)
        data, _ = http.get("datamuse", ctx.lemma, url, timeout=ctx.timeout, retries=ctx.retries,
                           refresh=ctx.refresh)
        return data or []

    def lookup(self, f: str, ctx: Context):
        # One request per field (not one per headword): fetch lazily here.
        if ctx.target != "en":
            return []
        return super().lookup(f, ctx)

    def raw(self, ctx):
        return None

    def normalize(self, f: str, _raw, ctx: Context) -> list[Candidate]:
        C = []
        w = ctx.lemma
        if f == "frequency":
            rows = self.ask(ctx, {"sp": w, "md": "f", "max": 1})
            for r in rows:
                if r.get("word", "").lower() == w:
                    tag = next((t for t in r.get("tags", []) if t.startswith("f:")), None)
                    if tag:
                        per_million = float(tag[2:])
                        z = round(math.log10(per_million) + 3, 2) if per_million > 0 else 0
                        C.append(Candidate(f, "en", {"zipf": z, "per_million": per_million},
                                           str(z), confidence=0.8))
            return C
        rel = QUERIES.get(f)
        if not rel:
            return C
        rows = self.ask(ctx, {rel: w, "max": 100 if f in ("synonyms", "related") else 20})
        homs = set()
        if f == "near_homophones":
            homs = {r["word"].lower() for r in self.ask(ctx, {"rel_hom": w, "max": 20})}
        top = max((r.get("score", 0) for r in rows), default=0) or 1
        for r in rows:
            word = (r.get("word") or "").strip()
            if not word or word.lower() == w or word.lower() in homs:
                continue
            tags = r.get("tags") or []
            # Proper nouns (apple → abel, babylon) are not in the dictionary
            # (spec section 7: 排除人名、品牌…及其他專有名詞).
            if "prop" in tags:
                continue
            # Sound- and spell-alikes include junk spellings ("apal", "abal").
            if f in ("homophones", "near_homophones", "similar_spelling") \
                    and zipf(word, "en") < 2.0:
                continue
            score = round(r.get("score", 0) / top, 3)
            value = {"word": word, "score": score}
            pos = next((_POS[t] for t in tags if t in _POS), None)
            if pos:
                value["pos"] = pos
            if f in ("homophones", "near_homophones"):
                value["note"] = "同音" if f == "homophones" else "近音"
            C.append(Candidate(f, "en", value, word.lower(),
                               confidence=0.5 + 0.4 * score if f != "homophones" else 0.9,
                               source_record_id=f"{rel}={w}"))
        return by_frequency(C, "en")
