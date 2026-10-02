"""構詞拆解: split an English word into prefixes, a root and suffixes,
in order, with meanings — e.g. exterior → ex- · -ter · -ior,
unhappiness → un- · happy · -ness, conservation → con- · serv · -ation.

The analyzer tries every prefix chain × suffix chain from morph_data,
lets the middle be a bound Latin/Greek root, an English word (with the
spelling changes of suffixing: happi→happy, mak→make, runn→run) or a
compound of two words, and scores each split by how much of the word it
explains. Etymology keeps it honest: Germanic words aren't cut into Latin
roots, and when Wiktionary has an etymology without any affix markup,
English derivations it would have marked (butt + -er for "butter") are
not invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from . import morph_data as md

# Assimilated prefix spellings: the next letter must fit.
NEXT = {"ac": "cq", "af": "f", "ag": "g", "al": "l", "an": "n", "ap": "p", "ar": "r", "as": "s",
        "at": "t", "col": "l", "com": "bmp", "cor": "r", "ef": "f", "dif": "f", "il": "l",
        "im": "bmp", "ir": "r", "oc": "c", "of": "f", "op": "p", "suc": "c", "suf": "f",
        "sug": "g", "sum": "m", "sup": "p", "sur": "r", "sus": "cpt", "syl": "l", "sym": "bmp",
        "sys": "t", "e": "bdglmnrv", "di": "bdglmnrv", "a": "bcdfgklmnpstvw"}
VOWELS = set("aeiouy")
# in- means "in, into" (not "not") before these English words: in-come, in-put.
IN_DIRECTIONAL = {"put", "come", "land", "sight", "side", "born", "door", "doors", "let", "take",
                  "stall", "vest", "deed", "flow", "breed", "grown", "lay", "roads", "sure"}
# Frequent tokens that aren't English roots (wordfreq counts them in English text).
NOT_ROOTS = {"der", "die", "das", "del", "des", "les", "los", "las", "usa", "uk", "eu", "ing",
             "tion", "ment", "ness", "est", "ter", "nes", "ally"}
# Latin suffixes that attach to Latin stems, not to English words (exam-ine).
BOUND_ONLY_SUFFIXES = {"ine", "ile", "ior", "ter", "ose", "ule", "cule", "tude", "ac", "ia"}
STAY_WHOLE = 4.8  # words at least this common aren't split further (happy, national, nature)
# Endings of adjectives, and of nouns made from adjectives: in-/un- before
# them mean "not" (im-possible, in-dependence, in-vis-ible).
ADJ_ENDINGS = ("ible", "able", "ent", "ant", "al", "ive", "ous", "ic", "ite", "ful", "less", "ar",
               "ary", "ile", "ine", "ence", "ance", "ency", "ancy", "ity", "ness", "ed")


@lru_cache(maxsize=50000)
def zipf(word: str) -> float:
    try:
        from wordfreq import zipf_frequency
        return zipf_frequency(word, "en")
    except ImportError:
        return 0.0


@lru_cache(maxsize=1)
def _pos_table() -> dict:
    try:
        from .adapters.local import cefr_list
        return cefr_list()
    except Exception:  # noqa: BLE001
        return {}


def word_pos(word: str) -> set[str]:
    """Parts of speech from the CEFR list, as noun / verb / adjective / adverb."""
    hit = _pos_table().get(word)
    names = {"adj": "adjective", "adv": "adverb", "n": "noun", "v": "verb"}
    return {names.get(p.rstrip(".").lower(), p.rstrip(".").lower()) for p in hit[1]} if hit \
        else set()


@dataclass
class Part:
    text: str  # the letters in the word ("happi")
    kind: str  # prefix / root / suffix
    shown: str  # how it is shown ("happy", "un-", "-ness")
    en: str | None = None
    zh: str | None = None
    origin: str | None = None
    free: bool = False  # an English word of its own

    def as_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind, "part": self.shown, "meaning": self.en,
                "meaning_zh": self.zh, "origin": self.origin, "free": self.free}


INFLECTIONS = {"ed", "d", "ing", "s", "es", "er", "est"}
CLASSICAL = {"la", "LL.", "ML.", "NL.", "VL.", "grc", "la-lat", "la-med", "la-new"}


@dataclass
class Evidence:
    origin: str | None = None  # language code of the etymon (la, ang, …)
    etym_without_affix: bool = False  # Wiktionary has an etymology but no affix markup

    @property
    def group(self) -> str | None:
        if self.origin in md.GERMANIC:
            return "germanic"
        if self.origin in md.LATINATE:
            return "latinate"
        return None


@dataclass
class Analysis:
    word: str
    parts: list[Part]
    score: float
    method: str  # mono / derived / bound / compound
    alternatives: list[list[Part]] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return " + ".join(p.shown for p in self.parts)

    @property
    def unknown(self) -> bool:
        return any(p.kind == "root" and not p.free and p.en is None for p in self.parts)


def _prefix_chains(w: str, max_n: int = 2):
    out = [([], 0)]
    frontier = [([], 0)]
    for _ in range(max_n):
        nxt = []
        for chain, i in frontier:
            for spelling, entries in md.PREFIX.items():
                if not w.startswith(spelling, i):
                    continue
                j = i + len(spelling)
                if len(w) - j < 2:
                    continue
                rule = NEXT.get(spelling)
                if rule and w[j] not in rule:
                    continue
                for e in entries:
                    nxt.append((chain + [(spelling, e)], j))
        out += nxt
        frontier = nxt
    return out


def _suffix_chains(w: str, start: int, max_n: int = 3):
    out = [([], len(w))]
    frontier = [([], len(w))]
    for _ in range(max_n):
        nxt = []
        for chain, j in frontier:
            for spelling, entries in md.SUFFIX.items():
                i = j - len(spelling)
                if i - start < 1 or not w.endswith(spelling, 0, j):
                    continue
                for e in entries[:1]:
                    nxt.append(([(spelling, e)] + chain, i))
        out += nxt
        frontier = nxt
    return out


def _free_forms(stem: str, suffixed: bool, next_suffix: str | None):
    """English words the stem can stand for: the stem itself, or with the
    spelling change suffixing made (drop e, y→i, doubled consonant)."""
    forms = [stem]
    if suffixed and next_suffix and next_suffix[0] in VOWELS:
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in VOWELS:
            forms.insert(0, stem[:-1])  # the single consonant first (run-n-ing)
        forms.append(stem + "e")
    if suffixed and stem.endswith("i"):
        forms.append(stem[:-1] + "y")
    return forms


def _prefix_meaning(entry: md.Morph, rest: str, root: Part) -> bool:
    """Which meaning of in-/un-/a- fits: 'not' before an adjective (or a
    noun made from one), 'in, into' / 'reverse' otherwise. [rest] is what
    follows the prefix in the word."""
    if not entry.tag:
        return True
    pos = word_pos(rest)
    adjective = "adjective" in pos or rest.endswith(ADJ_ENDINGS)
    if entry.form == "un":
        reverse = not adjective and "verb" in pos  # un-do, un-lock
        return (entry.tag == "dir") == reverse
    if entry.form in ("a", "an", "non"):
        return entry.tag == "neg"
    if root.free and root.shown in IN_DIRECTIONAL:
        return entry.tag == "dir"
    return (entry.tag == "neg") == adjective


def _roots(stem: str, suffixes, prefixes, ev: Evidence):
    """(Part list for the middle, bonus, method) options."""
    out = []
    latin_ok = ev.group != "germanic"
    next_suffix = suffixes[0][0] if suffixes else None
    # a bound Latin / Greek root
    if latin_ok and stem in md.ROOT and len(stem) >= 3:
        e = md.ROOT[stem][0]
        bonus = 0.32 if len(stem) >= 3 else 0.2
        out.append(([Part(stem, "root", stem, e.en, e.zh, e.origin)], bonus, "bound"))
    # a preposition as the base of a Latin comparative (ex·ter·ior)
    if latin_ok and suffixes and not prefixes and stem in md.BASE_PREFIXES:
        e = md.PREFIX[stem][0]
        out.append(([Part(stem, "root", stem, e.en, e.zh, e.origin)], 0.2, "bound"))
    # an English word
    for form in _free_forms(stem, bool(suffixes), next_suffix):
        z = zipf(form)
        if len(form) >= 3 and z >= 3.0 and form not in NOT_ROOTS \
                and (len(form) > 3 or form in _pos_table()) \
                and not (suffixes and suffixes[0][0] in BOUND_ONLY_SUFFIXES):
            bonus = 0.3 if z >= 4 else 0.15 if z >= 3 else 0.05
            out.append(([Part(stem, "root", form, None, None, None, True)], bonus, "derived"))
            break
    # two bound roots, Greek style (photo·graph, bio·logy is a suffix) —
    # only for a word known to come from Latin or Greek (not arti·san)
    if ev.origin in CLASSICAL and len(stem) >= 6:
        for k in range(3, len(stem) - 2):
            a, b = stem[:k], stem[k:]
            link = ""
            if a.endswith(("o", "i")) and a[:-1] in md.ROOT:
                a, link = a[:-1], a[-1]
            if a in md.ROOT and b in md.ROOT and len(a) >= 3 and len(b) >= 3:
                ea, eb = md.ROOT[a][0], md.ROOT[b][0]
                out.append(([Part(a + link, "root", a + link, ea.en, ea.zh, ea.origin),
                             Part(b, "root", b, eb.en, eb.zh, eb.origin)], 0.25, "bound"))
    # a compound of two English words (break·fast, under·stand)
    if not prefixes and not suffixes and not ev.etym_without_affix:
        for k in range(4, len(stem) - 3):
            a, b = stem[:k], stem[k:]
            if a in md.PREFIX:  # micro-scope, under-stand: a prefix, not a compound
                continue
            if zipf(a) >= 3.0 and zipf(b) >= 3.0 and a not in NOT_ROOTS and b not in NOT_ROOTS:
                out.append(([Part(a, "root", a, None, None, None, True),
                             Part(b, "root", b, None, None, None, True)], 0.25, "compound"))
    return out


def analyze(word: str, ev: Evidence | None = None) -> Analysis:
    ev = ev or Evidence()
    w = word.strip().lower()
    if " " in w or "-" in w:  # an open or hyphenated compound: its words
        parts = [Part(x, "root", x, None, None, None, True)
                 for x in w.replace("-", " ").split()]
        return Analysis(word, parts, 1.0, "compound")
    # The more common the word, the stronger the case for leaving it whole.
    z = zipf(w)
    mono = Analysis(word, [Part(w, "root", w, None, None, None, z >= 2.5)],
                    min(1.05, 0.95 + 0.03 * (z - 3)) if z >= 3 else 0.85 if z >= 2 else 0.6,
                    "mono")
    if not w.isalpha() or len(w) < 4:
        return mono
    options: list[tuple[float, list[Part], str]] = []
    for prefixes, i in _prefix_chains(w):
        for suffixes, j in _suffix_chains(w, i):
            stem = w[i:j]
            if not stem:
                continue
            if any(s == "ter" for s, _ in suffixes) and not (
                    not prefixes and stem in md.BASE_PREFIXES):
                continue  # -ter- only after a Latin preposition (ex-ter, pos-ter)
            for middle, bonus, method in _roots(stem, suffixes, prefixes, ev):
                if method == "derived" and (prefixes or suffixes) and ev.etym_without_affix:
                    continue  # Wiktionary would have marked an English derivation
                if method in ("bound",) and ev.group == "germanic":
                    continue
                head = "".join(sp for sp, _ in prefixes) + "".join(p.text for p in middle)
                if prefixes and suffixes and len(middle) == 1                         and len(middle[0].text) <= 3 and max(zipf(head), zipf(head + "e")) >= 3.0:
                    continue  # de·cor·ative: a short root, but decor(ate) is a word
                if method == "bound" and suffixes and not prefixes and all(
                        s in INFLECTIONS for s, _ in suffixes):
                    continue  # grat·ed: an English ending goes on an English word (grate)
                pre = []
                ok = True
                at = 0
                for spelling, e in prefixes:
                    at += len(spelling)
                    if not _prefix_meaning(e, w[at:], middle[0]):
                        ok = False
                        break
                    pre.append(Part(spelling, "prefix", spelling + "-", e.en, e.zh, e.origin))
                if not ok:
                    continue
                if any(s == "ee" for s, _ in suffixes) and not middle[-1].free:
                    continue  # -ee (one who receives) goes on English verbs: employ-ee
                suf = [Part(s, "suffix", "-" + s, e.en, e.zh, e.origin) for s, e in suffixes]
                parts = pre + middle + suf
                if len(parts) < 2:
                    continue
                known = sum(len(p.text) for p in parts)
                score = known / len(w) + bonus - 0.08 * (len(parts) - 1)
                score += 0.01 * sum(len(p.text) for p in middle)  # prefer spect-ion
                score -= 0.15 * sum(1 for p in pre + suf if len(p.text) == 1)
                score -= 0.1 * max(0, len(pre) - 1)  # a second prefix needs strong support
                # -scope, -phone as suffixes only if no prefix reading (micro- + scope)
                score -= 0.02 * sum(1 for p in suf if len(p.text) >= 5 and zipf(p.text) >= 3)
                options.append((score, parts, method))
    if not options:
        return mono
    options.sort(key=lambda o: -o[0])
    best_score, best_parts, method = options[0]
    if best_score <= mono.score:
        mono.alternatives = [o[1] for o in options[:2]]
        return mono
    return Analysis(word, expand(best_parts, ev), best_score, method,
                    [o[1] for o in options[1:3]])


def expand(parts: list[Part], ev: Evidence, depth: int = 0) -> list[Part]:
    """Split English-word parts further when that says more: a less common
    word (unhappy: un- + happy) or one with a prefix (transport: trans- +
    port). Very common words stay whole (nation, happy)."""
    if depth >= 3:
        return parts
    out: list[Part] = []
    for p in parts:
        if p.kind == "root" and p.free and len(p.shown) >= 5 and zipf(p.shown) < STAY_WHOLE \
                and p.shown not in md.PREFIX:
            sub = analyze(p.shown, Evidence(ev.origin))
            sound = all(q.kind != "root" or (zipf(q.shown) >= 3.8 if q.free else len(p.shown) >= 6)
                        for q in sub.parts)
            if sub.method != "mono" and not sub.unknown and sound:
                inner = list(sub.parts)
                # keep this word's letters (happi-ness, not happy-ness)
                if p.text != p.shown:
                    head = "".join(q.text for q in inner[:-1])
                    last = inner[-1]
                    inner[-1] = Part(p.text[len(head):] or last.text, last.kind, last.shown,
                                     last.en, last.zh, last.origin, last.free)
                out += inner
                continue
        out.append(p)
    return out


def normalize_affix_args(args: dict, name: str) -> tuple[dict, str]:
    """{{surf|+suf|en|nature|al}}: the surface analysis says which template
    it follows first, so every argument sits one place later."""
    first = str(args.get("1", ""))
    if name == "surf" and first.startswith("+"):
        shifted = {str(int(k) - 1): v for k, v in args.items() if k.isdigit() and int(k) >= 2}
        return shifted, {"suf": "suffix", "suffix": "suffix", "pre": "prefix", "prefix": "prefix",
                         "com": "compound", "compound": "compound"}.get(first[1:], "af")
    return args, name


def parts_from_affix_template(args: dict, name: str) -> list[str] | None:
    """Parts, in order, from a Wiktionary affix template's arguments."""
    import re
    args, name = normalize_affix_args(args, name)
    vals = [re.sub(r"<[^>]*>", "", v).strip() for k, v in sorted(
        ((k, v) for k, v in args.items() if k.isdigit() and int(k) >= 2),
        key=lambda kv: int(kv[0])) if v]
    if name == "ety":
        if not vals or not vals[0].startswith(":"):
            return None
        kind, vals = vals[0][1:], vals[1:]
        name = {"af": "af", "affix": "af", "pre": "prefix", "prefix": "prefix", "suf": "suffix",
                "suffix": "suffix", "com": "compound", "compound": "compound",
                "surf": "surf"}.get(kind)
        if name is None:
            return None
    if not vals:
        return None
    if name in ("prefix", "pre") and len(vals) >= 2:
        return [vals[0].rstrip("-") + "-"] + vals[1:]
    if name in ("suffix", "suf") and len(vals) >= 2:
        return [vals[0]] + ["-" + v.lstrip("-") for v in vals[1:]]
    return vals


def template_gloss(value: str) -> str | None:
    import re
    m = re.search(r"<t:([^>]*)>", value or "")
    return m.group(1) if m else None


def reconstructs(word: str, parts: list[str]) -> bool:
    """Do these parts spell the word, allowing the usual spelling changes
    at each join (happy+ness → happiness, make+ing → making, run+ing →
    running)? Tries every variant (backtracking)."""
    w = word.lower().replace(" ", "").replace("-", "")
    clean = [p.lower().strip().strip("-").replace(" ", "") for p in parts]
    if not all(clean):
        return False

    def fits(n: int, pos: int) -> bool:
        if n == len(clean):
            return pos == len(w)
        p = clean[n]
        variants = {p}
        if n < len(clean) - 1:
            if p.endswith("e"):
                variants.add(p[:-1])
            if p.endswith("y"):
                variants.add(p[:-1] + "i")
            variants.add(p + p[-1])
        return any(w.startswith(v, pos) and fits(n + 1, pos + len(v)) for v in variants)

    return fits(0, 0)
