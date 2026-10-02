"""Kaikki／Wiktionary: machine-readable JSONL extracted by wiktextract.

Per-headword JSONL from kaikki.org (the same records as the bulk dump;
never HTML). Each headword's record set is cached in raw-data/cache/kaikki/
and every fetch is listed in the source's snapshot.
"""

from __future__ import annotations

import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from .. import catalog, config, kaikki_index
from .. import morph_data as md
from ..morphology import (Evidence, Part, _prefix_meaning, expand, normalize_affix_args,
                          parts_from_affix_template,
                          template_gloss, zipf as en_zipf)
from ..text import fold, normalize_lemma, opencc, sense_key, example_key, tokens
from . import http
from .base import Candidate, Context, SourceAdapter, by_frequency, zipf

DICT_NAME = {"en": "English", "fr": "French", "zh-TW": "Chinese"}
LANG_CODE = {"en": "en", "fr": "fr", "zh-TW": "zh"}

POS = {"noun": "noun", "verb": "verb", "adj": "adj", "adv": "adv", "prep": "prep",
       "pron": "pron", "num": "num", "intj": "intj", "conj": "conj", "det": "det",
       "article": "det", "phrase": "phrase", "prep_phrase": "phrase", "proverb": "phrase",
       "name": "name"}
LOW_TAGS = {"obsolete", "archaic", "rare", "dialectal", "nonstandard", "misspelling",
            "alternative", "dated", "pronunciation-spelling", "eye-dialect"}
FORM_SKIP = {"table-tags", "inflection-template", "class", "romanization", "auxiliary"}
ACCENTS = {"General-American": "US", "US": "US", "American": "US",
           "Received-Pronunciation": "UK", "UK": "UK", "British": "UK",
           "Australia": "AU", "General-Australian": "AU", "Canada": "CA", "Canadian": "CA",
           "Paris": "FR", "Europe": "FR", "Quebec": "CA"}
LABEL_TAGS = {"informal", "formal", "slang", "colloquial", "vulgar", "offensive", "derogatory",
              "humorous", "literary", "figuratively", "idiomatic", "countable", "uncountable",
              "transitive", "intransitive", "British", "US", "Australia", "Canada", "archaic",
              "dated", "rare", "obsolete", "technical", "euphemistic", "childish", "poetic"}
AFFIX_TEMPLATES = {"affix", "af", "prefix", "pre", "suffix", "suf", "compound", "com",
                   "confix", "con", "surf", "blend"}
ORIGIN_TEMPLATES = {"inh", "inh+", "der", "der+", "bor", "bor+", "lbor", "slbor", "uder"}
LANG_NAMES = {"ang": "Old English", "enm": "Middle English", "fro": "Old French",
              "frm": "Middle French", "xno": "Anglo-Norman", "la": "Latin", "LL.": "Late Latin",
              "ML.": "Medieval Latin", "grc": "Ancient Greek", "non": "Old Norse",
              "gem-pro": "Proto-Germanic", "gmw-pro": "Proto-West Germanic",
              "ine-pro": "Proto-Indo-European", "fr": "French", "it": "Italian",
              "es": "Spanish", "pt": "Portuguese", "de": "German", "nl": "Dutch", "dum": "Middle Dutch",
              "ar": "Arabic", "fa": "Persian", "hi": "Hindi", "sa": "Sanskrit", "ja": "Japanese",
              "zh": "Chinese", "cmn": "Mandarin", "yue": "Cantonese", "ga": "Irish",
              "cy": "Welsh", "gd": "Scottish Gaelic", "sv": "Swedish", "da": "Danish",
              "no": "Norwegian", "is": "Icelandic", "ru": "Russian", "tr": "Turkish",
              "he": "Hebrew", "ota": "Ottoman Turkish", "nah": "Nahuatl", "en": "English",
              "osx": "Old Saxon", "goh": "Old High German", "gmh": "Middle High German",
              "VL.": "Vulgar Latin", "itc-pro": "Proto-Italic", "frk": "Frankish"}

# IPA → ARPAbet for General American transcriptions (Kaikki has no ARPAbet).
IPA_ARPA = [("aɪ", "AY"), ("aʊ", "AW"), ("eɪ", "EY"), ("oʊ", "OW"), ("ɔɪ", "OY"), ("tʃ", "CH"),
            ("dʒ", "JH"), ("ɝ", "ER"), ("ɚ", "ER"), ("ɑ", "AA"), ("æ", "AE"), ("ɔ", "AO"),
            ("ɛ", "EH"), ("ɪ", "IH"), ("i", "IY"), ("ʊ", "UH"), ("u", "UW"), ("ʌ", "AH"),
            ("ə", "AH"), ("b", "B"), ("d", "D"), ("ð", "DH"), ("f", "F"), ("ɡ", "G"), ("g", "G"),
            ("h", "HH"), ("k", "K"), ("l", "L"), ("m", "M"), ("n", "N"), ("ŋ", "NG"), ("p", "P"),
            ("ɹ", "R"), ("r", "R"), ("s", "S"), ("ʃ", "SH"), ("t", "T"), ("θ", "TH"), ("v", "V"),
            ("w", "W"), ("j", "Y"), ("z", "Z"), ("ʒ", "ZH")]
VOWEL_ARPA = {"AY", "AW", "EY", "OW", "OY", "ER", "AA", "AE", "AO", "EH", "IH", "IY", "UH", "UW",
              "AH"}


def ipa_to_arpabet(ipa: str) -> str | None:
    s = ipa.strip("/").replace("ː", "").replace(".", "").replace("ɾ", "t").replace("ɫ", "l")
    s = s.replace("l̩", "əl").replace("n̩", "ən").replace("ɚ", "ɚ")
    out, stress = [], "0"
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in "ˈˌ":
            stress = "1" if ch == "ˈ" else "2"
            i += 1
            continue
        if ch in " ()‿͡":
            i += 1
            continue
        for sym, arpa in IPA_ARPA:
            if s.startswith(sym, i):
                if arpa in VOWEL_ARPA:
                    out.append(arpa + stress)
                    stress = "0"
                else:
                    out.append(arpa)
                i += len(sym)
                break
        else:
            return None
    vowels = [k for k, p in enumerate(out) if p[-1].isdigit()]
    if len(vowels) == 1:
        out[vowels[0]] = out[vowels[0]][:-1] + "1"
    return " ".join(out) or None


def _pos(e: dict) -> str | None:
    return POS.get(e.get("pos", ""))


def _gloss(s: dict) -> str:
    return (s.get("glosses") or s.get("raw_glosses") or [""])[-1].strip()


def _is_form_of(s: dict) -> bool:
    return bool(s.get("form_of") or s.get("alt_of")) or "form-of" in s.get("tags", [])


# Recording file names say the accent when the tags don't
# (en-uk-London-bottle.ogg, EN-AU ck1 bench.ogg, en-us-bird.ogg).
FILE_ACCENTS = {"uk": "UK", "gb": "UK", "us": "US", "au": "AU", "ca": "CA", "nz": "NZ",
                "ie": "IE", "in": "IN", "za": "ZA"}


def file_accent(name: str | None) -> list[str]:
    m = re.match(r"(?i)en[-_ ]([a-z]{2})[-_ ]", name or "")
    a = FILE_ACCENTS.get(m.group(1).lower()) if m else None
    return [a] if a else []


def audio_slot(accent: list[str]) -> str:
    """The pronunciation slot a recording fills: UK, US, another accent, or
    "other" when nobody said (Lingua Libre speakers)."""
    for a in ("UK", "US"):
        if a in accent:
            return a
    return accent[0] if accent else "other"


def _accents(tags) -> list[str]:
    out = []
    for t in tags or []:
        a = ACCENTS.get(t)
        if a and a not in out:
            out.append(a)
    return out


def form_field(pos: str, tags: set[str], target: str) -> str | None:
    if tags & LOW_TAGS or tags & FORM_SKIP:
        return None
    if target == "en":
        if pos == "verb":
            if {"participle", "past"} <= tags:
                return "verb_past_participle"
            if {"participle", "present"} <= tags:
                return "verb_present_participle"
            if {"third-person", "singular", "present"} <= tags:
                return "verb_third_person"
            if "past" in tags and "participle" not in tags:
                return "verb_past"
        if pos == "noun" and "plural" in tags and "possessive" not in tags:
            return "noun_plural"
        if pos == "adj":
            if "comparative" in tags:
                return "adj_comparative"
            if "superlative" in tags:
                return "adj_superlative"
    if target == "fr":
        if pos == "verb":
            if {"participle", "past"} <= tags and not tags & {"feminine", "plural"}:
                return "fr_past_participle"
            if {"indicative", "present"} <= tags:
                person = next((n for p, n in (("first-person", "1"), ("second-person", "2"),
                                              ("third-person", "3")) if p in tags), None)
                number = "s" if "singular" in tags else "p" if "plural" in tags else None
                if person and number:
                    return f"fr_present_{person}{number}"
        if pos in ("adj", "noun"):
            if {"feminine", "plural"} <= tags:
                return "fr_feminine_plural"
            if "feminine" in tags and "plural" not in tags:
                return "fr_feminine"
            if "plural" in tags and "feminine" not in tags:
                return "fr_plural"
    return None


class Kaikki(SourceAdapter):
    key = "kaikki"

    def url(self, target: str, word: str) -> str:
        w = word.strip()
        q = urllib.parse.quote
        return (f"https://kaikki.org/dictionary/{DICT_NAME[target]}/meaning/"
                f"{q(w[0])}/{q(w[:2])}/{q(w)}.jsonl")

    def download_snapshot(self, language, snapshot_dir):
        # The full dumps are multi-GB; this project reads per-headword JSONL
        # (identical records) and records what it has cached.
        folder = http.CACHE / "kaikki"
        files = list(folder.glob("*.json")) if folder.exists() else []
        indexed = config.KAIKKI_INDEX.is_file()
        return {"version": "local SQLite index" if indexed else "per-headword JSONL (on demand)",
                "url": f"https://kaikki.org/dictionary/{DICT_NAME.get(language, 'English')}/",
                "path": str(folder), "row_count": len(files),
                "details": {"mode": "local_index" if indexed else "on_demand",
                            "index": str(config.KAIKKI_INDEX) if indexed else None,
                            "cached_headwords": len(files),
                            "note": "全量 JSONL 資料包 2–3 GB；逐字 JSONL 內容相同，隨查隨存。"}}

    def fetch(self, ctx: Context):
        word = ctx.display or ctx.lemma
        data = kaikki_index.lookup(ctx.target, word)
        if data is None:
            data, status = http.get("kaikki", word, self.url(ctx.target, word),
                                    timeout=ctx.timeout, retries=ctx.retries,
                                    refresh=ctx.refresh, lines=True)
        code = LANG_CODE[ctx.target]
        entries = [e for e in (data or []) if e.get("lang_code") == code
                   and normalize_lemma(e.get("word", ""), ctx.target) == ctx.lemma]
        return entries

    def other(self, ctx: Context, word: str) -> list[dict]:
        """Another headword's entries (for related words' native meanings)."""
        k = ("kaikki-other", ctx.target, word)
        if k not in ctx.memo:
            sub = Context(ctx.target, ctx.native, normalize_lemma(word, ctx.target), word,
                          refresh=ctx.refresh, timeout=ctx.timeout, retries=ctx.retries)
            try:
                ctx.memo[k] = self.fetch(sub)
            except http.SourceError:
                ctx.memo[k] = None
        return ctx.memo[k] or []

    def prefetch(self, ctx: Context, words: list[str]):
        """Fetch several other headwords at once (kaikki.org answers slowly,
        ~1–4 s per word; the rate limiter still spaces the requests)."""
        todo = [w for w in dict.fromkeys(words) if ("kaikki-other", ctx.target, w) not in ctx.memo]
        if len(todo) > 1:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda w: self.other(ctx, w), todo))

    # ── normalize ──

    def senses(self, entries, ctx) -> list[dict]:
        out, seen = [], set()
        for e in entries:
            pos = _pos(e)
            if not pos:
                continue
            real = [s for s in e.get("senses", []) if _gloss(s) and not _is_form_of(s)]
            for s in real or [s for s in e.get("senses", []) if _gloss(s)][:1]:
                g = _gloss(s)
                k = sense_key(pos, g)
                if k in seen:
                    continue
                seen.add(k)
                tags = set(s.get("tags", []))
                out.append({"pos": pos, "gloss": g, "sense_key": k, "sense": s, "entry": e,
                            "low": bool(tags & LOW_TAGS), "form_of": _is_form_of(s)})
        return out

    def normalize(self, f: str, entries, ctx: Context) -> list[Candidate]:
        if not entries:
            return []
        t = ctx.target
        C = []

        def add(value, key, slot="", conf=1.0, rid="", lang=None, raw=None):
            C.append(Candidate(f, lang or t, value, key, slot=slot, confidence=conf,
                               source_record_id=rid, raw_value=raw))

        word = entries[0].get("word", ctx.lemma)
        if f == "pos":
            for e in entries:
                p = _pos(e)
                if p and p != "name":
                    add({"pos": p}, p, slot=p, rid=f"{word}#{e.get('pos')}")
        elif f == "definition":
            gloss_lang = "en"  # English Wiktionary glosses are English
            for s in self.senses(entries, ctx):
                if s["pos"] == "name":
                    continue
                # A later etymology (sofa 2: a Mali Empire soldier) is a
                # different word that happens to share the spelling; the
                # label lets the app keep it off the card's main meaning.
                ety = str(s["entry"].get("etymology_number") or "")
                labels = sorted(set(s["sense"].get("tags", [])) & LABEL_TAGS)
                if ety.isdigit() and int(ety) > 1:
                    labels.append(f"etymology-{ety}")
                add({"pos": s["pos"], "gloss": s["gloss"], "sense_key": s["sense_key"],
                     "labels": labels,
                     "gloss_language": gloss_lang},
                    s["sense_key"], slot=s["pos"], conf=0.5 if s["low"] or s["form_of"] else 1.0,
                    rid=s["sense"].get("senseid", [""])[0] if isinstance(
                        s["sense"].get("senseid"), list) else "", lang=gloss_lang,
                    raw={"glosses": s["sense"].get("glosses"), "tags": s["sense"].get("tags")})
        elif f == "native_definition":
            self._native_definitions(entries, ctx, add)
        elif f == "usage_labels":
            for s in self.senses(entries, ctx):
                for tag in sorted(set(s["sense"].get("tags", [])) & LABEL_TAGS):
                    add({"label": tag, "sense_key": s["sense_key"]}, f"{tag}", slot="")
        elif f in ("ipa", "accent_labels", "audio", "homophones", "phonemes"):
            self._sounds(f, entries, ctx, add)
        elif f == "syllables":
            for e in entries:
                for h in e.get("hyphenations") or []:
                    parts = h.get("parts") or []
                    if parts:
                        add({"syllables": parts, "count": len(parts)}, "·".join(parts))
                if isinstance(e.get("hyphenation"), list) and e["hyphenation"]:
                    parts = e["hyphenation"]
                    add({"syllables": parts, "count": len(parts)}, "·".join(parts))
        elif f == "verb_base":
            for e in entries:
                if _pos(e) != "verb":
                    continue
                bases = [fo.get("word") for s in e.get("senses", []) for fo in s.get("form_of", [])]
                if bases and all(_is_form_of(s) for s in e.get("senses", [])):
                    for b in bases:
                        add({"form": b}, b.lower(), conf=0.9, rid=f"{word}#verb")
                else:
                    add({"form": word}, word.lower(), rid=f"{word}#verb")
        elif f in catalog.FORM_FIELDS:
            # A headword that is itself a form (grated, ate, eaten, apples,
            # better) shares its base word's whole table: eat, ate and eaten
            # all show eat / ate / eaten / eating / eats.
            # Only the same part of speech: "grated" (verb form of grate) takes
            # grate's verb forms, never grate's adjective or noun forms.
            sources, bases = [], []
            for e in entries:
                senses = e.get("senses", [])
                of = [fo.get("word") for s in senses for fo in s.get("form_of", []) if fo.get("word")]
                if senses and of and all(_is_form_of(s) for s in senses):
                    bases += [(b, _pos(e)) for b in of if b.lower() != word.lower()]
                else:
                    sources.append((e, word, False))
            for base, pos in dict.fromkeys(bases):
                sources += [(be, base, True) for be in self.other(ctx, base) if _pos(be) == pos]
            for e, owner, shared in sources:
                pos = _pos(e)
                for fo in e.get("forms", []):
                    form = (fo.get("form") or "").strip()
                    if not form or form.startswith("-") or (form == owner):
                        continue
                    if form_field(pos or "", set(fo.get("tags", [])), t) == f:
                        add({"form": form, **({"base": owner} if shared else {})}, form.lower(),
                            conf=(0.6 if " " in form else 1.0) * (0.95 if shared else 1),
                            rid=f"{owner}#{e.get('pos')}", raw=fo)
            C.sort(key=lambda c: -c.confidence)
        elif f in ("synonyms", "antonyms", "hypernyms", "hyponyms", "related"):
            senses = self.senses(entries, ctx)
            for s in senses:
                for r in s["sense"].get(f, []):
                    self._relation(add, r, s["pos"], s["sense_key"])
            for e in entries:
                for r in e.get(f, []):
                    self._relation(add, r, _pos(e), self._match_sense(senses, r.get("sense"),
                                                                       _pos(e)))
            C[:] = by_frequency(C, t)
        elif f == "derived_terms":
            for e in entries:
                for d in e.get("derived", []):
                    dw = (d.get("word") or "").strip()
                    if dw and " " not in dw and "-" not in dw and dw.lower() != word.lower():
                        add({"word": dw}, dw.lower(), rid=f"{word}#{e.get('pos')}")
            C[:] = by_frequency(C, t)
        elif f in ("root", "prefix", "suffix"):
            for part, kind in self._morphemes(entries):
                if kind == f:
                    add({"morpheme": part}, part.lower())
        elif f == "morphemes":
            bd = self._breakdown(entries, ctx)
            if bd:
                add(bd, bd["summary"], conf=0.95, rid=f"{word}#etymology")
        elif f == "morphemes_native":
            from .morph import part_slot
            missing = ctx.memo.get(("missing_slots", f))
            for bd in ctx.items("morphemes")[:1]:
                todo = [(i, p) for i, p in enumerate(bd.get("parts", [])) if p.get("free")
                        and (missing is None or part_slot(i, p) in missing)]
                self.prefetch(ctx, [p["part"] for _, p in todo if p["part"].lower() != ctx.lemma])
                for i, p in todo:
                    w = p["part"]
                    if w.lower() == ctx.lemma:
                        # The word itself (one whole part): its own first
                        # meaning, not a translation-table guess (leaf ≠
                        # 植物最顯著器官, apply ≠ 蘋果).
                        own = next((i.get("text") for i in ctx.items("native_definition")
                                    if i.get("text")), None)
                        text = "、".join(re.split(r"[、，,；;]", own)[:2]) if own else \
                            self._word_meaning(entries, ctx)
                    else:
                        text = self._word_meaning(self.other(ctx, w), ctx)
                    if text:
                        slot = part_slot(i, p)
                        add({"slot": slot, "part": w, "text": text}, slot, slot=slot, conf=0.8,
                            lang=ctx.native, rid=w)
        elif f in ("origin_language", "original_form"):
            for lang_code, lang_name, term in self._origins(entries):
                if f == "origin_language":
                    add({"language": lang_name, "code": lang_code}, lang_code)
                else:
                    add({"form": term, "language": lang_name, "code": lang_code},
                        f"{lang_code}:{term}")
        elif f == "etymology_text":
            for e in entries:
                text = _clean_etymology(e.get("etymology_text", ""))
                if text:
                    # How many affix templates: 0 means Wiktionary saw no English
                    # word formation here (used by 本機構詞分析).
                    add({"text": text, "affix_templates": len(_affix_templates(e))},
                        fold(text)[:80], lang="en")
        elif f in ("example_sentences", "example_sense"):
            for s in self.senses(entries, ctx):
                for ex in s["sense"].get("examples", []):
                    text = (ex.get("text") or "").strip()
                    if not text or ex.get("type") == "quotation" or ex.get("ref"):
                        continue
                    k = example_key(text)
                    if f == "example_sentences":
                        add({"text": text, "sense_key": s["sense_key"],
                             "translation": ex.get("english") or ex.get("translation")},
                            k, rid=f"{word}#{s['sense_key']}")
                    else:
                        add({"example_key": k, "sense_key": s["sense_key"]}, k, slot=k)
            if f == "example_sense":
                wanted = {i.get("key") or example_key(i.get("text", ""))
                          for i in ctx.items("example_sentences")}
                C[:] = [c for c in C if c.slot in wanted]
        elif f == "derived_native_meaning" or f in catalog.RELATION_NATIVE:
            rel = "derived_terms" if f == "derived_native_meaning" else catalog.RELATION_NATIVE[f]
            missing = ctx.memo.get(("missing_slots", f))
            items = [i for i in ctx.items(rel) if i.get("word")
                     and (missing is None or i["word"].lower() in missing)]
            self.prefetch(ctx, [i["word"] for i in items])
            # A relation word without its own part of speech (Datamuse) is
            # read in the headword's: ample's related "big" is 大, not 大人.
            head_pos = [i["pos"] for i in ctx.items("pos") if i.get("pos")]
            for item in items:
                w = item.get("word", "")
                text = (self._word_meaning(self.other(ctx, w), ctx, item["pos"])
                        if item.get("pos") else
                        self._word_meaning(self.other(ctx, w), ctx, head_pos, loose=True))
                if text:
                    add({"word": w, "text": text}, w.lower(), slot=w.lower(), conf=0.8,
                        lang=ctx.native, rid=w)
        return C

    # ── helpers ──

    def _relation(self, add, r: dict, pos, skey):
        w = (r.get("word") or "").strip()
        if not w or w.startswith("Thesaurus:") or len(w.split()) > 3:
            return
        add({"word": w, "pos": pos, "sense_key": skey, "note": r.get("sense") or ""},
            w.lower(), conf=0.9 if skey else 0.8)

    def _match_sense(self, senses, text, pos=None):
        """The sense whose gloss best matches a translation / relation
        table's sense label."""
        if not text:
            return None
        want = {_stem(t) for t in tokens(text)} - STOP
        best, score = None, 0.0
        for s in senses:
            if pos and s["pos"] != pos:
                continue
            # plants ~ plant: leaf's 「part of a plant」 table is the first
            # sense (…features of most vegetative plants), not 「anything
            # resembling the leaf of a plant」.
            have = {_stem(t) for t in tokens(" ".join(s["sense"].get("glosses") or [s["gloss"]]))} - STOP
            if not want or not have:
                continue
            sc = len(want & have) / len(want)
            if sc > score:
                best, score = s["sense_key"], sc
        return best if score >= 0.34 else None

    def _native_definitions(self, entries, ctx: Context, add):
        native = ctx.native
        wanted = {i.get("sense_key") for i in ctx.items("definition")} or None
        senses = self.senses(entries, ctx)
        if ctx.target != "en":
            # English Wiktionary glosses of French / Chinese words are English.
            if native == "en":
                for s in senses:
                    if wanted is None or s["sense_key"] in wanted:
                        add({"sense_key": s["sense_key"], "text": s["gloss"]}, s["sense_key"],
                            slot=s["sense_key"], lang="en")
            return
        by_sense: dict[str, list[str]] = {}
        conf: dict[str, float] = {}
        for e in entries:
            pos = _pos(e)
            trs = list(e.get("translations", []))
            for s in e.get("senses", []):
                trs += [dict(t, sense=t.get("sense") or _gloss(s)) for t in s.get("translations", [])]
            for tr in trs:
                text = _native_word(tr, native)
                if not text:
                    continue
                k = self._match_sense(senses, tr.get("sense"), pos)
                c = 0.9
                if not k:
                    first = next((s for s in senses if s["pos"] == pos), None)
                    if not first:
                        continue
                    k, c = first["sense_key"], 0.5
                if wanted is not None and k not in wanted:
                    continue
                lst = by_sense.setdefault(k, [])
                if text not in lst:
                    lst.append(text)
                conf[k] = max(conf.get(k, 0), c)
        for k, words in by_sense.items():
            words = _without_erhua(words)
            add({"sense_key": k, "text": "、".join(words[:3])}, k, slot=k, conf=conf[k],
                lang=native, raw={"words": words})

    def _word_meaning(self, entries, ctx: Context, pos=None, loose=False) -> str | None:
        """A short native meaning for another word: the translations of its
        first translated sense (big → 大, not also the "adult" sense's 大人),
        from its entries in [pos] (one part of speech or several). A [loose]
        guess uses every entry only when none has that part of speech; an
        entry in the right part of speech without translations gives nothing
        rather than another part of speech's meaning (major ≠ 少校)."""
        wanted = {pos} if isinstance(pos, str) else set(pos or ())
        if wanted and len(entries) > 1:
            matching = [e for e in entries if _pos(e) in wanted]
            entries = matching if matching or not loose else entries
        for e in entries:
            words, first_sense = [], None
            for tr in e.get("translations", []):
                w = _native_word(tr, ctx.native)
                if not w:
                    continue
                sense = tr.get("sense") or ""
                if first_sense is None:
                    first_sense = sense
                elif sense != first_sense:
                    break
                if w not in words:
                    words.append(w)
            if words:
                return "、".join(_without_erhua(words)[:2])
        return None

    def _sounds(self, f, entries, ctx, add):
        for e in entries:
            for snd in e.get("sounds", []):
                acc = _accents(snd.get("tags"))
                ipa = snd.get("ipa")
                if f == "ipa" and ipa:
                    phonemic = ipa.startswith("/")
                    value = {"ipa": ipa, "accent": acc}
                    # wind (風) /wɪnd/ vs wind (纏繞) /waɪnd/: another
                    # etymology's sound is never the default.
                    ety = str(e.get("etymology_number") or "")
                    if ety.isdigit() and int(ety) > 1:
                        value["etymology"] = int(ety)
                    add(value, ipa, conf=1.0 if phonemic else 0.7)
                elif f == "phonemes" and ipa and ipa.startswith("/") and "US" in acc:
                    arpa = ipa_to_arpabet(ipa)
                    if arpa:
                        add({"phonemes": arpa, "system": "ARPAbet", "from_ipa": ipa},
                            arpa, conf=0.6)
                elif f == "accent_labels":
                    for a in acc:
                        add({"accent": a}, a)
                elif f == "audio":
                    url = snd.get("mp3_url") or snd.get("ogg_url")
                    if url:
                        acc = acc or file_accent(snd.get("audio"))
                        add({"url": url, "file": snd.get("audio"), "accent": acc,
                             "fallback_url": snd.get("ogg_url")}, url, slot=audio_slot(acc),
                            rid=snd.get("audio") or url)
                elif f == "homophones" and snd.get("homophone") and \
                        zipf(snd["homophone"], ctx.target) >= 2.0:
                    h = snd["homophone"]
                    add({"word": h, "note": "同音"}, h.lower())

    def _morphemes(self, entries):
        seen = set()
        for e in _main_etymology(entries):
            for tpl in _affix_templates(e):
                for p in parts_from_affix_template(tpl.get("args", {}), tpl["name"]) or []:
                    kind = "prefix" if p.endswith("-") and not p.startswith("-") else \
                        "suffix" if p.startswith("-") else "root"
                    if (p, kind) not in seen:
                        seen.add((p, kind))
                        yield p, kind

    def _breakdown(self, entries, ctx):
        """構詞拆解 from Wiktionary's affix markup, in order; English-word
        parts are split further where that says more (unhappy → un- + happy)."""
        from .morph import breakdown_value
        word = entries[0].get("word", ctx.lemma)
        origin = next((code for code, _, _ in self._origins(entries)), None)
        for e in _main_etymology(entries):
            for tpl in _affix_templates(e):
                args, name = normalize_affix_args(tpl.get("args", {}), tpl["name"])
                cleaned = parts_from_affix_template(args, name)
                if not cleaned or len(cleaned) < 2:
                    continue
                raws = [v for k, v in sorted(((k, v) for k, v in args.items()
                                              if k.isdigit() and int(k) >= 2),
                                             key=lambda kv: int(kv[0]))
                        if v and not v.startswith(":")]
                parts = []
                for n, c in enumerate(cleaned):
                    gloss = template_gloss(raws[n]) if n < len(raws) else None
                    rest = "".join(x.strip("-") for x in cleaned[n + 1:])
                    parts.append(_part(c, gloss, rest))
                parts = expand(parts, Evidence(origin))
                return breakdown_value(parts, "wiktionary")
        return None

    def _origins(self, entries):
        for e in _main_etymology(entries):
            for tpl in e.get("etymology_templates", []):
                name, args = tpl.get("name"), tpl.get("args", {})
                if name in ORIGIN_TEMPLATES and args.get("2") and args.get("3"):
                    code, term = args["2"], re.sub(r"<[^>]*>", "", args["3"])
                    yield code, LANG_NAMES.get(code, code), term
                    return
                if name == "etymon" and ":" in args.get("3", ""):
                    code, term = args["3"].split(":", 1)
                    term = re.sub(r"<[^>]*>", "", term)
                    yield code, LANG_NAMES.get(code, code), term
                    return


def _stem(token: str) -> str:
    """A plural or third-person -s off, for matching glosses."""
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def _main_etymology(entries: list[dict]) -> list[dict]:
    """The entries of the spelling's first etymology. A later one is another
    word spelt the same (flower 2 「one who flows」 = flow + -er; apply 2 =
    apple + -y), so its word formation and origin are not this word's."""
    if not entries:
        return entries
    main = str(entries[0].get("etymology_number") or "")
    return [e for e in entries if str(e.get("etymology_number") or "") in ("", main)]


def _affix_templates(entry: dict) -> list[dict]:
    """The entry's word-formation templates (affix, prefix, suffix,
    compound, … and {{ety|en|:af|…}})."""
    out = []
    for tpl in entry.get("etymology_templates", []):
        name, args = tpl.get("name"), tpl.get("args", {})
        if name in AFFIX_TEMPLATES and name != "blend":
            out.append(tpl)
        elif name == "ety" and str(args.get("2", "")).lstrip(":") in (
                "af", "affix", "pre", "prefix", "suf", "suffix", "com", "compound", "surf"):
            out.append(tpl)
    return out


def _part(c: str, gloss: str | None, rest: str) -> Part:
    """One part of a Wiktionary affix analysis, described from the table."""
    c = c.strip()
    if c.endswith("-") and not c.startswith("-"):
        kind, text = "prefix", c.rstrip("-")
    elif c.startswith("-"):
        kind, text = "suffix", c.lstrip("-").rstrip("-")
    else:
        kind, text = "root", c
    options = md.lookup(kind, text)
    if kind == "prefix":
        probe = Part(rest, "root", rest, free=True)
        options = [e for e in options if _prefix_meaning(e, rest, probe)] or options
    e = options[0] if options else None
    free = kind == "root" and (" " in text or en_zipf(text.lower()) >= 2.5)
    shown = {"prefix": f"{text}-", "suffix": f"-{text}"}.get(kind, text)
    return Part(text, kind, shown, gloss or (e.en if e and not free else None), None,
                e.origin if e else None, free)


STOP = {"a", "an", "the", "of", "to", "or", "and", "in", "on", "for", "with", "by", "as", "be",
        "is", "that", "which", "something", "someone", "one", "any", "used", "from", "at"}


def _without_erhua(words: list[str]) -> list[str]:
    """Taiwan usage has no Beijing 兒化: 門兒 goes when 門 is listed, 叉兒
    when 叉子 is (女兒, 嬰兒 stay — no 女 or 嬰 beside them)."""
    out = []
    for w in words:
        base = w[:-1]
        if len(w) >= 2 and w.endswith("兒") and any(
                o != w and (o == base or o.startswith(base)) for o in words):
            continue
        out.append(w)
    return out


def _native_word(tr: dict, native: str) -> str | None:
    word = (tr.get("word") or "").strip()
    if not word and native == "zh-TW":
        # A translation with a gloss sits in the note: 「電腦 /电脑 (diànnǎo,
        # literally "electric brain")」 is computer's 電腦 (問題回報 #103).
        m = re.match(r"\s*([㐀-鿿]+(?:\s*/\s*[㐀-鿿]+)?)\s*\(", tr.get("note") or "")
        word = m.group(1) if m else ""
    if not word:
        return None
    if native == "zh-TW":
        lang, tags = tr.get("lang", ""), set(tr.get("tags", []))
        mandarin = lang in ("Chinese Mandarin", "Mandarin") or (
            lang == "Chinese" and "Mandarin" in tags)
        if not mandarin:
            return None
        trad, _, simp = word.partition("/")
        trad = trad.strip()
        if not simp and trad:
            conv = opencc("s2twp", trad)
            trad = conv or trad
        return trad or None
    if native == "fr":
        return word if tr.get("lang_code", tr.get("code")) == "fr" else None
    if native == "en":
        return word if tr.get("lang_code", tr.get("code")) == "en" else None
    return None


_TREE_TAG = re.compile(r"(?:der|bor|inh|lbor|slbor|cal|uder)\.\??$")


def _clean_etymology(text: str) -> str:
    """The first paragraph of the etymology, without the 「Etymology tree」
    lines (short "Language form" nodes) wiktextract puts before it."""
    lines = [ln.strip() for ln in (text or "").strip().split("\n")]
    # The 「PIE word」 box: a heading and the root ("*dwóh₁").
    if lines and lines[0] == "PIE word":
        lines = lines[2:] if len(lines) > 1 and lines[1].startswith("*") else lines[1:]
    if lines and lines[0] == "Etymology tree":
        # The tree ends with the headword's own node ("English green");
        # earlier nodes can end in a relation tag ("Latin pannabor.?") and
        # look like sentences.
        # A derived word's tree also has its base's node ("English crumble"
        # before "English crumbly"), so the last one before the text.
        end = next((j for j, ln in enumerate(lines) if len(ln.split()) > 6), len(lines))
        last = max((j for j, ln in enumerate(lines[1:end], 1)
                    if ln.startswith("English ") and len(ln.split()) <= 6
                    and not ln.endswith((".", ","))), default=None)
        if last is not None:
            lines = lines[last + 1:]
        else:
            i = 1
            # Tree nodes ("Old English æppel", "▲") are short and have no
            # final punctuation or end in a relation tag; the text is a
            # sentence.
            while i < len(lines) and len(lines[i].split()) <= 6 and (
                    not lines[i].rstrip().endswith((".", ")", "”", "\""))
                    or _TREE_TAG.search(lines[i])):
                i += 1
            lines = lines[i:]
    first = next((ln for ln in lines if ln), "")
    return first[:500]
