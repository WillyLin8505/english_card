"""Sources computed on this machine: word lists, frequency, CEFR, rules,
the lexicon's own entries, and the device TTS marker."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from sqlalchemy import func, select

from .. import catalog, config
from ..text import example_key, fold, tokens
from .base import Candidate, Context, SourceAdapter

CEFR_FILE = config.REPO / "app" / "assets" / "cefr_en.json"
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
WF_LANG = {"en": "en", "fr": "fr", "zh-TW": "zh"}
# British English is the default playback (spec section 7).
TTS_LOCALE = {"en": "en-GB", "fr": "fr-FR", "zh-TW": "zh-TW"}


@lru_cache(maxsize=1)
def cefr_list() -> dict:
    return json.loads(CEFR_FILE.read_text(encoding="utf-8"))["words"]


def _zipf(word: str, lang: str) -> float:
    try:
        from wordfreq import zipf_frequency
        return zipf_frequency(word, WF_LANG.get(lang, lang))
    except ImportError:
        return 0.0


class WordFreq(SourceAdapter):
    key = "wordfreq"

    def download_snapshot(self, language, snapshot_dir):
        import wordfreq
        return {"version": f"wordfreq {getattr(wordfreq, '__version__', '')}".strip(),
                "url": "https://github.com/rspeer/wordfreq", "path": wordfreq.__file__,
                "details": {"bundled": True}}

    def normalize(self, f, raw, ctx):
        if f != "frequency":
            return []
        z = _zipf(ctx.display or ctx.lemma, ctx.target)
        if z <= 0:
            return []
        return [Candidate(f, ctx.target, {"zipf": round(z, 2)}, str(round(z, 2)))]


class CefrJ(SourceAdapter):
    key = "cefrj"

    def download_snapshot(self, language, snapshot_dir):
        files = sorted((config.REPO / "data" / "raw").glob("*vocabulary-profile*.csv"))
        return {"version": "CEFR-J 1.5 + Octanove C1/C2 1.0", "path": str(CEFR_FILE),
                "url": "https://github.com/openlanguageprofiles/olp-en-cefrj",
                "files": files + [CEFR_FILE], "row_count": len(cefr_list())}

    def normalize(self, f, raw, ctx):
        if f != "cefr" or ctx.target != "en":
            return []
        hit = cefr_list().get(ctx.lemma)
        if not hit:
            return []
        by_pos = hit[1]
        level = min(by_pos.values(), key=LEVELS.index)
        return [Candidate(f, "en", {"level": level, "by_pos": by_pos}, level,
                          source_record_id=ctx.lemma)]


def _edit1(a: str, b: str) -> str | None:
    """How b differs from a by one edit, or None."""
    if a == b or abs(len(a) - len(b)) > 1:
        return None
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        if len(d) == 1:
            return f"{a[d[0]]}→{b[d[0]]}"
        if len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]]:
            return f"{a[d[0]]}{a[d[1]]}↔{b[d[0]]}{b[d[1]]}"
        return None
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long_[i]:
        i += 1
    if short[i:] != long_[i + 1:]:
        return None
    return f"+{long_[i]}" if len(b) > len(a) else f"-{long_[i]}"


@lru_cache(maxsize=3)
def _wordlist(lang: str) -> tuple[str, ...]:
    words: set[str] = set()
    try:
        from wordfreq import top_n_list
        words |= {w for w in top_n_list(WF_LANG.get(lang, lang), 60000) if w.isalpha()}
    except ImportError:
        pass
    if lang == "en":
        words |= {w for w in cefr_list() if w.isalpha()}
    return tuple(sorted(words))


class KaikkiWordlist(SourceAdapter):
    """Spelling neighbours: words one edit away. The spec names the Kaikki
    headword list; without the multi-GB dump this uses the wordfreq top
    60k (+ CEFR-J for English) as the word list — see the source note."""
    key = "kaikki_wordlist"

    def download_snapshot(self, language, snapshot_dir):
        return {"version": "wordfreq top-60k + CEFR-J", "row_count": len(_wordlist(language)),
                "details": {"note": "Kaikki 全量字表需下載 2–3 GB 資料包；目前以常用字表代替。"}}

    def normalize(self, f, raw, ctx):
        if f != "similar_spelling" or " " in ctx.lemma:
            return []
        w = ctx.lemma
        skip = {w + "s", w + "es", w + "ed", w + "d", w + "ing", w + "'s"}
        hits = []
        for x in _wordlist(ctx.target):
            if abs(len(x) - len(w)) > 1 or x in skip:
                continue
            diff = _edit1(w, x)
            if diff:
                hits.append((x, diff))
        hits.sort(key=lambda h: -_zipf(h[0], ctx.target))
        from .base import by_frequency
        return by_frequency([
            Candidate(f, ctx.target, {"word": x, "difference": diff, "note": "拼字相近"}, x,
                      confidence=0.8) for x, diff in hits[:20]
        ], ctx.target)


SUFFIX_POS = {"ness": ("adj", "noun", "名詞化"), "ity": ("adj", "noun", "名詞化"),
              "ment": ("verb", "noun", "名詞化"), "tion": ("verb", "noun", "名詞化"),
              "sion": ("verb", "noun", "名詞化"), "er": ("verb", "noun", "動作者"),
              "or": ("verb", "noun", "動作者"), "ist": ("noun", "noun", "從事者"),
              "ly": ("adj", "adv", "副詞化"), "ful": ("noun", "adj", "形容詞化"),
              "less": ("noun", "adj", "否定形容詞"), "able": ("verb", "adj", "可…的"),
              "ible": ("verb", "adj", "可…的"), "ous": ("noun", "adj", "形容詞化"),
              "al": ("noun", "adj", "形容詞化"), "ive": ("verb", "adj", "形容詞化"),
              "ize": ("adj", "verb", "動詞化"), "ise": ("adj", "verb", "動詞化"),
              "en": ("adj", "verb", "動詞化"), "ify": ("adj", "verb", "動詞化"),
              "hood": ("noun", "noun", "狀態"), "ship": ("noun", "noun", "身分關係"),
              "y": ("noun", "adj", "形容詞化"), "ing": ("verb", "noun", "動名詞"),
              "ance": ("verb", "noun", "名詞化"), "ence": ("verb", "noun", "名詞化")}
PREFIX = {"un": "否定", "in": "否定", "im": "否定", "dis": "否定／相反", "re": "再次",
          "mis": "錯誤", "pre": "之前", "over": "過度", "under": "不足", "non": "非",
          "anti": "反對", "sub": "下／次", "super": "超"}


def derivation(base: str, derived: str) -> dict | None:
    b, d = base.lower(), derived.lower()
    stems = {b, b[:-1] if b.endswith(("e", "y")) else b}
    if b.endswith("y"):
        stems.add(b[:-1] + "i")
    for suf, (frm, to, label) in sorted(SUFFIX_POS.items(), key=lambda kv: -len(kv[0])):
        if d.endswith(suf) and any(d[:-len(suf)] in (s, s + s[-1:]) for s in stems if s):
            return {"type": "suffix", "affix": f"-{suf}", "from_pos": frm, "to_pos": to,
                    "label": label}
    for pre, label in PREFIX.items():
        if d == pre + b:
            return {"type": "prefix", "affix": f"{pre}-", "label": label}
    if d.startswith(b) or b.startswith(d) or b in d.split():
        return {"type": "compound_or_other", "label": "同字根"}
    # A dictionary listed it as derived; the rules just can't name how.
    return {"type": "derived", "label": "衍生詞"}


def sentence_level(text: str, ignore: frozenset[str] | set[str] = frozenset()) -> str:
    """Estimate sentence CEFR from vocabulary and sentence length.

    Vocabulary dominates; length is a floor so a long sentence made from
    common words is not incorrectly labelled A1. [ignore] are the forms of
    the word being taught: a learner meets it in the sentence on purpose, so
    only the words around it set the level (an A2 word can have A1
    sentences). This is a local estimate, not an official CEFR annotation.
    """
    levels = cefr_list()
    terms = tokens(text)
    worst = 0
    for t in terms:
        if t in ignore:
            continue
        hit = levels.get(t)
        if not hit:
            continue
        lv = min(hit[1].values(), key=LEVELS.index)
        worst = max(worst, LEVELS.index(lv))
    n = len(terms)
    length_floor = 0 if n <= 6 else 1 if n <= 10 else 2 if n <= 15 else 3 if n <= 22 else 4 \
        if n <= 30 else 5
    return LEVELS[max(worst, length_floor)]


def suffix_pos(word: str) -> str | None:
    """A word's part of speech from its ending, when nothing lists it."""
    w = word.lower()
    for ends, pos in ((("ly",), "adv"), (("ness", "tion", "sion", "ment", "ity", "ship", "hood",
                                           "ism", "ist", "er", "or", "ance", "ence", "age"), "noun"),
                      (("ful", "ous", "ive", "able", "ible", "al", "ic", "less", "ish", "y"), "adj"),
                      (("ize", "ise", "ify", "ate", "en"), "verb")):
        if len(w) > 4 and w.endswith(ends):
            return pos
    return "noun" if w.isalpha() else None


def regular_plural(noun: str) -> str:
    """The regular English plural (of a phrase: of its last word)."""
    *head, w = noun.split(" ")
    if re.search(r"[^aeiou]y$", w):
        p = w[:-1] + "ies"
    elif re.search(r"(s|x|z|ch|sh)$", w):
        p = w + "es"
    else:
        p = w + "s"
    return " ".join([*head, p])


IRREGULAR_FORMS = {
    "be": {"am", "is", "are", "was", "were", "been", "being"},
    "child": {"children"}, "person": {"people"}, "man": {"men"},
    "woman": {"women"}, "mouse": {"mice"}, "goose": {"geese"},
    "tooth": {"teeth"}, "foot": {"feet"}, "go": {"went", "gone"},
    "do": {"did", "done"}, "have": {"had"}, "make": {"made"},
    "take": {"took", "taken"}, "come": {"came"}, "see": {"saw", "seen"},
    "get": {"got", "gotten"}, "say": {"said"}, "know": {"knew", "known"},
    "think": {"thought"}, "buy": {"bought"}, "bring": {"brought"},
    "teach": {"taught"}, "catch": {"caught"}, "run": {"ran"},
    "eat": {"ate", "eaten"}, "drink": {"drank", "drunk"},
    "write": {"wrote", "written"}, "speak": {"spoke", "spoken"},
    "drive": {"drove", "driven"}, "give": {"gave", "given"},
    "choose": {"chose", "chosen"}, "fall": {"fell", "fallen"},
    "feel": {"felt"}, "leave": {"left"}, "keep": {"kept"},
    "sleep": {"slept"}, "meet": {"met"}, "good": {"better", "best"},
    "bad": {"worse", "worst"},
}

ENGLISH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "can", "could", "did", "do", "does", "for", "from", "had", "has", "have",
    "he", "her", "hers", "him", "his", "i", "if", "in", "into", "is", "it",
    "its", "me", "mine", "my", "of", "on", "or", "our", "ours", "she", "that",
    "the", "their", "theirs", "them", "they", "this", "those", "to", "was", "we",
    "were", "what", "when", "where", "which", "who", "will", "with", "would",
    "you", "your", "yours",
}


def plausible_form(lemma: str, form: str) -> bool:
    """Conservative English inflection check for source-provided forms."""
    lemma, form = (lemma or "").casefold(), (form or "").casefold()
    if lemma == form or form in IRREGULAR_FORMS.get(lemma, set()):
        return True
    if " " in lemma:
        before, head = lemma.rsplit(" ", 1)
        return form.startswith(before + " ") and plausible_form(head, form[len(before) + 1:])
    if form.startswith(lemma) and form[len(lemma):] in {"s", "es", "d", "ed", "ing", "er", "est"}:
        return True
    stems = {lemma}
    if lemma and lemma[-1].isalpha() and lemma[-1] not in "aeiouy":
        stems.add(lemma + lemma[-1])
    if lemma.endswith("e"):
        stems.add(lemma[:-1])
    if lemma.endswith("y"):
        stems.add(lemma[:-1] + "i")
    if lemma.endswith("f"):
        stems.add(lemma[:-1] + "v")
    if lemma.endswith("fe"):
        stems.add(lemma[:-2] + "v")
    return any(form.startswith(stem)
               and form[len(stem):] in {"s", "es", "d", "ed", "ing", "er", "est"}
               for stem in stems)


def word_level(word: str, language: str = "en") -> str:
    """A word's CEFR level: its easiest CEFR-J level when listed, else an
    estimate from how common it is (a phrase counts as its hardest word)."""
    from .base import frequency_profile
    w = (word or "").strip().lower()
    hit = cefr_list().get(w) if language == "en" else None
    if hit:
        return min(hit[1].values(), key=LEVELS.index)
    parts = tokens(w) if language == "en" else [w]
    if len(parts) > 1:
        return max((word_level(p, language) for p in parts), key=LEVELS.index)
    return frequency_profile(round(_zipf(w, language), 1))["cefr"]


def word_forms(ctx: Context) -> frozenset[str]:
    """The headword and its inflected forms, lower case."""
    forms = {ctx.lemma.lower()}
    for k in catalog.FORM_FIELDS:
        for i in ctx.items(k):
            if i.get("form") and (ctx.target != "en" or plausible_form(ctx.lemma, i["form"])):
                forms.add(i["form"].lower())
    if ctx.target == "en" and " " not in ctx.lemma:
        w = ctx.lemma.lower()
        stem = w[:-1] if w.endswith("e") else w
        pos = {i.get("pos") for i in ctx.items("pos")}
        if "noun" in pos:
            forms.add(regular_plural(w))
        if "verb" in pos:
            forms |= {w + "s", w + "es", w + "ed", w + "d", stem + "ing",
                      (w[:-1] + "ies") if w.endswith("y") else w + "s",
                      (w[:-1] + "ied") if w.endswith("y") else w + "ed"}
        if "adj" in pos or "adjective" in pos:
            forms |= {w + "er", w + "est"}
        forms |= IRREGULAR_FORMS.get(w, set())
    return frozenset(forms)


RARE_SENSE_LABELS = {"obsolete", "archaic", "dated", "rare", "slang", "humorous", "nonstandard",
                     "historical", "vulgar", "derogatory", "offensive", "euphemistic", "poetic",
                     "pronunciation-spelling", "eye-dialect"}


class LocalCalc(SourceAdapter):
    key = "local_calc"

    def normalize(self, f, raw, ctx):
        C = []
        if f == "cefr" and ctx.target == "en":
            # Not in CEFR-J: estimated from frequency, and marked so.
            level = word_level(ctx.lemma)
            C.append(Candidate(f, "en", {"level": level, "by_pos": {}, "estimate": True,
                                         "cefr_source": "frequency_estimate"}, level,
                               confidence=0.5, source_record_id=ctx.lemma))
        elif f == "ipa" and ctx.target == "en" and " " in ctx.lemma:
            # A phrase: its words' pronunciations (cutting board).
            parts = [(cefr_list().get(w) or [None, None, None])[2] for w in ctx.lemma.split()]
            if parts and all(parts):
                ipa = "/" + " ".join(p.strip("/") for p in parts) + "/"
                C.append(Candidate(f, "en", {"ipa": ipa, "accent": "US", "composed": True}, ipa,
                                   confidence=0.6, source_record_id=ctx.lemma))
        elif f == "noun_plural" and ctx.target == "en":
            plural = regular_plural(ctx.lemma)
            last = plural.split()[-1]
            # Only a plural people write (not "informations").
            if " " in plural or _zipf(last, "en") >= 1.5:
                C.append(Candidate(f, "en", {"form": plural, "tags": ["plural"], "rule": True},
                                   plural.lower(), confidence=0.6))
        elif f == "derived_pos":
            for item in ctx.items("derived_terms"):
                w = item.get("word", "")
                rel = derivation(ctx.lemma, w) or {}
                hit = cefr_list().get(w.lower()) or cefr_list().get(w.lower().split()[-1]) \
                    if w else None
                pos = rel.get("to_pos") or (next(iter(hit[1])) if hit else None) \
                    or ("phrase" if " " in w or "'" in w else suffix_pos(w))
                if pos:
                    C.append(Candidate(f, ctx.target, {"word": w, "pos": pos}, w.lower(),
                                       slot=w.lower(), confidence=0.5))
        elif f == "derivation_relation":
            for item in ctx.items("derived_terms"):
                w = item.get("word", "")
                rel = derivation(ctx.lemma, w)
                if rel:
                    C.append(Candidate(f, ctx.target, {"word": w, **rel}, w.lower(),
                                       slot=w.lower(), confidence=0.7))
        elif f == "example_difficulty":
            for item in ctx.items("example_sentences"):
                k = item.get("key") or example_key(item.get("text", ""))
                if ctx.target == "en":
                    lv = item.get("level") or sentence_level(item.get("text", ""))
                else:
                    n = len(tokens(item.get("text", ""))) or len(item.get("text", ""))
                    lv = "A1" if n <= 5 else "A2" if n <= 8 else "B1" if n <= 12 else "B2"
                if lv:
                    C.append(Candidate(f, ctx.target, {"example_key": k, "level": lv}, k, slot=k,
                                       confidence=0.6))
        elif f == "example_sense":
            senses = ctx.items("definition")
            forms = word_forms(ctx)
            verb_only = _verb_only_forms(ctx)
            by_pos: dict[str, list[dict]] = {}
            for x in senses:
                by_pos.setdefault(x.get("pos"), []).append(x)
            try:
                listed = [{"adj.": "adj", "adv.": "adv"}.get(p, p) for p in
                          ((cefr_list().get(ctx.lemma) or [None, {}])[1] or {})]
            except Exception:  # noqa: BLE001 — no list: the most senses
                listed = []
            main_pos = next((p for p in listed if p in by_pos),
                            max(by_pos, key=lambda p: len(by_pos[p])) if by_pos else None)
            # A homograph: another etymology inside a main usage (wind the
            # verb 纏繞), not a rare extra one (apply's adjective 「apple-y」).
            # It is also pronounced differently (wind /wɪnd/, /waɪnd/; bow,
            # tear) — pasta's obscure second etymology is not one.
            main = set(listed) or {main_pos}
            ipas = ctx.items("ipa")
            first_ipa = next((_bare_ipa(i.get("ipa")) for i in ipas if not i.get("etymology")), "")
            other_ipa = {_bare_ipa(i.get("ipa")) for i in ipas if (i.get("etymology") or 0) > 1}
            homograph = bool(first_ipa and other_ipa - {first_ipa}) and any(
                str(l).startswith("etymology-") for x in senses
                if x.get("pos") in main for l in (x.get("labels") or []))
            for item in ctx.items("example_sentences"):
                k = item.get("key") or example_key(item.get("text", ""))
                if item.get("sense_key") and any(s.get("sense_key") == item["sense_key"]
                                                 for s in senses):
                    C.append(Candidate(f, ctx.target, {"example_key": k,
                                                       "sense_key": item["sense_key"]}, k,
                                       slot=k, confidence=0.9))
                    continue
                use = _usage_pos(item.get("text", ""), forms, verb_only, ctx.lemma)
                if use == "other":
                    continue  # 「the wound」: a verb form used as a noun is another word
                words = set(tokens(item.get("text", ""))) - ENGLISH_STOPWORDS - forms
                ranked = []
                for s in senses:
                    if use and s.get("pos") and s.get("pos") != use and any(
                            x.get("pos") == use for x in senses):
                        continue  # mugged is the verb, the mug the noun
                    gloss = set(tokens(s.get("gloss", ""))) - ENGLISH_STOPWORDS - forms
                    ranked.append((len(words & gloss), s))
                ranked.sort(key=lambda pair: pair[0], reverse=True)
                score, best = ranked[0] if ranked else (0, None)
                second = ranked[1][0] if len(ranked) > 1 else 0
                # Owner decision (問題回報 #87, 2026-10-01): one word shared
                # with a gloss is evidence enough.
                if best and score >= 1 and score > second:
                    C.append(Candidate(f, ctx.target, {"example_key": k,
                                                       "sense_key": best.get("sense_key")}, k,
                                       slot=k, confidence=0.5))
                    continue
                # A homograph (wind 風／纏繞, bow, tear: senses of another
                # etymology) still needs that evidence.
                if homograph:
                    continue
                # Otherwise the main usage's first common sense: the part of
                # speech the sentence shows, else the CEFR-J listed one.
                usage = use if use in by_pos else main_pos
                first = next((x for x in by_pos.get(usage, []) if not _rare_sense(x)),
                             (by_pos.get(usage) or [None])[0])
                if first is not None:
                    C.append(Candidate(f, ctx.target, {"example_key": k,
                                                       "sense_key": first.get("sense_key")}, k,
                                       slot=k, confidence=0.4))
        elif f == "stress":
            for item in ctx.items("ipa"):
                ipa = item.get("ipa", "")
                if "ˈ" in ipa:
                    before = ipa.split("ˈ")[0]
                    vowels = len(re.findall(r"[aeiouæɑɒɔəɛɪʊʌɜɝɚ]+", before))
                    C.append(Candidate(f, ctx.target, {"primary_syllable": vowels + 1,
                                                       "from_ipa": ipa}, str(vowels + 1),
                                       confidence=0.7))
                    break
        return C


DETERMINERS = {"a", "an", "the", "my", "your", "his", "her", "its", "our", "their", "this",
               "that", "these", "those", "some", "any", "no", "every", "each", "another"}


PARTICLES = {"out", "up", "off", "down", "away", "back", "over", "through", "around"}
ARTICLES = {"a", "an", "the", "my", "your", "his", "her", "its", "our", "their"}
PHRASE_END = {"is", "was", "are", "were", "be", "been", "of", "in", "on", "at", "with", "to",
              "and", "or", "but", "for", "from", "by", "that", "which", "who", "has", "had",
              "have", "will", "can", "could", "would", "should", "must", "may", "might", "did",
              "does", "do", "into", "onto", "under", "over", "behind", "near", "as", "so",
              "than", "then", "there", "here", "too", "again", "now", "yet", "still", "s"}


def _bare_ipa(ipa: str | None) -> str:
    """IPA without stress, length, brackets or syllable marks, to compare."""
    return re.sub(r"[ˈˌ./\[\]ːˑ̯()]", "", ipa or "")


def _rare_sense(sense: dict) -> bool:
    return any(str(l).lower() in RARE_SENSE_LABELS or str(l).startswith("etymology-")
               for l in (sense.get("labels") or []))


def base_is_word(form: str, lemma: str) -> bool:
    """The form minus -s/-es is a real word other than the lemma."""
    return any(b and b != lemma and _zipf(b, "en") >= 4.0
               for b in (form[:-1], form[:-2] if form.endswith("es") else ""))


def _verb_only_forms(ctx: Context) -> frozenset[str]:
    """Forms that can only be the verb (mugged, wound), not the noun or
    adjective spelt the same (mugs, winds)."""
    verb, other = set(), {ctx.lemma.lower()}
    for k in catalog.FORM_FIELDS:
        for i in ctx.items(k):
            form = (i.get("form") or "").lower()
            if form:
                (verb if k.startswith("verb_") and k != "verb_base" else other).add(form)
    return frozenset(verb - other)


def _usage_pos(text: str, forms, verb_only, lemma: str | None = None) -> str | None:
    """Which part of speech the headword is in this sentence, when its form
    or a determiner before it says so: "verb" (Tom was mugged), "noun" (the
    mug), "other" (the wound — wind's past form used as a noun is another
    word), or None (unclear)."""
    if lemma and " " in lemma:
        # A phrase entry (butter knife): the phrase itself must be there.
        low_text = " ".join(tokens(text))
        return None if any(" " in f and f in low_text for f in forms) else "other"
    raw = tokens(text)
    toks = [t[:-2] if t.endswith("'s") else t.rstrip("'") for t in raw]
    words = list(re.finditer(r"[A-Za-zÀ-ÿœæ']+", text or ""))
    cased = [m.group(0) for m in words]
    # A capital that does not start a sentence marks a name.
    starts = [not (text or "")[:m.start()].rstrip(" \"'“‘(").strip()
              or (text or "")[:m.start()].rstrip(" \"'“‘(").endswith((".", "!", "?", ":"))
              for m in words]
    low = (text or "").lower()
    if not any(t in forms for t in toks):
        return "other"  # 「this is a pen」: not this word at all
    for i, t in enumerate(toks):
        if t not in forms:
            continue
        if i < len(cased) and not starts[i] and cased[i][:1].isupper() and not any(
                f[:1].isupper() for f in forms):
            return "other"  # 「the mighty Pan」: a name
        if (t == lemma or t in verb_only) and i + 1 < len(toks) and toks[i + 1] in PARTICLES and not (
                i > 0 and toks[i - 1] in DETERMINERS) and not any(" " in f for f in forms):
            return "other"  # 「pan out」: a phrasal verb is its own entry
        after_det = i > 0 and toks[i - 1] in DETERMINERS
        near_det = after_det or (i > 1 and toks[i - 2] in DETERMINERS)
        # leaves is leaf's plural and leave's -s form: without a determiner
        # (「the train leaves」) it is the other word (問題回報 #104).
        # 「the bus that leaves」: that/which here is a relative pronoun,
        # so only an article or possessive (or these/those) counts.
        plural_det = i > 0 and toks[i - 1] in ARTICLES | {"these", "those", "some", "many"}
        if lemma and t != lemma and t.endswith("s") and not plural_det and any(
                b and b not in forms for b in (t[:-1], t[:-2] if t.endswith("es") else "")
        ) and base_is_word(t, lemma):
            return "other"
        if t in verb_only:
            # 「the wound」: a noun spelt like the verb's form is another
            # word; so is long-winded. (Not 「this applies」: a pronoun.)
            if (i > 0 and toks[i - 1] in ARTICLES) or re.search(
                    r"\w-" + re.escape(t) + r"\b|\b" + re.escape(t) + r"-\w", low):
                return "other"
            return "verb"
        # A determiner just before, or before one modifier (a coffee mug),
        # and the noun phrase ends here — 「the crumbly soil」 is the adjective.
        ends = i == len(toks) - 1 or toks[i + 1] in PHRASE_END or raw[i].endswith("'s")
        return "noun" if near_det and ends else None
    return None


class LexiconLookup(SourceAdapter):
    """Meanings and parts of speech from entries already in this lexicon."""
    key = "lexicon"

    def normalize(self, f, raw, ctx):
        from .. import models as m
        if ctx.session is None:
            return []
        rel = ("derived_terms" if f in ("derived_native_meaning", "derived_pos")
               else catalog.RELATION_NATIVE.get(f))
        slots = {}
        if f == "morphemes_native":
            from .morph import part_slot
            rel = "morphemes"
            words = []
            for bd in ctx.items("morphemes")[:1]:
                for i, p in enumerate(bd.get("parts", [])):
                    if p.get("free"):
                        words.append({"word": p["part"]})
                        slots[p["part"].lower()] = part_slot(i, p)
        if not rel:
            return []
        C = []
        s = ctx.session
        for item in (words if f == "morphemes_native" else ctx.items(rel)):
            w = item.get("word", "")
            from ..text import normalize_lemma
            norm = normalize_lemma(w, ctx.target)
            q = select(m.Lexeme).where(m.Lexeme.language == ctx.target,
                                       m.Lexeme.normalized == norm, m.Lexeme.status == "full")
            lexemes = s.execute(q).scalars().all()
            if not lexemes:
                continue
            # The word's main usage first (問題回報 #16): the asked part of
            # speech, else the CEFR-J listed one (knife noun, not 削), else
            # the one with the most senses (wall noun, not its eye-dialect).
            senses = dict(s.execute(select(m.Sense.lexeme_id, func.count()).where(
                m.Sense.lexeme_id.in_([lx.id for lx in lexemes])).group_by(m.Sense.lexeme_id)).all())
            try:
                listed = {{"adj.": "adj", "adv.": "adv"}.get(p, p): lv for p, lv in
                          ((cefr_list().get(norm) or [None, {}])[1] or {}).items()}
            except Exception:  # noqa: BLE001 — no list: senses only
                listed = {}
            levels = ["A1", "A2", "B1", "B2", "C1", "C2"]
            # A source's part of speech for the relation word (Datamuse's
            # tags) only counts when it is one of the word's main usages:
            # salad's 「happy」 is 高興, not the rare noun 喜事.
            asked = item.get("pos") if not listed or item.get("pos") in listed else None
            lexemes.sort(key=lambda lx: (bool(asked) and lx.pos != asked,
                                         levels.index(listed[lx.pos]) if listed.get(lx.pos) in levels
                                         else 9, -senses.get(lx.id, 0)))
            if f == "derived_pos":
                C.append(Candidate(f, ctx.target, {"word": w, "pos": lexemes[0].pos},
                                   w.lower(), slot=w.lower(), source_record_id=str(lexemes[0].id)))
                continue
            for lx in lexemes:
                rows = s.execute(
                    select(m.SenseTranslation.text, m.Sense.id, m.Sense.labels,
                           m.SenseTranslation.is_ai)
                    .join(m.Sense, m.Sense.id == m.SenseTranslation.sense_id)
                    .where(m.Sense.lexeme_id == lx.id,
                           m.SenseTranslation.native_language == ctx.native)
                    .order_by(m.Sense.ordinal)).all()
                # Its first common sense (not obsolete, slang or another
                # etymology's), as the app's card front reads it.
                common = [r for r in rows if not any(
                    str(l).lower() in RARE_SENSE_LABELS or str(l).startswith("etymology-")
                    for l in (r.labels or []))]
                # A dictionary translation before an AI one (問題回報 #84:
                # surface 表面, not 「物件之外圍」).
                row = next((r for r in common if not r.is_ai),
                           common[0] if common else (rows[0] if rows else None))
                if row:
                    slot = slots.get(w.lower(), w.lower())
                    C.append(Candidate(f, ctx.native, {"word": w, "text": row.text,
                                                       "lexeme_id": lx.id, "sense_id": row.id,
                                                       "slot": slot, "part": w},
                                       slot, slot=slot, source_record_id=f"lexeme:{lx.id}"))
                    break
        return C


class SystemTTS(SourceAdapter):
    key = "system_tts"

    def normalize(self, f, raw, ctx):
        if f not in ("audio", "tts_fallback"):
            return []
        loc = TTS_LOCALE.get(ctx.target, ctx.target)
        return [Candidate(f, ctx.target, {"tts": True, "locale": loc, "text": ctx.display
                                          or ctx.lemma}, f"tts:{loc}", confidence=0.3)]


class NotImplementedSource(SourceAdapter):
    def __init__(self, key: str):
        self.key = key

    def lookup(self, field_key, ctx):
        from .http import SourceError
        raise SourceError("unavailable", f"{self.meta.name} 的 adapter 尚未實作", retryable=False)


_ = fold  # re-exported helpers used by tests
