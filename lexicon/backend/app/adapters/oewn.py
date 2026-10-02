"""Open English WordNet via the `wn` package (official WN-LMF release)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..text import example_key, fold, sense_key
from .base import Candidate, Context, SourceAdapter, by_frequency
from .http import SourceError

LEXICON = "oewn:2024"
POS = {"n": "noun", "v": "verb", "a": "adj", "s": "adj", "r": "adv"}

# wn keeps one module-level SQLite connection that can't cross threads,
# so every WordNet call runs on this one thread.
_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="oewn")
_db = None


def _wordnet():
    global _db
    import wn
    if _db is None:
        try:
            _db = wn.Wordnet(LEXICON)
        except Exception:  # noqa: BLE001 — first run: download (~30 MB)
            wn.download(LEXICON)
            _db = wn.Wordnet(LEXICON)
    return _db


def _first_lemma(ss) -> str | None:
    lemmas = ss.lemmas()
    return lemmas[0] if lemmas else None


def _lookup(word: str) -> list[dict]:
    wordnet = _wordnet()
    out = []
    for ss in wordnet.synsets(word):
        pos = POS.get(ss.pos, ss.pos)
        rec = {"id": ss.id, "pos": pos, "definition": ss.definition() or "",
               "lemmas": [l for l in ss.lemmas()], "examples": list(ss.examples()),
               "hypernyms": [x for x in (_first_lemma(h) for h in ss.hypernyms()) if x],
               "hyponyms": [x for x in (_first_lemma(h) for h in ss.hyponyms()) if x],
               "similar": [x for x in (_first_lemma(h) for h in
                                       ss.get_related("similar") + ss.get_related("also")) if x],
               "antonyms": [], "derivations": []}
        for s in ss.senses():
            if s.word().lemma().lower() != word.lower():
                continue
            rec["antonyms"] += [a.word().lemma() for a in s.get_related("antonym")]
            rec["derivations"] += [(d.word().lemma(), POS.get(d.synset().pos, d.synset().pos))
                                   for d in s.get_related("derivation")]
        out.append(rec)
    return out


def _pos_of(word: str) -> list[str]:
    wordnet = _wordnet()
    seen = []
    for ss in wordnet.synsets(word):
        p = POS.get(ss.pos, ss.pos)
        if p not in seen:
            seen.append(p)
    return seen


class OEWN(SourceAdapter):
    key = "oewn"

    def download_snapshot(self, language, snapshot_dir):
        import wn
        wn.download(LEXICON)
        lex = next((l for l in wn.lexicons() if l.id == "oewn"), None)
        return {"version": f"oewn:{lex.version}" if lex else LEXICON,
                "url": "https://en-word.net/", "path": str(wn.config.data_directory),
                "row_count": None, "details": {"format": "WN-LMF via wn"}}

    def fetch(self, ctx: Context):
        if ctx.target != "en":
            return []
        try:
            return _thread.submit(_lookup, ctx.display or ctx.lemma).result(timeout=ctx.timeout + 60)
        except Exception as e:  # noqa: BLE001
            raise SourceError("unavailable", f"WordNet: {e}") from e

    def normalize(self, f: str, recs, ctx: Context) -> list[Candidate]:
        C = []
        word = ctx.display or ctx.lemma

        def add(value, key, slot="", conf=1.0, rid="", lang="en"):
            C.append(Candidate(f, lang, value, key, slot=slot, confidence=conf,
                               source_record_id=rid))

        if f == "derived_pos":
            for item in ctx.items("derived_terms"):
                w = item.get("word", "")
                poses = _thread.submit(_pos_of, w).result()
                if poses:
                    add({"word": w, "pos": poses[0], "all": poses}, w.lower(), slot=w.lower(),
                        conf=0.8)
            return C
        for r in recs or []:
            skey = sense_key(r["pos"], r["definition"])
            if f == "pos":
                add({"pos": r["pos"]}, r["pos"], slot=r["pos"], rid=r["id"])
            elif f == "definition" and r["definition"]:
                add({"pos": r["pos"], "gloss": r["definition"], "sense_key": skey,
                     "synset": r["id"], "gloss_language": "en"}, skey, slot=r["pos"], rid=r["id"])
            elif f == "synonyms":
                for l in r["lemmas"]:
                    if l.lower() != word.lower():
                        add({"word": l, "pos": r["pos"], "sense_key": skey}, l.lower(), rid=r["id"])
            elif f in ("hypernyms", "hyponyms", "antonyms"):
                for l in r[f]:
                    add({"word": l, "pos": r["pos"], "sense_key": skey}, l.lower(), rid=r["id"])
            elif f == "related":
                for l in r["similar"]:
                    add({"word": l, "pos": r["pos"], "sense_key": skey}, l.lower(), rid=r["id"])
            elif f == "derived_terms":
                for l, p in r["derivations"]:
                    if l.lower() != word.lower() and " " not in l:
                        add({"word": l, "pos": p}, l.lower(), rid=r["id"])
            elif f == "example_sentences":
                for ex in r["examples"]:
                    text = ex.strip().strip('"')
                    if text and text[0].islower():
                        text = text[0].upper() + text[1:]
                    if text and text[-1] not in ".!?":
                        text += "."
                    add({"text": text, "sense_key": skey}, example_key(text), rid=r["id"],
                        conf=0.8)
            elif f == "example_sense":
                wanted = {fold(i.get("text", "")): i.get("key") or example_key(i.get("text", ""))
                          for i in ctx.items("example_sentences")}
                for ex in r["examples"]:
                    k = wanted.get(fold(ex))
                    if k:
                        add({"example_key": k, "sense_key": skey}, k, slot=k, rid=r["id"])
        if f in ("synonyms", "hypernyms", "hyponyms", "antonyms", "related",
                 "derived_terms"):
            C = by_frequency(C, ctx.target)
        return C
