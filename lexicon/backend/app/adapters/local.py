"""Sources computed on this machine: word lists, frequency, CEFR, rules,
the lexicon's own entries, and the device TTS marker."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select

from .. import catalog, config
from ..text import example_key, fold, tokens
from .base import Candidate, Context, SourceAdapter, form_bases

CEFR_FILE = config.REPO / "app" / "assets" / "cefr_en.json"
OXFORD_EXTRA = Path(__file__).resolve().parents[1] / "oxford5000_extra.json"
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
WF_LANG = {"en": "en", "fr": "fr", "zh-TW": "zh"}
# British English is the default playback (spec section 7).
TTS_LOCALE = {"en": "en-GB", "fr": "fr-FR", "zh-TW": "zh-TW"}


@lru_cache(maxsize=1)
def cefr_list() -> dict:
    """CEFR-J/Octanove, plus the Oxford 5000 additions (B2-C1) it does not
    list, so e.g. adjacent is C1 instead of a B1 frequency guess (#220)."""
    words = json.loads(CEFR_FILE.read_text(encoding="utf-8"))["words"]
    if OXFORD_EXTRA.exists():
        for w, pos in json.loads(OXFORD_EXTRA.read_text(encoding="utf-8"))["words"].items():
            words.setdefault(w, [round(_zipf(w, "en"), 2), pos, ""])
    return words


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
    """One-edit neighbours from the complete local Kaikki index when present.
    Without it, use wordfreq/CEFR-J and identify the fallback explicitly."""
    key = "kaikki_wordlist"

    def download_snapshot(self, language, snapshot_dir):
        from ..kaikki_index import wordlist_snapshot
        indexed = wordlist_snapshot(language)
        if indexed is not None:
            return indexed
        return {"version": "wordfreq top-60k + CEFR-J", "row_count": len(_wordlist(language)),
                "details": {"note": "Kaikki 全量字表需下載 2–3 GB 資料包；目前以常用字表代替。"}}

    def normalize(self, f, raw, ctx):
        if f != "similar_spelling" or " " in ctx.lemma:
            return []
        w = ctx.lemma
        skip = {w + "s", w + "es", w + "ed", w + "d", w + "ing", w + "'s"}
        hits = []
        from ..kaikki_index import spelling_candidates
        indexed = spelling_candidates(ctx.target, w)
        origin = 'kaikki_index' if indexed is not None else 'wordfreq_cefr_fallback'
        for x in indexed if indexed is not None else _wordlist(ctx.target):
            if abs(len(x) - len(w)) > 1 or x in skip:
                continue
            diff = _edit1(w, x)
            if diff:
                hits.append((x, diff))
        hits.sort(key=lambda h: -_zipf(h[0], ctx.target))
        from .base import by_frequency
        return by_frequency([
            Candidate(f, ctx.target, {"word": x, "difference": diff, "note": "拼字相近",
                                      "wordlist": origin}, x,
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
    "sleep": {"slept"}, "meet": {"met"}, "blow": {"blew", "blown"},
    "good": {"better", "best"},
    "bad": {"worse", "worst"},
}

ENGLISH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "can", "could", "did", "do", "does", "for", "from", "had", "has", "have",
    "he", "her", "hers", "him", "his", "i", "if", "in", "into", "is", "it",
    "its", "me", "mine", "my", "of", "on", "or", "our", "ours", "she", "that",
    "the", "their", "theirs", "them", "they", "this", "those", "to", "was", "we",
    "were", "what", "when", "where", "which", "who", "will", "with", "would",
    "through",
    "you", "your", "yours",
}

# Incidental counts are not evidence of a shared sense: a book leaf has
# "two pages", but leaves turning red in "two weeks" are still plant leaves.
SENSE_COUNT_WORDS = set('zero one two three four five six seven eight nine ten '
                      'eleven twelve thirteen fourteen fifteen sixteen seventeen '
                      'eighteen nineteen twenty thirty forty fifty sixty seventy '
                      'eighty ninety hundred thousand million billion'.split())


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
    if lemma.endswith("ie"):
        stems.add(lemma[:-2] + "y")  # lie → lying, die → dying, tie → tying
    if lemma.endswith("f"):
        stems.add(lemma[:-1] + "v")
    if lemma.endswith("fe"):
        stems.add(lemma[:-2] + "v")
    return any(form.startswith(stem)
               and form[len(stem):] in {"s", "es", "d", "ed", "ing", "er", "est"}
               for stem in stems)


_VOICELESS, _SIBILANT = set("ptkfθsʃ"), set("szʃʒ")  # tʃ, dʒ end in ʃ, ʒ


def _inflection_suffix(base: str, form: str) -> str | None:
    """"d" (past), "s" (plural, third person) or "ing" when [form] is
    [base]'s regular inflection by spelling (not leaf → leaves: /f/ → /v/)."""
    if form == base or form in IRREGULAR_FORMS.get(base, set()) \
            or not plausible_form(base, form) \
            or (base.endswith(("f", "fe")) and not form.startswith(base)):
        return None
    return next((s for s in ("ing", "d", "s") if form.endswith(s)), None)


def _with_suffix(ipa: str, suffix: str) -> str:
    """/ˈdɹɪzəl/ + d → /ˈdɹɪzəld/, /spɒt/ + d → /spɒtɪd/, /bʌs/ + s → /bʌsɪz/."""
    body = ipa.strip("/")
    last = re.sub(r"[ˈˌːˑ.()̀-ͯ]", "", body)[-1:]
    if suffix == "ing":
        end = "ɪŋ"
    elif suffix == "d":
        end = "ɪd" if last in "td" else "t" if last in _VOICELESS else "d"
    else:
        end = "ɪz" if last in _SIBILANT else "s" if last in _VOICELESS else "z"
    if end[0] == "ɪ" and not re.search("[ˈˌ]", body):
        body = "ˈ" + body  # one syllable more: spot → /ˈspɒtɪd/
    return f"/{body}{end}/"


def _phonemic_from_transcription(ipa: str) -> str | None:
    """Reduce common Wiktionary allophones to learner-friendly /.../ IPA.

    This is only used when a regular inflection has no phonemic entry.  It
    lets dapple [ˈdæpəɫ] supply dappled /ˈdæpəld/ without making the narrow
    transcription the learner's default.
    """
    if re.fullmatch(r"/[^/ ,]+/", ipa):
        return ipa
    if not re.fullmatch(r"\[[^\] ,]+\]", ipa):
        return None
    body = ipa[1:-1].replace("ɫ", "l").replace("ɾ", "t").replace("ɪ̈", "ɪ")
    return f"/{body}/"


def inflected_ipa(word: str) -> list[dict]:
    """IPA for a regular inflection the dictionary gives no sound for, from
    its base word's (drizzled ← drizzle /ˈdɹɪzəl/: /ˈdɹɪzəld/, 問題回報 #24)."""
    from .. import kaikki_index
    from .kaikki import _accents
    w = word.lower()
    bases = dict.fromkeys(str(f.get("word") or "").lower()
                          for e in kaikki_index.lookup("en", w) or []
                          for s in e.get("senses") or [] for f in s.get("form_of") or [])
    for base in bases:
        suffix = _inflection_suffix(base, w)
        if not suffix:
            continue
        out = []
        sounds = []
        for e in kaikki_index.lookup("en", base) or []:
            ety = str(e.get("etymology_number") or "")
            if str(e.get("word", "")).lower() != base or (ety.isdigit() and int(ety) > 1):
                continue  # wind (纏繞) is not wind (風)
            sounds.extend(e.get("sounds") or [])
        # A broad source is preferable whenever one exists. Narrow sounds are
        # a last resort for a base such as dapple, never extra learner IPAs.
        phonemic = [snd for snd in sounds if str(snd.get("ipa") or "").startswith("/")]
        for snd in phonemic or sounds:
            ipa = _phonemic_from_transcription(snd.get("ipa") or "")
            if ipa:
                v = {"ipa": _with_suffix(ipa, suffix), "accent": _accents(snd.get("tags")),
                     "composed": True, "base": base}
                if v["ipa"] not in {o["ipa"] for o in out}:
                    out.append(v)
        if out:
            return out[:3]
    return []


def _alt_of_bases(word: str) -> list[str]:
    """Bases named by every sense as an alternative spelling.

    A form_of link is not enough: upperclassmen is the plural of
    upperclassman and is not said the same way. A sense with its own
    meaning blocks the copy, so a homograph cannot borrow another word.
    """
    from .. import kaikki_index
    entries = kaikki_index.lookup("en", word.lower()) or []
    if not entries:
        return []
    bases: list[str] = []
    for entry in entries:
        senses = entry.get("senses") or []
        if not senses:
            return []
        for sense in senses:
            linked = [str(item.get("word") or "").strip()
                      for item in (sense.get("alt_of") or []) if item.get("word")]
            if not linked:
                return []
            for base in linked:
                if base.lower() != word.lower() and base not in bases:
                    bases.append(base)
    return bases


def _base_phonemic(base: str) -> list[dict]:
    """Phonemic /…/ IPA of [base], skipping a later etymology (wind 纏繞)."""
    from .. import kaikki_index
    from .kaikki import _accents
    sounds = []
    for entry in kaikki_index.lookup("en", base) or []:
        ety = str(entry.get("etymology_number") or "")
        if str(entry.get("word", "")).lower() != base.lower() or (ety.isdigit() and int(ety) > 1):
            continue
        sounds.extend(entry.get("sounds") or [])
    out = []
    for sound in sounds:
        ipa = str(sound.get("ipa") or "")
        accents = _accents(sound.get("tags"))
        # Regional variants (Canada, Australia) must not become the default
        # ahead of the citation form.
        if any(accent not in ("US", "UK") for accent in accents):
            continue
        if not ipa.startswith("/") or not re.fullmatch(r"/[^/]+/", ipa):
            continue
        row = {"ipa": ipa, "accent": accents, "composed": True, "base": base}
        if ipa not in {item["ipa"] for item in out}:
            out.append(row)
    return out[:3]


def _closed_spelling(phrase: str) -> str:
    return re.sub(r"[\s-]+", "", phrase).lower()


def _closed_compound_bases(word: str) -> list[str]:
    """The phrase a closed spelling names (backburner ← back burner).

    One sense may define the compound in its own words. That does not make
    it a different word, as long as every alt_of is that same phrase.
    """
    from .. import kaikki_index
    entries = kaikki_index.lookup("en", word.lower()) or []
    found: list[str] = []
    for entry in entries:
        for sense in entry.get("senses") or []:
            for item in sense.get("alt_of") or []:
                base = str(item.get("word") or "").strip()
                if " " not in base and "-" not in base:
                    continue
                if _closed_spelling(base) != word.lower() or base in found:
                    continue
                found.append(base)
    return found


@lru_cache(maxsize=1)
def _cmudict_source():
    """One loaded CMUdict for every rule here (a fresh one re-read the whole
    file on each call, which made a library audit crawl)."""
    from .cmudict import CMUdict
    source = CMUdict()
    source._load()
    return source


def _cmudict_ipa(phrase: str) -> str | None:
    """US IPA for a word or a phrase CMUdict only lists in parts."""
    from ..arpabet import arpabet_to_ipa
    source = _cmudict_source()
    text = phrase.strip()
    parts = text.split()
    if len(parts) == 1 and "-" in text:
        parts = text.split("-")
    prons = [source._pron.get(part.lower()) for part in parts]
    if not parts or not all(prons):
        return None
    ipas = [arpabet_to_ipa(pron[0]) for pron in prons]
    if not all(ipas):
        return None
    if len(ipas) == 1:
        return ipas[0]
    return "/" + " ".join(ipa.strip("/") for ipa in ipas) + "/"


def linked_base_ipa(word: str) -> list[dict]:
    """IPA for a spelling variant whose entry only points at a base we can
    already pronounce (panick → panic, chainmail → chain mail, 問題回報 #209).

    The base has to be the one Wiktionary names. A closed compound is never
    split by guesswork.
    """
    for base in _alt_of_bases(word) or _closed_compound_bases(word):
        copied = _base_phonemic(base)
        if copied:
            return copied
        ipa = _cmudict_ipa(base)
        if ipa:
            return [{"ipa": ipa, "accent": "US", "composed": True, "base": base,
                     "from_phonemes": True}]
    return []


def derived_adjective_ipa(word: str) -> list[dict]:
    """Derive an *-ly* adjective after silent ``mb`` (crumb → crumbly).

    The base's final ``b`` becomes audible before the suffix.  This covers a
    productive spelling pattern when the derived entry has audio but no IPA.
    """
    from .. import kaikki_index
    from .kaikki import _accents
    w = word.lower()
    if not w.endswith("mbly"):
        return []
    base = w[:-2]
    out = []
    for e in kaikki_index.lookup("en", base) or []:
        for snd in e.get("sounds") or []:
            ipa = snd.get("ipa") or ""
            if not re.fullmatch(r"/[^/ ,]+/", ipa):
                continue
            body = ipa[1:-1]
            if not body.endswith("m"):
                continue
            value = f"/{body}bli/"
            row = {"ipa": value, "accent": _accents(snd.get("tags")),
                   "composed": True, "base": base}
            if value not in {item["ipa"] for item in out}:
                out.append(row)
    return out[:3]


# ── Word parts (問題回報 #291) ───────────────────────────────────────
# A rare derivative no dictionary pronounces (frother, attester, loungey)
# is its base word's IPA plus the sound of a suffix that keeps the base's
# stress. Suffixes that move the stress (-ation, -ity, -ic) are left out on
# purpose: a wrong stress is worse than no IPA. (UK, US) pairs where the
# accents differ; one string where they agree.
_AFFIX_SUFFIX = {
    "er": ("ə", "ɚ"), "or": ("ə", "ɚ"), "ers": ("əz", "ɚz"), "ory": ("əɹi", "ɚi"),
    "y": "i", "ey": "i", "ie": "i", "ies": "iz",
    "ness": "nəs", "less": "ləs", "ly": "li", "ish": "ɪʃ", "ful": "fəl",
    "ment": "mənt", "ize": "aɪz", "ise": "aɪz", "ist": "ɪst", "ism": "ɪzəm",
    "able": "əbəl", "hood": "hʊd", "ship": "ʃɪp", "dom": "dəm", "like": "laɪk",
    "en": "ən", "ery": ("əɹi", "ɚi"), "ward": ("wəd", "wɚd"), "wards": ("wədz", "wɚdz"),
    "some": "səm", "fold": "fəʊld", "ling": "lɪŋ", "let": "lət", "ette": "ɛt",
    # Combining forms Wiktionary files as suffixes (問題回報 #209: repair + -person).
    "person": ("pɜːsən", "pɜɹsən"), "proof": "pɹuːf",
}
_AFFIX_PREFIX = {
    "un": "ʌn", "non": ("nɒn", "nɑn"), "re": "ɹiː", "pre": "pɹiː", "de": "diː",
    "mis": "mɪs", "dis": "dɪs", "out": "aʊt", "over": ("əʊvə", "oʊvɚ"),
    "under": ("ʌndə", "ʌndɚ"), "anti": "ænti", "sub": "sʌb", "co": ("kəʊ", "koʊ"),
    "super": ("suːpə", "suːpɚ"), "inter": ("ɪntə", "ɪntɚ"), "multi": "mʌlti",
    "semi": "sɛmi", "micro": ("maɪkɹəʊ", "maɪkɹoʊ"), "mini": "mɪni", "ex": "ɛks",
    "counter": ("kaʊntə", "kaʊntɚ"), "self": "sɛlf", "step": "stɛp",
}
_AFFIX_TEMPLATES = {"suffix", "prefix", "affix", "af", "compound", "com", "ety"}
_IPA_VOWELS = set("aeiouæɑɒɔəɚɛɜɪʊʌ")


def _affix_sound(table: dict, part: str, accent: str) -> str | None:
    snd = table.get(part)
    if isinstance(snd, tuple):
        return snd[1] if accent == "US" else snd[0]
    return snd


def _template_parts(word: str) -> list[list[tuple[str, str]]]:
    """Word parts Wiktionary's etymology names, as (kind, spelling) lists:
    attester = suffix(attest, er), frother = ety(:af, froth, -er<id:agent noun>),
    stepdad = ety(:af, step-, dad). Only parts that spell the word qualify."""
    from .. import kaikki_index
    found: list[list[tuple[str, str]]] = []
    for entry in kaikki_index.lookup("en", word.lower()) or []:
        for t in entry.get("etymology_templates") or []:
            name, args = t.get("name"), t.get("args") or {}
            if name not in _AFFIX_TEMPLATES or str(args.get("1", "en")) != "en":
                continue
            raw = [str(args.get(str(i)) or "") for i in range(2, 7)]
            if name == "ety":
                if not raw[0].startswith(":af"):
                    continue
                raw = raw[1:]
            parts: list[tuple[str, str]] = []
            for i, text in enumerate(raw):
                text = re.sub(r"<[^>]*>", "", text).strip().lower()
                if not text:
                    continue
                if not re.fullmatch(r"-?[a-z][a-z']*-?", text):
                    parts = []
                    break
                if name == "suffix" and i == 1 or text.startswith("-"):
                    parts.append(("suffix", text.strip("-")))
                elif name == "prefix" and i == 0 or text.endswith("-"):
                    parts.append(("prefix", text.strip("-")))
                else:
                    parts.append(("word", text))
            if len(parts) >= 2 and _spells(parts, word) and parts not in found:
                found.append(parts)
    return found


def _spelling_variants(parts: list[tuple[str, str]]) -> set[str]:
    """Spellings the parts can take side by side: lounge+y → loungey,
    thug+y → thuggy, happy+ness → happiness, plane+ar+ize: e dropped."""
    out = {""}
    for i, (kind, text) in enumerate(parts):
        nxt = parts[i + 1][1][:1] if i + 1 < len(parts) else ""
        forms = {text}
        if kind == "word" and nxt:
            if nxt in "aeiouy":
                if text.endswith("e"):
                    forms.add(text[:-1])
                if re.search(r"[aeiou][bdfglmnprstz]$", text):
                    forms.add(text + text[-1])
            if text.endswith("y") and nxt != "i":
                forms.add(text[:-1] + "i")
            if text.endswith("e") and nxt == "y":
                forms.add(text)
        out = {a + b for a in out for b in forms}
    return out


def _spells(parts: list[tuple[str, str]], word: str) -> bool:
    return re.sub(r"[\s-]+", "", word.lower()) in _spelling_variants(parts)


def _guess_parts(word: str) -> list[list[tuple[str, str]]]:
    """Parts by spelling alone when Wiktionary names none (loungey, thuggy):
    one known suffix or prefix, and a base that has to be a dictionary
    headword with phonemic IPA. Longer affixes first (-ness before -s)."""
    w = word.lower()
    out: list[list[tuple[str, str]]] = []
    for suffix in sorted(_AFFIX_SUFFIX, key=len, reverse=True):
        stem = w[: -len(suffix)] if w.endswith(suffix) else ""
        if len(stem) < 3:
            continue
        bases = [stem]
        if suffix[0] in "aeiouy":
            bases.append(stem + "e")
            if len(stem) > 3 and stem[-1] == stem[-2] and stem[-1] in "bdfglmnprstz":
                bases.append(stem[:-1])
        if stem.endswith("i"):
            bases.append(stem[:-1] + "y")
        for base in bases:
            if base != w and _base_phonemic(base) and [("word", base), ("suffix", suffix)] not in out:
                out.append([("word", base), ("suffix", suffix)])
        if out:
            return out
    for prefix in sorted(_AFFIX_PREFIX, key=len, reverse=True):
        base = w[len(prefix):].lstrip("-") if w.startswith(prefix) else ""
        if len(base) >= 3 and _base_phonemic(base):
            out.append([("prefix", prefix), ("word", base)])
            return out
    return out


def _part_body(kind: str, text: str, accent: str) -> tuple[str, bool, bool] | None:
    """IPA body (no slashes) of one part in one accent: (body, from CMUdict
    phonemes, specific to this accent). A prefix not in the table (step-) is
    a word."""
    if kind == "suffix":
        snd = _affix_sound(_AFFIX_SUFFIX, text, accent)
        return (snd, False, isinstance(_AFFIX_SUFFIX.get(text), tuple)) if snd else None
    if kind == "prefix":
        snd = _affix_sound(_AFFIX_PREFIX, text, accent)
        if snd:
            return (snd, False, isinstance(_AFFIX_PREFIX.get(text), tuple))
    for row in _base_phonemic(text):
        if not row["accent"] or accent in row["accent"]:
            return (row["ipa"].strip("/"), False, bool(row["accent"]))
    if accent == "US":
        ipa = _cmudict_ipa(text)
        if ipa:
            return (ipa.strip("/"), True, True)
    return None


# Prefixes that never take a noun's main stress (unbelief, nonbeliever).
_UNSTRESSED_PREFIXES = {"un", "non", "re", "pre", "de", "mis", "dis", "a", "be", "en", "em"}


def _join_parts(body: str, kind: str, part: str, spelling: str, prev_kind: str,
                noun: bool = False) -> str:
    """Attach one part's sound: froth+er → ˈfɹɒθə, water+y (UK) → ˈwɔːtəɹi
    (linking r), un+happy → ˌʌnˈhæpi, step+dad → ˈstɛpˌdæd. A noun's
    prefix takes the main stress (outgroup ˈaʊtˌɡɹuːp) unless it is one that
    never does; a verb's or adjective's base keeps it (outrun ˌaʊtˈɹʌn)."""
    stressed = "ˈ" in body
    if kind == "suffix":
        base = body if stressed else "ˈ" + body
        if part[:1] in _IPA_VOWELS:
            if base.endswith("ɚ"):
                base = base[:-1] + "əɹ"
            elif spelling.rstrip("e").endswith("r") and base[-1:] not in "ɹr":
                base += "ɹ"
            elif base.endswith("əl") and spelling.endswith("le"):
                base = base[:-2] + "l"  # crumble + y → ˈkɹʌmbli, settle + er → ˈsɛtlə
        if part[:1] == "l" and base.endswith("l"):
            part = part[1:]
        return base + part
    if prev_kind == "prefix":
        prefix = re.sub("[ˈˌ]", "", body)  # a word used as a prefix (auto-) drops its own
        base = part if "ˈ" in part else "ˈ" + part
        if noun and spelling in _AFFIX_PREFIX and spelling not in _UNSTRESSED_PREFIXES:
            return "ˈ" + prefix + base.replace("ˈ", "ˌ")
        return "ˌ" + prefix + base
    second = part.replace("ˈ", "ˌ")  # a compound: first part stressed
    return (body if stressed else "ˈ" + body) + ("" if "ˌ" in second else "ˌ") + second


def derived_affix_ipa(word: str) -> list[dict]:
    """IPA for a derivative or compound from its parts (問題回報 #291):
    Wiktionary's named parts first (attest + -er), a spelling guess only
    when it names none and ECDICT has no IPA either (loungey). Every base
    must already have phonemic IPA; the value is an estimate and says so."""
    w = word.lower()
    if " " in w or not re.fullmatch(r"[a-z][a-z'-]*", w):
        return []
    from .. import kaikki_index
    guessed = False
    options = _template_parts(w)
    if not options:
        from .ecdict import ECDict
        if ECDict().ipa(w):
            return []  # a dictionary's own IPA is next in line
        options, guessed = _guess_parts(w), True
    pos = {str(e.get("pos") or "") for e in kaikki_index.lookup("en", w) or []}
    noun = bool(pos) and pos <= {"noun", "name"}
    out: list[dict] = []
    for parts in options:
        for accent in ("UK", "US"):
            body, phonemes, specific, prev_kind, ok = "", False, False, "", True
            for i, (kind, text) in enumerate(parts):
                got = _part_body(kind, text, accent)
                if got is None:
                    ok = False
                    break
                snd, from_phonemes, this_accent = got
                phonemes, specific = phonemes or from_phonemes, specific or this_accent
                body = snd if i == 0 else _join_parts(body, kind, snd, parts[i - 1][1], prev_kind,
                                                      noun)
                prev_kind = kind
            if not ok:
                continue
            ipa = f"/{body}/"
            same = next((item for item in out if item["ipa"] == ipa), None)
            if same is not None:  # said the same way in both accents
                if same["accent"] and accent not in same["accent"]:
                    same["accent"].append(accent)
                continue
            row = {"ipa": ipa, "accent": [accent] if specific else [], "composed": True,
                   "estimate": True,
                   "base": " + ".join(("-" if k == "suffix" else "") + t + ("-" if k == "prefix" else "")
                                      for k, t in parts),
                   "derived": "spelling" if guessed else "wiktionary"}
            if phonemes:
                row["from_phonemes"] = True
            out.append(row)
        if out:
            break
    return out[:3]


# Keep respelled and optional sounds out of this conservative fallback.
_ODD_IPA = re.compile(r"[()]|[aɪ]j")


def _stress_suffix_bases(base: str, ending: str) -> list[dict]:
    """Use a dictionary's phonemic form, then CMUdict if none is usable.

    Syllable dots are IPA separators, not missing or invalid sounds. Removing
    them preserves the phonemes and stress. Require explicit stress for these
    polysyllabic bases; never guess it from an unmarked transcription.
    """
    out = []
    for row in _base_phonemic(base):
        body = row["ipa"].strip("/").replace(".", "")
        if (body.endswith(ending) and "ˈ" in body and not _ODD_IPA.search(body)
                and not re.search(r"[\s,]", body)):
            out.append({**row, "ipa": f"/{body}/"})
    if not out:
        ipa = _cmudict_ipa(base)
        if ipa and ipa.strip("/").endswith(ending) and "ˈ" in ipa:
            out.append({"ipa": ipa, "accent": ["US"], "from_phonemes": True})
    return out


def stress_suffix_ipa(word: str) -> list[dict]:
    """Two regular suffixes, using dictionary bases only (card 551).

    -ically keeps the -ic base's stress; -isation/-ization moves main stress
    to -ation. Every derived value remains explicitly marked as an estimate.
    """
    w = word.lower()
    out: list[dict] = []
    if w.endswith("ically") and len(w) > 9:
        base = w[:-4]
        for row in _stress_suffix_bases(base, "ɪk"):
            body = row["ipa"].strip("/")
            out.append({**row, "ipa": f"/{body}li/",
                        "composed": True, "estimate": True, "base": f"{base} + -ally",
                        "derived": "spelling"})
    m_ = re.fullmatch(r"([a-z]{4,})(is|iz)ation", w)
    if m_:
        for verb in (m_.group(1) + "ise", m_.group(1) + "ize"):
            for row in _stress_suffix_bases(verb, "aɪz"):
                body = row["ipa"].strip("/")
                body = body.replace("ˈ", "ˌ")[:-1] + "ˈzeɪʃən"
                out.append({**row, "ipa": f"/{body}/",
                            "composed": True, "estimate": True, "base": f"{verb} + -ation",
                            "derived": "spelling"})
    seen, uniq = set(), []
    for r in out:
        if r["ipa"] not in seen:
            seen.add(r["ipa"])
            uniq.append(r)
    return uniq[:3]


@lru_cache(maxsize=20_000)
def _family_cap(word: str, language: str) -> int | None:
    """One level above the word's base's listed level (sunny <= sun + 1;
    -ed forms: the base's level, striped <= stripe B1 -- 問題回報 #214/#218/#221), whether or not
    [word] itself has some other listed part of speech. None when no
    listed base spelling is found. Candidate bases reuse images.py's
    morphology (suffix, prefix and spelling repairs already used to level
    photo-tag labels) rather than a second guesser."""
    if language != "en":
        return None
    from .. import images
    from .base import _listed_levels
    levels = _listed_levels()
    best = None
    # -ed forms (striped, potted) just describe "having/with" the base, so
    # they sit at the base's level (問題回報 #221: striped <= stripe B1)
    bump = 0 if word.endswith("ed") else 1
    for stem in images._base_candidates(word):
        lv = levels.get(stem)
        if lv is not None:
            best = lv + bump if best is None else min(best, lv + bump)
    return best


def derivation_cap(word: str, language: str) -> int | None:
    """[_family_cap], but None when [word] itself is listed under some part
    of speech -- its own level is then authoritative (standing noun C2
    「social standing」), so no family ceiling applies to it as a whole."""
    if language != "en":
        return None
    from .base import _listed_levels
    if word in _listed_levels():
        return None
    return _family_cap(word, language)


_CONCRETE_LEXNAMES = {"noun.artifact", "noun.food", "noun.plant", "noun.animal",
                      "noun.body", "noun.substance", "noun.object"}


@lru_cache(maxsize=10_000)
def is_concrete_noun(word: str) -> bool:
    """[word]'s dominant WordNet sense is a physical, photographable thing
    (artifact, food, plant, animal, body part, substance) -- scarecrow,
    croissant, cactus -- so a low zipf need not mean a hard CEFR level
    (問題回報 #220/#221). False without the WordNet index."""
    def lookup():
        synsets = _wordnet().synsets(word, pos="n")
        return synsets[0].lexfile() if synsets else None
    try:
        from .oewn import _thread, _wordnet
        lexfile = _thread.submit(lookup).result(timeout=5)
    except Exception:  # noqa: BLE001 — WordNet unavailable: no correction
        return False
    return lexfile in _CONCRETE_LEXNAMES


def capped_frequency_level(word: str, zipf_value: float, language: str = "en") -> str:
    """frequency_profile's CEFR estimate, capped by the word-family rule
    above so a derived word never estimates far above its base (問題回報
    #214/#218). [is_concrete_noun] is deliberately not applied here: a
    photographable noun's rarity in text is not always wrong (chalice is a
    genuinely C1/C2 word despite being a WordNet noun.artifact) -- the
    owner's decision for #163 is to recompute+flag concrete-noun candidates
    for manual review, not auto-correct them."""
    from .base import frequency_profile
    idx = LEVELS.index(frequency_profile(round(zipf_value, 1))["cefr"])
    cap = derivation_cap(word, language)
    if cap is not None:
        idx = min(idx, cap)
    return LEVELS[idx]


FR_REVIEWED = Path(__file__).resolve().parents[1] / "fr_cefr_reviewed.json"
FR_LEXIQUE = Path(__file__).resolve().parents[1] / "fr_lexique_lemma_zipf.json"


@lru_cache(maxsize=1)
def fr_reviewed() -> dict[str, str]:
    """法語基礎 3000 字's levels: wordfreq + Lexique frequency, then reviewed
    by Claude against the DELF A1-B1 descriptors (問題回報 #332 decision C;
    FLELex is CC BY-NC-SA). Built by tools/card335_fr_cefr.py."""
    if not FR_REVIEWED.exists():
        return {}
    return json.loads(FR_REVIEWED.read_text(encoding="utf-8"))["words"]


@lru_cache(maxsize=1)
def _fr_lexique() -> dict[str, float]:
    if not FR_LEXIQUE.exists():
        return {}
    return json.loads(FR_LEXIQUE.read_text(encoding="utf-8"))["lemmas"]


def fr_zipf(word: str) -> float:
    """A French lemma's zipf: the higher of wordfreq (one spelling) and
    Lexique 3.83's lemma frequency (all its forms -- parler, chaussure)."""
    return max(_zipf(word, "fr"), _fr_lexique().get(word, 0.0))


def fr_cefr_source(word: str) -> str:
    return "ai_reviewed" if (word or "").strip().lower() in fr_reviewed() else "frequency_estimate"


def word_level(word: str, language: str = "en") -> str:
    """A word's CEFR level: its easiest CEFR-J level when listed (French: the
    reviewed 3000-word list), else a capped frequency estimate (a phrase
    counts as its hardest word)."""
    w = (word or "").strip().lower()
    hit = cefr_list().get(w) if language == "en" else None
    if hit:
        return min(hit[1].values(), key=LEVELS.index)
    if language == "fr" and w in fr_reviewed():
        return fr_reviewed()[w]
    parts = tokens(w) if language == "en" else [w]
    if len(parts) > 1:
        return max((word_level(p, language) for p in parts), key=LEVELS.index)
    return capped_frequency_level(w, fr_zipf(w) if language == "fr" else _zipf(w, language), language)


# Kaikki tags of a conjugation nobody meets in an example sentence: the past
# historic (je vis = voir) and a form that is only subjunctive (qu'il fonde =
# fondre). Such a use of another verb does not make the form ambiguous.
_FR_RARE_USE_TAGS = {"historic", "dialectal", "regional"}


@lru_cache(maxsize=20_000)
def _fr_form_verbs(form: str) -> tuple[tuple[str, bool], ...]:
    """The verbs French Wiktionary conjugates ``form`` from, with whether
    that use is a common one: suis → (être, True), (suivre, True); vis →
    (vivre, True), (voir, False — past historic). Empty without the Kaikki
    index."""
    from .. import kaikki_index
    out: dict[str, bool] = {}
    for e in kaikki_index.lookup("fr", form) or []:
        if str(e.get("word", "")).lower() != form or e.get("pos") != "verb":
            continue
        for s in e.get("senses") or []:
            tags = set(s.get("tags") or [])
            # A regional (Louisiana été = aller), dated or dialectal use is
            # no competitor either.
            regional = any(t[:1].isupper() for t in tags)
            common = not (tags & (_FR_RARE_USE_TAGS | RARE_SENSE_LABELS)) and not regional and not (
                "subjunctive" in tags and not tags & {"indicative", "imperative"})
            for b in form_bases(s):
                b = b.strip().lower()
                if b:
                    out[b] = out.get(b, False) or common
    return tuple(sorted(out.items()))


@lru_cache(maxsize=20_000)
def _fr_verb_lemma(word: str) -> bool:
    """French Wiktionary gives ``word`` a verb meaning of its own (être,
    aller), not only form-of senses (fait, poli, admis — participles)."""
    from .. import kaikki_index
    from .base import is_form_sense
    return any(str(e.get("word", "")).lower() == word and e.get("pos") == "verb"
               and any(not is_form_sense(s) for s in e.get("senses") or [])
               for e in kaikki_index.lookup("fr", word) or [])


def _unaccent(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c))


def fr_shared_verb_forms(lemma: str, verb_forms) -> frozenset[str]:
    """Conjugations of ``lemma`` that another verb, at least a fifth as
    frequent, uses in a common tense (問題回報 #582): suivre's « suis » is
    almost always être, so it finds and matches no example sentence. être
    keeps « suis » (suivre is far rarer); vivre keeps « vis » (voir's use is
    the past historic); the infinitive is never shared away. The verb the
    lemma itself conjugates (aimé → aimer, connaitre → connaître) and a
    participle entry (polis → poli) are not other verbs."""
    lemma = (lemma or "").lower()
    own_bases = {b for b, _ in _fr_form_verbs(lemma)} | {lemma, _unaccent(lemma)}
    own = max(fr_zipf(b) for b in own_bases)  # paraitre counts as paraître
    shared = set()
    for f in verb_forms:
        f = (f or "").lower()
        if not f or f == lemma or " " in f:
            continue
        for base, common in _fr_form_verbs(f):
            if not common or base in own_bases or _unaccent(base) in own_bases:
                continue
            if not _fr_verb_lemma(base):
                continue
            if fr_zipf(base) >= own - 0.7:  # the other verb ≥ 1/5 as frequent
                shared.add(f)
                break
    return frozenset(shared)


def _fr_shared_forms(ctx: Context) -> frozenset[str]:
    """fr_shared_verb_forms for this run's verb-form items."""
    if getattr(ctx, "target", None) != "fr":
        return frozenset()
    verb_forms = {(i.get("form") or "").lower() for k in catalog.INFLECTION_FIELDS
                  if catalog.FORM_POS.get(k) == "verb" for i in ctx.items(k)}
    return fr_shared_verb_forms(ctx.lemma, verb_forms)


def word_forms(ctx: Context) -> frozenset[str]:
    """The headword and its inflected forms, lower case. For French, a
    conjugation another frequent verb shares (suivre's suis, 問題回報 #582)
    is left out: it would find that verb's sentences."""
    forms = {ctx.lemma.lower()}
    shared = _fr_shared_forms(ctx)
    for k in catalog.INFLECTION_FIELDS:
        for i in ctx.items(k):
            if i.get("form") and (ctx.target != "en" or plausible_form(ctx.lemma, i["form"])):
                if i["form"].lower() not in shared:
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
        if f == "cefr" and ctx.target in ("en", "fr"):
            # Not in CEFR-J (English): estimated from wordfreq, and marked so.
            # French has no open CEFR list (FLELex is CC BY-NC-SA): the
            # 3000-word list is AI-reviewed (#332), the rest a frequency estimate.
            level = word_level(ctx.lemma, ctx.target)
            source = fr_cefr_source(ctx.lemma) if ctx.target == "fr" else "frequency_estimate"
            C.append(Candidate(f, ctx.target, {"level": level, "by_pos": {}, "estimate": True,
                                               "cefr_source": source}, level,
                               confidence=0.6 if source == "ai_reviewed" else 0.5,
                               source_record_id=ctx.lemma))
        elif f == "ipa" and ctx.target == "en" and " " in ctx.lemma:
            # A phrase: its words' pronunciations (cutting board).
            parts = [(cefr_list().get(w) or [None, None, None])[2] for w in ctx.lemma.split()]
            if parts and all(parts):
                ipa = "/" + " ".join(p.strip("/") for p in parts) + "/"
                C.append(Candidate(f, "en", {"ipa": ipa, "accent": "US", "composed": True}, ipa,
                                   confidence=0.6, source_record_id=ctx.lemma))
        elif f == "ipa" and ctx.target == "en":
            # A regular inflection (drizzled, crinkled): its base word's IPA
            # with the suffix's sound; else a derivative's parts (frother,
            # 問題回報 #291), an estimate with a lower confidence.
            for v in (inflected_ipa(ctx.lemma) or derived_adjective_ipa(ctx.lemma)
                      or linked_base_ipa(ctx.lemma) or derived_affix_ipa(ctx.lemma)
                      or stress_suffix_ipa(ctx.lemma)):
                C.append(Candidate(f, "en", v, v["ipa"],
                                   confidence=0.5 if v.get("estimate") else 0.6,
                                   source_record_id=ctx.lemma))
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
                          ((cefr_list().get(ctx.lemma) or [None, {}])[1] or {})] \
                    if ctx.target == "en" else []
            except Exception:  # noqa: BLE001 — no list: the most senses
                listed = []
            if ctx.target == "en":
                main_pos = next((p for p in listed if p in by_pos),
                                max(by_pos, key=lambda p: len(by_pos[p])) if by_pos else None)
            else:
                # No CEFR list for French: the dictionary lists the main
                # part of speech first (maison noun «house» before the
                # adjective «homemade», card #329), sense count misleads.
                main_pos = next(iter(by_pos), None)
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
                if ctx.target == "en":
                    use = _usage_pos(item.get("text", ""), forms, verb_only, ctx.lemma)
                else:
                    use = _usage_pos_fr(item.get("text", ""), forms, verb_only)
                if use == "other":
                    continue  # 「the wound」: a verb form used as a noun is another word
                # A French sentence shares no words with an English gloss:
                # its sense is the part of speech it shows (card #329).
                words = (set(tokens(item.get("text", "")))
                         - ENGLISH_STOPWORDS - SENSE_COUNT_WORDS - forms) \
                    if ctx.target == "en" else set()
                ranked = []
                for s in senses:
                    if use and s.get("pos") and s.get("pos") != use and any(
                            x.get("pos") == use for x in senses):
                        continue  # mugged is the verb, the mug the noun
                    gloss = (set(tokens(s.get("gloss", "")))
                             - ENGLISH_STOPWORDS - SENSE_COUNT_WORDS - forms)
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
                # etymology) still needs that evidence. French has no gloss
                # evidence: chat /ʃa/ «cat» (listed first) takes the
                # sentence, not chat /tʃat/ «online chat» (card #329).
                if homograph and ctx.target == "en":
                    continue
                # Otherwise the main usage's first common sense: the part of
                # speech the sentence shows, else the CEFR-J listed one.
                usage = use if use in by_pos else main_pos
                common = [x for x in by_pos.get(usage, []) if not _rare_sense(x)]
                first = common[0] if common else (by_pos.get(usage) or [None])[0]
                if first is not None:
                    value = {"example_key": k, "sense_key": first.get("sense_key")}
                    # Kaikki order is not frequency order (spell 「使著魔」
                    # before 「拼字」): a guess among several senses says so,
                    # and Qwen picks the sense later (card #528,
                    # tools/card528_pick.py).
                    if len(by_pos.get(usage) or []) > 1:
                        value["evidence"] = "fallback"
                    C.append(Candidate(f, ctx.target, value, k, slot=k, confidence=0.4))
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
    for k in catalog.INFLECTION_FIELDS:
        for i in ctx.items(k):
            form = (i.get("form") or "").lower()
            if form:
                # English verb_* and French fr_present_* / fr_past_participle.
                is_verb = catalog.FORM_POS.get(k) == "verb" and k != "verb_base"
                (verb if is_verb else other).add(form)
    # suivre's « suis » is être's too (問題回報 #582): not a form to match on.
    return frozenset(verb - other - _fr_shared_forms(ctx))


# French determiners before a noun: la maison, une maison, ma maison, à la
# maison (card #329: a sentence's part of speech, like _usage_pos for English).
FR_DETERMINERS = {"le", "la", "les", "l", "un", "une", "des", "du", "au", "aux", "ce", "cet",
                  "cette", "ces", "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses",
                  "notre", "votre", "leur", "nos", "vos", "leurs", "quel", "quelle", "quels",
                  "quelles", "chaque", "plusieurs", "quelques", "aucun", "aucune", "tout",
                  "toute", "tous", "toutes"}
# What may follow a noun phrase (la maison est…, à la maison avec…); «un grand
# homme» continues with a noun, so grand is the adjective there.
FR_PHRASE_END = {"est", "sont", "était", "étaient", "sera", "seront", "a", "ont", "avait",
                 "de", "du", "des", "d", "à", "au", "aux", "en", "dans", "sur", "sous", "avec",
                 "pour", "par", "sans", "chez", "vers", "entre", "que", "qu", "qui", "dont",
                 "où", "et", "ou", "mais", "ne", "n", "se", "s", "y", "me", "te", "nous",
                 "vous", "il", "elle", "ils", "elles", "je", "tu", "on", "ce", "c", "là",
                 "ici", "aussi", "très", "trop", "plus", "moins", "encore", "toujours",
                 "jamais", "déjà", "maintenant", "hier", "demain", "puis", "donc", "si"}


# Determiners that never stand before a verb (問題回報 #575). Not le / la /
# les / l' (object pronouns: «il la place»), leur («je leur livre»), ce («ce
# faisant») or tout («tout compte fait»).
# trois places
_FR_NUMBERS = {"deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "vingt",
               "cent", "mille"}
# pas de place, sur place, à part: no finite verb or participle follows a
# preposition (a verb after de is the infinitive; en does: «il en place»).
_FR_PREPOSITIONS = {"de", "d", "sur", "sous", "avec", "sans", "par", "pour", "chez", "vers",
                    "contre", "dans", "entre", "à", "selon", "malgré", "parmi"}
_FR_NOUN_DET = {"un", "une", "des", "du", "au", "aux", "cet", "cette", "ces", "mon", "ma", "mes",
                "ton", "ta", "tes", "son", "sa", "ses", "notre", "votre", "nos", "vos", "leurs",
                "quel", "quelle", "quels", "quelles", "chaque", "plusieurs", "quelque", "quelques", "aucun",
                "aucune", "nul", "nulle", "certains", "certaines", "divers", "diverses",
                } | _FR_NUMBERS | _FR_PREPOSITIONS
_FR_ARTICLE = {"le", "la", "les", "l"}
# Before le / la / les / l' these make it the object pronoun: «je le livre»,
# «ne la place pas», «qui les force», «te l'adresse».
_FR_CLITIC_HOSTS = {"je", "j", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "ne", "n",
                    "me", "m", "te", "t", "se", "s", "lui", "y", "en", "qui"}
# Capitalised words that open a sentence rather than name someone.
_FR_SENTENCE_START = {"voici", "voilà", "et", "mais", "puis", "alors", "donc", "ensuite", "enfin",
                      "oui", "non", "regarde", "regardez", "prends", "prenez", "donne", "donnez",
                      "où", "quand", "comme", "c", "ça", "cela", "ceci"}
# Adjectives that stand before the noun: «un petit masque», «la grande place».
_FR_PRENOMINAL = {
    "petit", "petite", "petits", "petites", "grand", "grande", "grands", "grandes", "bon", "bonne",
    "bons", "bonnes", "beau", "bel", "belle", "beaux", "belles", "nouveau", "nouvel", "nouvelle",
    "nouveaux", "nouvelles", "vieux", "vieil", "vieille", "vieilles", "jeune", "jeunes", "gros",
    "grosse", "grosses", "mauvais", "mauvaise", "mauvaises", "autre", "autres", "premier",
    "première", "premiers", "premières", "dernier", "dernière", "derniers", "dernières", "même",
    "mêmes", "seul", "seule", "seuls", "seules", "vrai", "vraie", "vrais", "vraies", "joli", "jolie",
    "jolis", "jolies", "long", "longue", "longs", "longues", "haut", "haute", "meilleur",
    "meilleure", "meilleurs", "meilleures", "pire", "double", "simple", "deuxième", "troisième",
    "énorme", "énormes", "excellent", "excellente", "gentil", "gentille", "immense", "large",
    "nombreux", "nombreuses", "chouette", "chouettes", "faux", "fausse", "fausses"}
# un très petit livre, une si belle fête: a degree adverb before that adjective.
_FR_DEGREE = {"très", "si", "trop", "assez", "aussi", "plus", "moins", "bien", "tout", "toute"}


def _fr_det_led(toks: list[str], cased: list[str], i: int) -> bool:
    """The token at ``i`` heads a noun phrase: a determiner just before it,
    or before one pre-nominal adjective (un masque, au cours, ma part, la
    bouche, un petit masque). le / la / les / l' after a subject or clitic
    pronoun is the object pronoun (il la place, je l'adresse), and after a
    name it may be one too (Marie la place)."""
    def det(j: int) -> bool:
        if j < 0:
            return False
        if toks[j] in _FR_NOUN_DET:
            # quelqu'un fouille, l'un assemble: the pronoun, then the verb
            return not (toks[j] in ("un", "une") and j > 0 and toks[j - 1] in ("quelqu", "l"))
        if toks[j] == "ce":
            return not toks[i].endswith("ant")  # ce masque; not «ce faisant»
        if toks[j] not in _FR_ARTICLE:
            return False
        if j == 0:
            return True
        host = toks[j - 1]
        # «Voici le livre.» mid-text: a capital after a full stop, not a name (#575)
        name = j - 1 > 0 and cased[j - 1][:1].isupper() and host not in _FR_SENTENCE_START
        return host not in _FR_CLITIC_HOSTS and not name
    if i and toks[i - 1] in _FR_NUMBERS and toks[i].endswith(("é", "ée", "és", "ées")):
        return False  # cinq divisé par trois
    if det(i - 1):
        return True
    # un petit masque — not «à nouveau enfermé», «de même placé»
    # de nombreux livres, d'autres places: a plural adjective after de is partitive (#575)
    if i > 1 and toks[i - 1] in _FR_PRENOMINAL and toks[i - 1].endswith(("s", "x")) \
            and toks[i - 2] in ("de", "d") and toks[i - 1] not in ("plus", "mauvais", "gros"):
        return True
    if i > 1 and toks[i - 1] in _FR_PRENOMINAL and toks[i - 2] not in _FR_PREPOSITIONS:
        if det(i - 2):
            return True
        # un très petit livre (#575)
        return i > 2 and toks[i - 2] in _FR_DEGREE and det(i - 3)
    return False


def _fr_other_lemma(form: str) -> bool:
    """A verb form that is also a French lemma of its own (or its plural),
    per Lexique: masque, place, cours, accusé, lions → lion. Not «stoppons»
    or «embellit»: there le / l' before it is the object pronoun («comment le
    stoppons-nous», «et l'embellit»)."""
    lemmas = _fr_lexique()
    return form in lemmas or (form[-1:] in ("s", "x") and form[:-1] in lemmas)


def _fr_tokens(text: str) -> tuple[list[str], list[str]]:
    """Words lower-cased and as written, split at elisions (l'école → l, école)."""
    raw = [p for t in re.split(r"[^A-Za-zÀ-ÿœæŒÆ'’]+", (text or "").replace("’", "'"))
           for p in t.strip("'").split("'") if p]
    return [t.lower() for t in raw], raw


def _usage_pos_fr(text: str, forms, verb_only) -> str | None:
    """Which part of speech the French headword is in this sentence: "noun"
    after a determiner when the noun phrase ends there (la maison est…,
    une belle maison), "verb" for a form only the verb has (mangeons),
    "other" when the word is not there, else None (unclear).

    A form only the verb has, right after a determiner, is a noun spelt the
    same — another word (問題回報 #575): la place (placer), le livre
    (livrer), un masque (masquer), au cours (courir), ma part (partir). When
    every use in the sentence is such a noun, the sentence is "other"."""
    toks, cased = _fr_tokens(text)
    if not any(t in forms for t in toks):
        return "other"
    foreign = own = False
    for i, t in enumerate(toks):
        if t not in forms:
            continue
        if t in verb_only:
            if _fr_det_led(toks, cased, i) and _fr_other_lemma(t):
                foreign = True
                continue
            return "verb"
        own = True  # «la place pour placer…»: the infinitive is this word
        near_det = i > 0 and (toks[i - 1] in FR_DETERMINERS
                              or (i > 1 and toks[i - 2] in FR_DETERMINERS))
        ends = i == len(toks) - 1 or toks[i + 1] in FR_PHRASE_END
        if near_det and ends:
            return "noun"
    return "other" if foreign and not own else None


# Finite copulas only. Bare "be" is "must be shadow" (a noun), not "is tired".
_COPULA = {"is", "are", "was", "were", "am", "seems", "seem", "seemed",
           "looks", "look", "looked", "feels", "feel", "became", "become"}
_DEGREE = {"very", "really", "so", "too", "quite", "more", "most", "extremely"}
_MODAL = {"will", "would", "can", "could", "should", "must", "may", "might", "did", "does"}
# -ly nouns/verbs that are not manner adverbs.
_NOT_LY_ADV = {"family", "apply", "reply", "supply", "imply", "only", "fly", "belly"}
# Not "al"/"ic": those endings are the noun itself (metal, traffic).
_ADJ_SUFFIX = ("ed", "ful", "ous", "ive", "less", "able", "ible", "ish")
# Closed-class adverbs that sit between a subject and a verb. They are not
# the noun head of "a coffee mug", even when a determiner is two words back
# (問題回報 #241: "My head still felt").
_PREVERBAL = {
    "still", "even", "just", "also", "only", "already", "always", "never",
    "often", "ever", "almost", "rather", "quite", "not", "now", "then",
    "yet", "again", "once", "soon", "sometimes", "usually", "really",
    "actually", "suddenly", "seldom", "rarely", "hardly", "nearly",
    "simply", "finally", "too", "so", "here", "there",
}
_FINITE_VERB = {
    "is", "are", "was", "were", "am", "be", "been", "do", "does", "did",
    "has", "have", "had", "will", "would", "can", "could", "should",
    "must", "may", "might",
}
# A base form right after one of these is the verb: 「doesn't fear the
# tiger」, 「should drink milk」, 「Don't worry」 (問題回報 #557). Bare do /
# does / did are left out: 「did everything」 makes the word an object.
_AUX_BEFORE_VERB = {
    "will", "would", "can", "could", "should", "must", "may", "might", "shall",
    "won't", "wouldn't", "can't", "cannot", "couldn't", "shouldn't", "mustn't",
    "mightn't", "shan't", "don't", "doesn't", "didn't", "never",
}
_NOT_HOSTS = _AUX_BEFORE_VERB | {"do", "does", "did"}
# 「want to change」, 「able to drink」, 「how to fear」: the word before
# ``to`` takes an infinitive, so the base form after it is the verb.
_INFINITIVE_HOSTS = {
    "want", "wants", "wanted", "need", "needs", "needed", "like", "likes", "liked",
    "love", "loves", "loved", "hate", "hates", "hated", "going", "able", "unable",
    "try", "tries", "tried", "trying", "used", "have", "has", "had", "ought", "how",
    "order", "decide", "decided", "decides", "hope", "hopes", "hoped", "begin",
    "begins", "began", "start", "starts", "started", "seem", "seems", "seemed",
    "tend", "tends", "tended", "learn", "learns", "learned", "learnt", "forget",
    "forgets", "forgot", "refuse", "refuses", "refused", "plan", "plans", "planned",
    "mean", "means", "meant", "expect", "expects", "expected", "wish", "wishes",
    "wished", "afford", "manage", "managed", "supposed", "allowed", "likely",
    "easy", "hard", "difficult", "impossible", "possible", "ready", "willing",
    "enough", "prefer", "prefers", "preferred", "continue", "continued", "promise",
    "promised", "agree", "agreed", "fail", "failed", "dare", "happy", "glad",
    "afraid", "free", "time", "way", "chance", "nothing", "something", "anything",
}
# 「went to work the field」 is rare; 「went to school the next day」 is not,
# so a determiner after the word proves nothing when movement leads to it.
_MOTION_BEFORE_TO = {
    "go", "goes", "went", "gone", "going", "come", "comes", "came", "get", "gets",
    "got", "back", "return", "returned", "walk", "walked", "drive", "drove",
    "travel", "travelled", "traveled", "way", "trip", "visit", "move", "moved",
    "send", "sent", "take", "took", "taken", "bring", "brought", "run", "ran",
    "off", "down", "up", "out", "over", "home", "straight", "directly",
}


# Hyphenated headwords (close-up) stay one token. Other hyphens still split
# (well-known → well, known), which is what a non-compound lemma needs.
_SURFACE = re.compile(r"[A-Za-zÀ-ÿœæ']+(?:-[A-Za-zÀ-ÿœæ']+)*")
_VERBISH = _FINITE_VERB | {
    "go", "goes", "went", "gone", "come", "came", "make", "made", "take", "took",
    "see", "saw", "feel", "feels", "felt", "seem", "seems", "look", "looks",
    "get", "gets", "got", "say", "said", "know", "think", "want", "need",
    "drive", "drove", "driven", "sing", "sang", "run", "ran", "give", "gave",
}


def _form_bag(forms) -> set[str]:
    return {str(f).lower() for f in forms if f}


def _surface_pieces(text: str, forms) -> tuple[list[str], list[str], list[str], list[bool]]:
    """Lowercase tokens, original case, and whether each token starts a sentence.

    A hyphen stays inside the token (close-up, merry-go-round). Splitting it
    would make round match inside merry-go-round.
    """
    _ = forms
    raw, cased, starts = [], [], []
    for match in _SURFACE.finditer(text or ""):
        span = match.group(0)
        prefix = (text or "")[:match.start()]
        sentence_start = (not prefix.rstrip(" \"'“‘(").strip()
                          or prefix.rstrip(" \"'“‘(").endswith((".", "!", "?", ":")))
        raw.append(span.lower())
        cased.append(span)
        starts.append(sentence_start)
    toks = [t[:-2] if t.endswith("'s") else t.rstrip("'") for t in raw]
    return raw, toks, cased, starts


def _word_tokens(text: str, forms=()) -> tuple[list[str], list[str]]:
    raw, toks, _cased, _starts = _surface_pieces(text, forms)
    return raw, toks


def _listed_poses(word: str) -> set[str]:
    word = (word or "").lower()
    keys = [word]
    # "plumes" is plume + s, not plum + es. Prefer a listed singular.
    if len(word) > 3 and word.endswith("s") and word[:-1] in cefr_list():
        keys.append(word[:-1])
    elif word.endswith("ies") and len(word) > 4:
        keys.append(word[:-3] + "y")
    elif word.endswith("es") and len(word) > 3:
        keys.append(word[:-2])
    elif word.endswith("s") and len(word) > 3:
        keys.append(word[:-1])
    for key in keys:
        hit = cefr_list().get(key)
        if hit and len(hit) > 1 and isinstance(hit[1], dict) and hit[1]:
            return {str(p).rstrip(".") for p in hit[1]}
    return set()


def _participle_modifier(toks: list[str], i: int) -> bool:
    """scalloped potatoes, fanged mushrooms, well versed — not He graded assignments."""
    prev = toks[i - 1] if i else ""
    nxt = toks[i + 1] if i + 1 < len(toks) else ""
    if prev in _DEGREE | {"well"}:
        return True
    if "adj" in _listed_poses(prev):
        return True
    prep = {"of", "in", "on", "with", "for", "from", "by", "at", "to", "into",
            "and", "or", "well", "against", "about", "over", "under", "after",
            "before", "without", "through"}
    if nxt and "noun" in _listed_poses(nxt) and (
            prev in DETERMINERS | _DEGREE | prep
            or (prev in {"has", "have", "had"} and toks[i].endswith("ing"))):
        return True
    if toks[i].endswith("ing") and prev in {"and", "or"}:
        return True
    # "the housing market", "a manned compact vehicle": the participle
    # modifies a noun. "He graded assignments" and "quickly graded assignments"
    # stay verbs.
    subject = {"i", "he", "she", "we", "they", "you", "it", "tom", "mary"}
    if (toks[i].endswith(("ed", "ing"))
            and prev not in subject | _FINITE_VERB | _COPULA | _VERBISH | _MODAL
            and not prev.endswith("ly") and "adv" not in _listed_poses(prev)):
        nxt2 = toks[i + 2] if i + 2 < len(toks) else ""
        if nxt and "noun" in _listed_poses(nxt):
            return True
        # "manned compact vehicle": compact is not listed, vehicle is the noun.
        if nxt2 and "noun" in _listed_poses(nxt2) and (
                _clear_adj(nxt) or not _listed_poses(nxt)):
            return True
    return False


def _lexical_verb(token: str) -> bool:
    """A real verb, not a word that merely ends in -ed (red)."""
    if not token or token in DETERMINERS:
        return False
    if token in _VERBISH:
        return True
    poses = _listed_poses(token)
    if poses:
        return "verb" in poses and "adj" not in poses and "noun" not in poses
    return len(token) > 4 and token.endswith(("ed", "ing"))


def _adj_evidence(token: str) -> bool:
    """Dictionary or an existing shape says this complement is an adjective."""
    poses = _listed_poses(token)
    if _looks_adj_token(token) or token.endswith(("ary", "ory")):
        return True
    if "adj" in poses and "verb" not in poses:
        return True
    return not poses and suffix_pos(token) == "adj"


def _adj_not_noun(token: str) -> bool:
    """Attributive adjective, not a noun modifying another noun (chocolate fudge)."""
    poses = _listed_poses(token)
    if "noun" in poses and "adj" not in poses:
        return False
    if "adj" in poses and "noun" not in poses:
        return True
    if poses:
        return False
    if "-" in token:
        return True
    return suffix_pos(token) == "adj"


def _can_be_modified(token: str) -> bool:
    """The word after an attributive adjective: a noun or another adjective."""
    poses = _listed_poses(token)
    if not poses:
        return False
    if "verb" in poses and "noun" not in poses and "adj" not in poses:
        return False
    return "noun" in poses or "adj" in poses


def _clear_adj(token: str) -> bool:
    """An adjective, not a noun that merely also lists an adjective reading."""
    poses = _listed_poses(token)
    if "adj" in poses and "noun" not in poses:
        return True
    if "adj" in poses and _easiest_listed_pos(token) == "adj":
        return True
    return not poses and suffix_pos(token) == "adj"


def _looks_adj_token(token: str) -> bool:
    """A real adjective ending, not a short word that happens to end that way (olive)."""
    for suf in _ADJ_SUFFIX:
        if token.endswith(suf) and len(token) - len(suf) >= 3:
            return True
    return False


def _easiest_listed_pos(word: str) -> str | None:
    hit = cefr_list().get(word or "")
    if not hit or len(hit) < 2 or not isinstance(hit[1], dict) or not hit[1]:
        return None
    pos_map = hit[1]
    best = min(pos_map, key=lambda p: LEVELS.index(pos_map[p]) if pos_map[p] in LEVELS else 9)
    return best.rstrip(".")


def _gap_modifier(word: str) -> bool:
    """The word between a determiner and a candidate head is an adjective
    (``an icy wind``, ``a quiet still``), not the noun of the subject
    (``my head still``)."""
    if not word:
        return False
    if word in _DEGREE or _looks_adj_token(word) or suffix_pos(word) == "adj":
        return True
    return _easiest_listed_pos(word) == "adj"


def _one_edit(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if a == b[:i] + b[i + 1:]:
            return True
    return False


def _form_of_lemma(lemma: str, form: str) -> bool:
    """True when ``form`` is this headword, not another verb's paradigm (seen/saw)."""
    lemma, form = lemma.lower(), (form or "").lower()
    if not form:
        return False
    if form == lemma or plausible_form(lemma, form):
        return True
    # shoe/shod is one edit. cultivated/cultivates is another word's -s form.
    if form.endswith("s") or lemma.endswith("s"):
        return False
    return _one_edit(lemma, form)


def matches_lexeme_pos(text: str, lemma: str, pos: str, forms, verb_only=()) -> bool:
    """True when this sentence uses ``lemma`` as ``pos``.

    A different detected use is rejected (``I eat bread`` is not the verb).
    An unclear sentence is rejected too, so a rare part of speech is not
    filled with the common one. Noun evidence has to be a real noun phrase:
    ``My head still felt`` is not the noun ``still`` even though a determiner
    sits two words earlier.
    """
    bag = {str(f).lower() for f in forms if f and _form_of_lemma(lemma, str(f))}
    bag.add(lemma.lower())
    if pos == "intj":
        return _intj_frame(text, bag)
    if pos == "noun" and " " in lemma:
        # "raised bed", "spiral arms": the single-word frames never match a
        # compound, so every sentence was rejected (卡 #166).
        joined = " " + " ".join(tokens(text)) + " "
        return any(" " + " ".join(tokens(f)) + " " in joined for f in bag if " " in f)
    if pos in _CLOSED_CLASS:
        return lemma.lower() in _CLOSED_CLASS[pos] and _closed_class_frame(text, lemma.lower(), pos)
    only = frozenset(str(f).lower() for f in verb_only if _form_of_lemma(lemma, str(f))
                     and str(f).lower() != lemma.lower())
    use = _usage_pos(text, bag, only, lemma)
    if use == "other" or (use and use != pos and pos not in ("adj", "adv")):
        return False
    if pos == "verb":
        return use == "verb" or _verb_frame(text, lemma, only)
    if pos == "noun":
        return use != "verb" and _noun_frame(text, bag)
    if pos == "adj":
        return _adj_frame(text, lemma, bag)
    if pos == "adv":
        return _adv_frame(text, lemma, bag)
    if pos == "phrase" and " " in lemma:
        return lemma.lower() in " ".join(tokens(text))
    return False


# Function words (問題回報 #351). Their dictionary pos is often odd (swim/pron,
# do/num), so only these lemmas are ever accepted, each as the listed pos.
_CLOSED_CLASS = {
    "prep": {"about", "along", "as", "near", "on", "except", "despite", "without", "per"},
    "conj": {"before", "until", "since", "till", "however", "yet", "where", "how", "because",
             "but", "whether"},
    "det": {"both", "each", "little", "much", "no", "one", "which", "certain", "enough", "per",
            "neither", "another", "any", "this", "many"},
    "pron": {"another", "any", "each", "either", "he", "i", "little", "many", "much", "one",
             "there", "this", "what", "where", "who", "anywhere", "plenty", "neither", "both"},
}
_SUBJECT = {"i", "you", "he", "she", "it", "we", "they", "there", "this", "that"}
_OBJECT = {"me", "him", "her", "us", "them", "you", "it"}


def _closed_class_frame(text: str, lemma: str, pos: str) -> bool:
    """The function word is used as ``pos``: a preposition has an object,
    a conjunction a clause, a determiner a noun after it, a pronoun stands
    alone (``Each of us``, ``I like this``). Any such use in the sentence counts."""
    raw, toks = _word_tokens(text, {lemma})
    for i, t in enumerate(toks):
        if t != lemma:
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        prev = toks[i - 1] if i else ""
        stops = bool(re.search(r"[,.;:!?)\"”]$", raw[i]))
        if pos == "prep":
            if not nxt or stops or prev in {"to"} or (i and raw[i - 1].endswith(",")):
                continue
            if nxt in DETERMINERS or nxt in _OBJECT or nxt[:1].isdigit() or (
                    nxt not in PHRASE_END and not _lexical_verb(nxt) and nxt not in _SUBJECT):
                return True
        elif pos == "conj":
            if not nxt or stops:
                continue
            if nxt in DETERMINERS or nxt in _SUBJECT or nxt in {"to"} or raw[i + 1][:1].isupper():
                return True
        elif pos == "det":
            if not nxt or stops or prev in {"the", "of"} or nxt in PHRASE_END or nxt in _FINITE_VERB:
                continue
            if (nxt in _COPULA or _lexical_verb(nxt) or nxt in _OBJECT or nxt in DETERMINERS
                    or nxt in _SUBJECT or nxt in {"about", "around", "more", "too", "so"}):
                continue
            return True
        elif pos == "pron":
            if lemma in {"he", "i", "there", "what", "when", "where", "who", "which", "anywhere"}:
                return True
            if (not nxt or stops or nxt in PHRASE_END or nxt in _FINITE_VERB or nxt in _COPULA
                    or nxt in {"of", "and", "or"}):
                return True
    return False


def _intj_frame(text: str, forms) -> bool:
    """The word is said on its own: ``"Cheese!" said the photographer.``

    It opens the sentence or a quote and is followed by ``!`` (or ``,``),
    so ``The fire was warm.`` is not the interjection (問題回報 #286)."""
    alts = "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
    return bool(re.search(
        r"(?:^|[.!?]\s+|[\"“‘(]\s*)(?:" + alts + r")[\"”’]?\s*[!,]",
        text.strip(), re.I))


def _verb_frame(text: str, lemma: str, verb_only: frozenset) -> bool:
    _raw, toks = _word_tokens(text, {lemma.lower(), *verb_only})
    if any(t in verb_only and not _participle_modifier(toks, i) for i, t in enumerate(toks)):
        return True
    for i, t in enumerate(toks):
        if t != lemma.lower() or i == 0:
            continue
        # "did everything", "did good": did/does right before the word is the
        # main verb, so the word is its object (問題回報 #351).
        if toks[i - 1] in _MODAL - {"did", "does"}:
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            # "Can orange trees" — the modal belongs to the later verb.
            if nxt in DETERMINERS or nxt in {"it", "him", "her", "them", "me", "us", "you"} or not nxt:
                return True
    # Imperative: "Bread the cutlets."
    if toks and toks[0] == lemma.lower() and len(toks) > 1 and toks[1] in DETERMINERS:
        return True
    return False


_IRREGULAR_VERB_FORMS = {
    form for lemma, forms in IRREGULAR_FORMS.items()
    if lemma not in {"child", "person", "man", "woman", "mouse", "goose",
                     "tooth", "foot", "good", "bad"}
    for form in forms
}


def _noun_frame(text: str, forms) -> bool:
    """``a``/``an``/``the`` directly before the head (``the bread``).

    ``that``/``this`` are also pronouns (``that still has``), and a following
    -ing word is often another modifier (``a separate smoking section``).
    """
    raw, toks = _word_tokens(text, forms)
    for i, t in enumerate(toks):
        if t not in forms or i == 0 or toks[i - 1] not in {"a", "an", "the"}:
            continue
        # "can" is also a noun ("an empty can"), so a modal here does not
        # prove the noun phrase has ended.
        np_end = PHRASE_END - {"can", "may", "might", "will", "must"}
        ends = i == len(toks) - 1 or toks[i + 1] in np_end or raw[i].endswith("'s")
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        # "a masculine and feminine system" and "the black-and-white marbled
        # cover" are modifiers. "a cunning thought": thought is a noun that
        # is also a verb form.
        # "a masculine and feminine system": X and Y modify the noun after them.
        # "the bread and butter" has no noun after the pair, so bread stays.
        if nxt in {"and", "or"} and i + 3 < len(toks):
            after = toks[i + 3]
            after_poses = _listed_poses(after)
            if "noun" in after_poses or (not after_poses and not _lexical_verb(after)):
                continue
        if "-" in t and not ends:
            continue
        next_verb = bool(nxt) and "noun" not in _listed_poses(nxt) and (
            nxt in _IRREGULAR_VERB_FORMS or nxt.endswith("ed"))
        if ends or next_verb:
            return True
    return False


def _adj_frame(text: str, lemma: str, forms) -> bool:
    """Predicative (``is crinkled``, ``is chocolate``) or attributive
    (``the crinkled paper``, ``an aquatic park``).

    A noun in front of another noun (``chocolate fudge``, ``this street``)
    is not enough. ``was spread`` / ``was carved into`` stay passives.
    ``Tom is observing`` is the progressive, not an adjective.
    """
    _raw, toks = _word_tokens(text, forms)
    for i, t in enumerate(toks):
        if t not in forms and t != lemma.lower():
            continue
        prev = toks[i - 1] if i else ""
        prev2 = toks[i - 2] if i > 1 else ""
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        predicative = prev in _COPULA or (prev in _DEGREE and prev2 in _COPULA)
        if predicative and not nxt and not t.endswith("ly"):
            poses = _listed_poses(t)
            if poses == {"adv"}:
                continue
            if (t.endswith("ing") and prev not in _DEGREE and "adj" not in poses
                    and not _looks_adj_token(t)):
                continue
            # was/were + a verb (was spread) is passive. was/were + an
            # adjective (was happy, was very fitting) is predicative.
            if prev in {"was", "were"}:
                if _adj_evidence(t):
                    return True
            else:
                return True
        after_det = prev in DETERMINERS or (prev in _DEGREE and prev2 in DETERMINERS)
        verbish_next = _lexical_verb(nxt) and "noun" not in _listed_poses(nxt) and "adj" not in _listed_poses(nxt)
        if (after_det and nxt and nxt not in PHRASE_END and nxt not in DETERMINERS
                and not verbish_next and (
                    (_looks_adj_token(t) and "noun" not in _listed_poses(t))
                    or (_can_be_modified(nxt) and _adj_not_noun(t)))):
            return True
    return False


def _adv_frame(text: str, lemma: str, forms) -> bool:
    """Manner -ly adverbs by presence. Other adverbs only in an adverb slot:
    closed-class (also), before a verb (still does), before an adjective
    (stone cold), or after a verb (hovered overhead). Not ``the still``,
    ``a red light``, ``goes flat``, or ``Today is Monday``.
    """
    w = lemma.lower()
    bag = _form_bag(forms)
    if w in _NOT_LY_ADV or w in DETERMINERS or _noun_frame(text, bag | {w}):
        return False
    _raw, toks = _word_tokens(text, bag | {w})
    if w.endswith("ly"):
        if "adj" in _listed_poses(w):
            # "such a lovely day", "an early bird": the adjective (問題回報 #351).
            for i, t in enumerate(toks):
                if t in bag | {w} and (i and toks[i - 1] in DETERMINERS):
                    return False
        return w in toks or any(t in bag and t.endswith("ly") for t in toks)
    if w not in toks and not any(t in bag for t in toks):
        return False
    poses = _listed_poses(w)
    listed_adv = "adv" in poses
    for i, t in enumerate(toks):
        if t != w and t not in bag:
            continue
        prev = toks[i - 1] if i else ""
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if prev in DETERMINERS:
            continue
        if "noun" in poses and nxt in _COPULA:
            continue
        if poses == {"adv"}:
            return True
        if listed_adv and _lexical_verb(nxt):
            return True
        if _clear_adj(nxt) and "adj" not in poses:
            return True
        if listed_adv and _clear_adj(nxt):
            return True
        if ((listed_adv or not poses) and "adj" not in poses and "noun" not in poses
                and not nxt and _lexical_verb(prev) and prev not in _COPULA):
            return True
        if listed_adv and nxt in PHRASE_END and prev not in _COPULA and _lexical_verb(prev):
            return True  # "She arrived early to help us."
        if (listed_adv and not nxt and prev not in _COPULA and not _lexical_verb(prev)):
            # "is not flat" / "basically flat" are adjectives. "o'clock sharp" is not.
            prev2 = toks[i - 2] if i > 1 else ""
            if "adj" in poses and (prev.endswith("ly") or prev in _DEGREE or prev == "not"
                                   or prev2 in _COPULA or prev2 in _DEGREE):
                continue
            return True
        if listed_adv and prev in _COPULA and _clear_adj(nxt):
            return True
    return False


def _base_after_auxiliary(toks: list[str], cased: list[str], starts: list[bool], i: int) -> bool:
    """The base form at ``i`` follows an auxiliary, a negation or an
    infinitive ``to``, so it is the verb (問題回報 #557): 「doesn't fear the
    tiger」, 「should drink milk」, 「Don't worry」, 「will never change」,
    「not to neglect your duty」, 「want to drink」.

    Not 「Can fear be useful?」 (fear is the subject of be), 「a can opener」
    (the modal is a noun), 「Will Smith」 (a name), 「is never fear」 or
    「went to school the next day」 (movement, then a new phrase).
    """
    if i == 0:
        return False
    prev = toks[i - 1]
    before = toks[i - 2] if i >= 2 else ""
    nxt = toks[i + 1] if i + 1 < len(toks) else ""
    if nxt in _FINITE_VERB or nxt in _VERBISH or (nxt and _lexical_verb(nxt)):
        return False

    def is_name(j: int) -> bool:
        return j < len(cased) and not starts[j] and cased[j][:1].isupper()

    if prev in _AUX_BEFORE_VERB:
        if is_name(i - 1) or before in ARTICLES:
            return False
        return not (prev == "never" and before in _COPULA)
    if prev == "not" and before in _NOT_HOSTS:
        return True
    if prev == "to":
        host = before if before != "not" else (toks[i - 3] if i >= 3 else "")
        if host in _INFINITIVE_HOSTS:
            return True
        return bool(host) and host not in _MOTION_BEFORE_TO and (
            nxt in DETERMINERS or nxt in _OBJECT)
    return False


# Verbs that take an adjective after them like ``is``: 「getting late」,
# 「stay awake」, 「sounds pretty」 (問題回報 #567). Not turn/go: 「turn right」.
_LINKING = {
    "be", "been", "being", "get", "gets", "got", "getting", "gotten", "grow", "grows",
    "grew", "growing", "stay", "stays", "stayed", "remain", "remains", "remained",
    "keep", "keeps", "kept", "sound", "sounds", "sounded", "smell", "smells", "smelled",
    "taste", "tastes", "tasted", "seeming", "looking", "feeling", "becoming", "becomes",
}
# Adjectives that are degree adverbs before another adjective even after a
# determiner: 「a pretty good idea」, 「a real nice guy」.
_DEGREE_ADJ = {"pretty", "real", "dead", "awful", "mighty", "jolly"}
# Adverbs a degree word can sit before: 「pretty well」, 「pretty soon」.
_ADV_HEADS = {"well", "much", "soon", "often", "far", "fast", "hard", "late", "early", "quickly"}


def _verb_before(prev: str) -> bool:
    """``prev`` is a verb the next word can modify as an adverb: 「works」 in
    「works hard」, 「arrived」, 「did」 — not is/get (they take adjectives)."""
    if (not prev or prev in _COPULA or prev in _LINKING or prev in DETERMINERS
            or prev in _MODAL - {"did", "does"} or prev in {"has", "have", "had", "am", "be"}):
        return False
    if prev in {"do", "does", "did", "done", "doing"} or prev in _VERBISH - _FINITE_VERB:
        return True
    poses = _listed_poses(prev)
    if poses:
        return "verb" in poses and "adj" not in poses and "adv" not in poses
    return len(prev) > 4 and prev.endswith(("ed", "ing"))


def _adj_adv_use(toks: list[str], i: int, pause: bool = False) -> str | None:
    """A word that is both an adjective and an adverb (pretty, fast, hard,
    late, well): the slot says which (問題回報 #567). 「are pretty proud」,
    「pretty well」, 「works hard」 → adv; 「is late」, 「a fast car」 → adj;
    otherwise None."""
    t = toks[i]
    prev = toks[i - 1] if i else ""
    prev2 = toks[i - 2] if i > 1 else ""
    nxt = toks[i + 1] if i + 1 < len(toks) else ""
    nxt2 = toks[i + 2] if i + 2 < len(toks) else ""
    ends = not nxt or nxt in PHRASE_END
    # 「It means "pretty", right?」, 「positions left open」: no degree word.
    before_adj = (bool(nxt) and not pause and nxt not in DETERMINERS
                  and _listed_poses(prev) != {"noun"} and (_clear_adj(nxt) or nxt in _ADV_HEADS))
    if prev in DETERMINERS:
        if before_adj and t in _DEGREE_ADJ:
            return "adv"  # a pretty good idea
        if nxt and "noun" in _listed_poses(nxt) and not _clear_adj(nxt):
            return "adj"  # a fast car, the late train
        return None
    if before_adj and (t in _DEGREE_ADJ or not nxt2 or nxt2 in PHRASE_END
                       or "noun" not in _listed_poses(nxt2)):
        return "adv"  # are pretty proud, fast asleep — not 「long hard days」
    if not ends:
        return None
    if prev in _COPULA | _LINKING or (prev in _DEGREE and prev2 in _COPULA | _LINKING):
        return None if t == "back" else "adj"  # is late, getting late
    if _verb_before(prev) or (prev in _DEGREE and _verb_before(prev2)):
        return "adv"  # works hard, arrived late, runs too fast
    return None


def _usage_pos(text: str, forms, verb_only, lemma: str | None = None) -> str | None:
    """Which part of speech the headword is in this sentence, when its form
    or a determiner before it says so: "verb" (Tom was mugged), "noun" (the
    mug), "other" (the wound — wind's past form used as a noun is another
    word), or None (unclear)."""
    if lemma and " " in lemma:
        # A phrase entry (butter knife): the phrase itself must be there.
        low_text = " ".join(tokens(text))
        return None if any(" " in f and f in low_text for f in forms) else "other"
    raw, toks, cased, starts = _surface_pieces(text, forms)
    low = (text or "").lower()
    if not any(t in forms for t in toks):
        return "other"  # 「this is a pen」: not this word at all
    # pretty, fast, hard, late, well (問題回報 #567). Closed-class adverbs
    # (still, even) keep the adverb-slot rule below.
    both_adj_adv = bool(lemma) and lemma.lower() not in _PREVERBAL and {
        "adj", "adv"} <= _listed_poses(lemma)
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
        plural_det = ((i > 0 and toks[i - 1] in ARTICLES | {"these", "those", "some", "many"})
                      or (i > 1 and toks[i - 2] in {"these", "those", "some", "many"}))
        if lemma and t != lemma and t.endswith("s") and not plural_det and any(
                b and b not in forms for b in (t[:-1], t[:-2] if t.endswith("es") else "")
        ) and base_is_word(t, lemma):
            return "other"
        if lemma and t == lemma.lower() and _base_after_auxiliary(toks, cased, starts, i):
            return "verb"  # 「doesn't fear the tiger」 (問題回報 #557)
        if both_adj_adv and t == lemma.lower():
            pause = bool(re.search(r"(?i)\b" + re.escape(t) + r"\b[\"'”’]?\s*[,;:.!?\"“”(—]", text or ""))
            use = _adj_adv_use(toks, i, pause)
            if use:
                return use
        if t in verb_only:
            # 「the wound」: a noun spelt like the verb's form is another
            # word; so is long-winded. (Not 「this applies」: a pronoun.)
            # 「many layers」: a quantifier means this form is the noun.
            if (i > 0 and toks[i - 1] in DETERMINERS | {
                    "many", "several", "few", "two", "three", "four", "five",
                    "six", "seven", "eight", "nine", "ten"}) or re.search(
                    r"\w-" + re.escape(t) + r"\b|\b" + re.escape(t) + r"-\w", low):
                return "other"
            if _participle_modifier(toks, i):
                continue
            return "verb"
        # A determiner just before, or before one modifier (a coffee mug),
        # and the noun phrase ends here — 「the crumbly soil」 is the adjective.
        ends = i == len(toks) - 1 or toks[i + 1] in PHRASE_END or raw[i].endswith("'s")
        next_is_verb = i + 1 < len(toks) and (
            toks[i + 1] in {form for values in IRREGULAR_FORMS.values() for form in values}
            or toks[i + 1].endswith(("ed", "ing")))
        plural_head = (t != lemma and t.endswith("s")
                       and (after_det or (i > 1 and toks[i - 2] in {"these", "those", "some", "many"})))
        finite_next = next_is_verb or (i + 1 < len(toks) and toks[i + 1] in _FINITE_VERB)
        # Determiner two words back + a following verb is "My head still felt",
        # not the noun still. "a coffee mug" is unchanged (mug is not an
        # adverb). "the still of the night" and "a quiet still" stay nouns.
        adverb_slot = (not after_det and t in _PREVERBAL and finite_next
                       and not _gap_modifier(toks[i - 1] if i else ""))
        if adverb_slot:
            continue
        return "noun" if near_det and (ends or next_is_verb or plural_head) else None
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
