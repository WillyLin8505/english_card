"""Lexicon quality rules (docs/LEXICON_QUALITY_RULES.md, 問題回報 #182–#186).

Pure functions, no database: the lint tool (tools/lint_lexicon.py) runs the
inclusion and CEFR rules over a whole pack; app_pack.build calls apply_pack()
so every pack ranks senses, orders examples and carries the flags/overrides
recorded under lexicon/quality/. Nothing here deletes data."""

from __future__ import annotations

import json
import re
from pathlib import Path

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
QUALITY_DIR = Path(__file__).resolve().parents[2] / "quality"

# Sense labels that make a sense low priority (hidden from the main meaning).
LOW_SENSE_LABELS = {
    "obsolete", "archaic", "dated", "rare", "slang", "humorous", "nonstandard",
    "historical", "vulgar", "derogatory", "offensive", "euphemistic", "poetic",
    "informal", "colloquial", "dialectal",
}
# Kaikki sense tags that are not a common, standalone meaning.
_NON_SUBSTANTIVE = LOW_SENSE_LABELS | {"alt-of", "form-of", "abbreviation", "initialism",
                                       "acronym", "misspelling", "alternative"}
OBJECT_PRONOUNS = {"her", "him", "them", "me", "us", "it", "my", "his", "its", "our",
                   "your", "their", "one's", "someone", "somebody", "something"}
# Placeholder names that dominate some Tatoeba sentences and read oddly.
ODD_NAMES = {"Ziri", "Mennad", "Baya", "Yanni", "Skura", "Rima", "Sami", "Layla", "Taninna"}
DERIV_SUFFIXES = ("y", "ful", "less", "ness", "ly", "er", "ish")
_POS_LIST = {"adj": "adj.", "adv": "adv."}


def level_index(level: str | None) -> int | None:
    return LEVELS.index(level) if level in LEVELS else None


# ---------------------------------------------------------------- inclusion
def _senses(entries: list[dict]):
    for e in entries:
        for s in e.get("senses") or []:
            yield e.get("pos"), s


def _substantive(entries: list[dict]) -> bool:
    """Has a common-noun/verb/... sense that is not rare, a form or an abbreviation."""
    for pos, s in _senses(entries):
        if pos == "name":
            continue
        tags = set(s.get("tags") or [])
        if s.get("form_of") or s.get("alt_of") or tags & _NON_SUBSTANTIVE:
            continue
        return True
    return False


_INFLECTION_TAGS = {"plural", "past", "participle", "gerund", "third-person",
                    "comparative", "superlative", "present"}
# 問題回報 #217: a handful of Kaikki senses carry no tags/form_of at all and
# only say so in the gloss text ("simple past and past participle of base").
# Matched only as a fallback (see _sense_base) and only against a single,
# un-nested gloss, so a sense with its own extra meaning layered on top of
# the form-of note (based: "simple past and past participle of base" +
# "Being derived from …") is never swallowed by the regex.
_INFLECTION_GLOSS_RE = re.compile(
    r"^(?:simple past(?: tense)? and past participle|simple past(?: tense)?|past participle|"
    r"present participle and gerund|present participle|plural|"
    r"third-person singular(?: simple present(?: indicative)?)?|comparative|superlative)"
    r" of ([A-Za-z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,3})\.?$", re.I)


# 問題回報 #296 (card #318): a spelling variant (distill = "US standard spelling
# of distil") is a pointer to the main entry, never a word of its own. The gloss
# shape is the same in DB definitions and Kaikki; tools/card318_variants.py
# imports this pattern.
VARIANT_GLOSS_RE = re.compile(
    r"^(?:(?:US|UK|British|American|Canadian|Australian|Irish|Oxford|Non-Oxford|obsolete|archaic|"
    r"nonstandard|dated|rare|standard|alternative|alternate|common|informal|eye|and|English|"
    r"misspelling|superseded|less common|uncommon|proscribed|hyphenated|unhyphenated)[ ,]+)*"
    r"(?:spelling|form|misspelling)s? of "
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]*?)(?:\s*[,:(“;].*|\.)?$", re.I)


def _sense_base(sense: dict, word: str) -> str | None:
    """The word this sense is purely a form of, by tag or (fallback) gloss text."""
    tags = set(sense.get("tags") or [])
    if tags & _INFLECTION_TAGS:
        for f in sense.get("form_of") or []:
            b = (f.get("word") or "").lower()
            if b and b != word:
                return b
        return None
    glosses = sense.get("glosses") or []
    if sense.get("alt_of") and not sense.get("form_of") and len(glosses) == 1:
        m = VARIANT_GLOSS_RE.match(str(glosses[0]).strip())
        if m and m.group(1).lower() != word:
            return m.group(1).lower()
    if sense.get("form_of") or sense.get("alt_of"):
        return None
    if len(glosses) != 1:
        return None  # a nested/extra gloss means this sense has its own meaning
    m = _INFLECTION_GLOSS_RE.match(str(glosses[0]).strip())
    if m:
        b = m.group(1).lower()
        if b != word:
            return b
    return None


def _listed_for_pos(word: str, pos: str, cefr_words: dict) -> bool:
    """True when the official list already gives this spelling a level for this pos.

    ``attached`` listed as an adjective must not also shield the verb, whose
    only sense is "past of attach" (card #162). A stub with no pos yet stays
    shielded whenever the spelling is listed at all."""
    if word not in cefr_words:
        return False
    if pos in (None, "", "unknown"):
        return True
    row = cefr_words[word]
    by_pos = row[1] if isinstance(row, (list, tuple)) and len(row) > 1 and isinstance(row[1], dict) else None
    if not by_pos:
        return True
    return _POS_LIST.get(pos, pos) in by_pos


def inflection_base(lemma: str, pos: str, entries: list[dict], cefr_words: dict) -> str | None:
    """tore → tear, fleeing → flee, tenants → tenant.

    Scoped to this lexeme's own part of speech once it has one: Kaikki
    entries are not ordered consistently (an adjective entry for "dappled"
    can come before the verb entry that is its only inflected sense), so
    looking at entries[0] picked the wrong one for roughly a third of real
    cases (問題回報 #217). A spelling that also has a substantive sense under
    this same pos — in the same Kaikki entry (found 創立) or a different one
    (lying 說謊的) — keeps its own entry rather than becoming a pointer, the
    #194 rule, now decided per pos+entry instead of by DB status. A stub not
    yet assigned a real pos (materialize.py's "unknown") has no own content
    to protect, so it is checked across every entry, as before."""
    if pos == "name":
        return None
    word = lemma.lower()
    own = entries if pos in (None, "", "unknown") else [e for e in entries if e.get("pos") == pos]
    if not own:
        return None
    bases: list[str] = []
    has_own_sense = False
    for e in own:
        if e.get("pos") == "name":
            continue  # empress (feminine of emperor) is a word of its own
        for s in e.get("senses") or []:
            b = _sense_base(s, word)
            if b:
                bases.append(b)
                continue
            tags = set(s.get("tags") or [])
            if not (s.get("form_of") or s.get("alt_of") or tags & _NON_SUBSTANTIVE):
                has_own_sense = True
    if not bases or _listed_for_pos(word, pos, cefr_words):
        return None
    # Mixed entry (a real sense plus a form-of sense): never redirect the
    # whole lexeme. An unknown stub still follows its listed base.
    if has_own_sense and (pos not in (None, "", "unknown")
                          or not any(b in cefr_words for b in bases)):
        return None
    return next((b for b in bases if b in cefr_words), bases[0])


def inclusion_flags(lemma: str, pos: str, entries: list[dict], cefr_words: dict) -> dict:
    """Rule codes (-> detail) for an entry that should not be a learner word."""
    out: dict[str, str] = {}
    word = lemma.lower()
    listed = word in cefr_words
    tokens = word.split()
    caps = len(tokens) == 1 and lemma.isupper() and 2 <= len(lemma) <= 5 and not listed
    # Title Case phrase / ALL CAPS / digit: brand, place, or product code.
    if (pos == "name" or re.search(r"\d", lemma) or caps
            or (len(tokens) >= 2 and not listed and lemma != word and lemma.istitle())
            or (len(tokens) == 1 and lemma != word and not listed
                and any(e.get("pos") == "name" for e in entries))):
        out["proper_or_brand"] = "專有名詞、品牌或含數字"
    abbr_tags = {"abbreviation", "initialism", "acronym"}
    tagged = [set(s.get("tags") or []) for _, s in _senses(entries)]
    if caps or (tagged and all(t & abbr_tags for t in tagged)):
        out["abbreviation"] = "縮寫"
    # Person names are pos=name in Kaikki. A common word sharing the spelling
    # keeps its entry when it has a substantive non-name sense.
    if (len(tokens) == 1 and not listed and any(e.get("pos") == "name" for e in entries)
            and not _substantive(entries) and "inflected_form" not in out
            and not inflection_base(lemma, pos, entries, cefr_words)):
        out["person_name"] = "人名"
    base = inflection_base(lemma, pos, entries, cefr_words)
    if base and (len(tokens) == 1 or not listed):
        # "coffee beans" / "fooling around": the whole phrase is only a form.
        out["inflected_form"] = base
    elif len(tokens) != 1 and not listed:
        if tokens[-1] in OBJECT_PRONOUNS or tokens[0] in OBJECT_PRONOUNS:
            out["phrase_fragment"] = "片語碎片（含受詞代名詞）"
        elif not entries and not re.search(r"\d", lemma):
            out["phrase_fragment"] = "片語碎片（字典查無）"
    return out


# --------------------------------------------------------------------- CEFR
def cefr_flags(lemma: str, pos: str, cefr: str | None, zipf: float | None,
               cefr_words: dict, entries: list[dict] | None = None) -> dict:
    out: dict[str, str] = {}
    lv = level_index(cefr)
    if lv is None:
        return out
    word = lemma.lower()
    row = cefr_words.get(word)
    if row:
        by_pos = row[1] or {}
        listed = by_pos.get(_POS_LIST.get(pos, pos)) or (min(by_pos.values(), key=LEVELS.index)
                                                         if by_pos else None)
        if listed in LEVELS and lv > LEVELS.index(listed) and (lv >= 4 or lv > LEVELS.index(listed) + 1):
            out["cefr_above_list"] = listed
    elif lv >= 4 and " " not in word:
        if zipf is not None and zipf >= 3.5:
            out["common_word_too_hard"] = "B2"
        else:
            for suf in DERIV_SUFFIXES:
                if word.endswith(suf) and len(word) > len(suf) + 2:
                    stem = word[: -len(suf)]
                    for b in {stem, stem[:-1] if stem[-1:] == stem[-2:-1] else stem, stem + "e"}:
                        r = cefr_words.get(b)
                        if r and r[1] and min(LEVELS.index(x) for x in r[1].values() if x in LEVELS) <= 1:
                            out["common_word_too_hard"] = f"由 {b} 衍生，建議 ≤B1"
                            break
                if out:
                    break
    if " " in word and lv <= 2 and pos in ("verb", "phrase", "adv"):
        out["idiom_too_easy"] = "B2"
    return out


# ------------------------------------------------------------------ senses
def sense_is_low(sense: dict, has_dictionary_before: bool, *, count_etymology: bool = True) -> bool:
    labels = {str(x).lower() for x in sense.get("labels") or []}
    if labels & LOW_SENSE_LABELS or "low_priority" in labels:
        return True
    # etymology-N: another word with the same spelling (phone 語音 = speech
    # sound) -- but only a demotion when some other sense in the entry is
    # not itself etymology-tagged (count_etymology=False from rank_senses
    # otherwise); 問題回報 #216: frame/wave/drink/... had every kaikki sense
    # filed under etymology-2+ once etymology-1's form-of-only senses were
    # dropped upstream, leaving the entry with no main sense at all.
    if count_etymology and any(x.startswith("etymology-") for x in labels):
        return True
    # Owner decision #84: an AI translation is a sub-sense description when a
    # dictionary translation of the word already exists.
    return bool(sense.get("native_ai")) and has_dictionary_before


def _label_low(sense: dict) -> bool:
    labels = {str(x).lower() for x in sense.get("labels") or []}
    return bool(labels & LOW_SENSE_LABELS) or "low_priority" in labels


def _etymology_tagged(sense: dict) -> bool:
    return any(str(x).lower().startswith("etymology-") for x in sense.get("labels") or [])


# Labels about register, not about time or rarity: a sense carrying only
# these is still a current meaning (meth 冰毒 is informal, stanch 使止血
# poetic) and is the first to come back when an entry has no main sense.
REGISTER_LABELS = {"informal", "colloquial", "slang", "humorous", "euphemistic", "poetic",
                   "nonstandard", "dialectal", "derogatory"}  # moron 白痴 is the meaning
# Never the meaning a card shows, even when nothing else has Chinese (chimp:
# the only translated sense was the offensive one).
NEVER_MAIN_LABELS = {"offensive", "vulgar"}


def _has_zh(s: dict) -> bool:
    return bool((s.get("native") or "").strip())


def rank_senses(senses: list[dict], low_keys: set[str] | None = None) -> list[dict]:
    """Main senses first (original order kept), low ones marked and after.

    When that leaves no main sense with Chinese, the card would show
    nothing, so senses come back in stages until one with Chinese is main
    (card #164) — a reviewed demotion (``low_keys``) never comes back:
      1. senses whose only low labels are about register (meth 冰毒 is
         informal; stanch's one translated sense is poetic), not senses
         filed under another etymology;
      2. etymology-N senses without a low label (monogram: the only
         non-etymology sense is obsolete, so 花押字 under etymology-3 is
         the meaning; frail the noun: 籮筐 rather than the dated 少女);
      3. any sense with Chinese (the translation worker fills the real main
         sense later, and this one goes back to low on its own).
    Offensive / vulgar / derogatory senses never come back. Etymology-N
    senses next to a plain main sense stay demoted."""
    low_keys = low_keys or set()
    count_etymology = any(not _etymology_tagged(s) for s in senses)
    seen_dict = False
    for i, s in enumerate(senses):
        # The first sense is not demoted for its etymology tag: sense_order
        # put it first (card #381: date 「a specific day」 and pen 「a tool
        # for writing」 are etymology-2/3, after the fruit and the enclosure).
        low = sense_is_low(s, seen_dict, count_etymology=count_etymology and i > 0) \
            or _sense_key(s) in low_keys
        s["priority"] = "low" if low else "main"
        if not low and s.get("native") and not s.get("native_ai"):
            seen_dict = True

    def main_with_zh() -> bool:
        return any(s["priority"] == "main" and _has_zh(s) for s in senses)

    def labels_of(s: dict) -> set[str]:
        return {str(x).lower() for x in s.get("labels") or []}

    stages = (
        lambda s: (labels_of(s) & LOW_SENSE_LABELS) <= REGISTER_LABELS
        and not (count_etymology and _etymology_tagged(s)),
        lambda s: _etymology_tagged(s) and not (labels_of(s) & LOW_SENSE_LABELS),
        lambda s: True,
    )
    for keep in stages:
        if main_with_zh():
            break
        for s in senses:
            if _has_zh(s) and _sense_key(s) not in low_keys and keep(s) \
                    and not labels_of(s) & (NEVER_MAIN_LABELS | {"low_priority"}):
                s["priority"] = "main"
    for s in senses:
        labels = s.setdefault("labels", [])
        if s["priority"] == "low" and "low_priority" not in labels:
            s["labels"] = [*labels, "low_priority"]
    # An entry with no main sense at all shows its first sense; never let that
    # be the offensive one (chimp: 黑猩猩 untranslated, 黑人 first).
    return sorted(senses, key=lambda s: (s["priority"] == "low", bool(labels_of(s) & NEVER_MAIN_LABELS)))


def _sense_key(s: dict) -> str:
    return str(s.get("id"))


# ---------------------------------------------------------------- examples
def inflections(lemma: str, forms: list[str] = ()) -> set[str]:
    w = lemma.lower()
    out = {w, w + "s", w + "es", w + "ed", w + "d", w + "ing", w + "er", w + "est", *map(str.lower, forms)}
    if w.endswith("e"):
        out |= {w[:-1] + "ing", w[:-1] + "ed", w[:-1] + "er", w[:-1] + "est"}
    if w.endswith("y"):
        out |= {w[:-1] + "ies", w[:-1] + "ied", w[:-1] + "ier", w[:-1] + "iest"}
    if len(w) > 2 and w[-1] not in "aeiouwxy" and w[-2] in "aeiou":
        out |= {w + w[-1] + "ed", w + w[-1] + "ing", w + w[-1] + "er"}
    if w.endswith("ed"):
        out |= {w[:-2], w[:-1], w[:-2] + "ing", w[:-2] + "s"}
    return out


# Keep in sync with app/lib/services/learning_content.dart exampleIsCharged.
# Headword exemption: teaching "church" may use a sentence about a church.
_CHARGED_SEX = re.compile(
    r"\b(?:sex(?:es|ual\w*|y)?|nude|naked|porn|orgasm|prostitute|whore|slut|rape|rapist|"
    r"penis|vagina|erotic|intercourse|adultery|adulter\w*|fornicat\w*|brothel|"
    r"masturbat\w*|condom|genital)\b", re.I)
_CHARGED_VIOLENCE = re.compile(
    r"\b(?:murder(?:ed|ing|s|er|ers|ous)?|kill(?:ed|ing|s|er|ers)?|"
    r"shoot(?:ing|s|er|ers)?|bullet|guns?|stab(?:bed|bing|s)?|bombs?|suicide|torture)\b",
    re.I)
_CHARGED_RELIGION = re.compile(
    r"\b(?:god|jesus|christ|allah|bible|quran|koran|mosque|church|priest|buddha|"
    r"buddhist|worship|prayer|scripture|gospel|heaven|hell)\b", re.I)
_CHARGED_POLITICS = re.compile(
    r"\b(?:migration|immigrant|immigration|refugee|asylum|abortion|bolshevik|"
    r"communist|communism|nazi|hitler|genocide|trump|biden|feminis\w*|"
    r"parliament|dictator\w*|propaganda)\b", re.I)
_CHARGED_STANCE_NOUN = re.compile(
    r"\b(?:woman|women|migration|immigrants?|abortion|gender|pronouns?)\b", re.I)
_CHARGED_BAN = re.compile(r"\b(?:outlaw(?:ed|ing|s)?|ban(?:ned|ning)?)\b", re.I)
_CHARGED_SOFT = re.compile(
    r"\b(?:oh my god|thank god|for god'?s sake|god knows|what the hell|the hell)\b", re.I)
_STANCE_LEMMAS = {"woman", "women", "migration", "immigrant", "abortion", "gender", "pronoun"}


def _charged_foreign(pattern: re.Pattern, source: str, lemma: str) -> bool:
    low = (lemma or "").lower()
    for match in pattern.finditer(source or ""):
        hit = match.group(0).lower()
        if low and (hit.startswith(low) or low.startswith(hit)):
            continue
        return True
    return False


def example_is_charged(text: str, lemma: str = "") -> str | None:
    """Politics, religion, violence or sex that is not the headword itself.

    Learning cards sort these after a neutral sentence (問題回報 #254).
    Returns the category, or None. Nothing is deleted.
    """
    raw = text or ""
    if _charged_foreign(_CHARGED_SEX, raw, lemma):
        return "sex"
    if _charged_foreign(_CHARGED_VIOLENCE, raw, lemma):
        return "violence"
    if _charged_foreign(_CHARGED_POLITICS, raw, lemma):
        return "politics"
    if _charged_foreign(_CHARGED_RELIGION, _CHARGED_SOFT.sub(" ", raw), lemma):
        return "religion"
    if (lemma or "").lower() not in _STANCE_LEMMAS and _CHARGED_STANCE_NOUN.search(raw) \
            and _CHARGED_BAN.search(raw):
        return "politics"
    return None


def example_flags(text: str, lemma: str, pos: str, forms: list[str] = ()) -> list[str]:
    flags = []
    t = (text or "").strip()
    # A trailing quote mark (closing a quoted word) is not part of the word
    # itself, only an internal apostrophe/hyphen is ('don't, 'Tell-tale').
    words = re.findall(r"[A-Za-z]+(?:['\-][A-Za-z]+)*", t)
    low = []
    for x in words:
        x = re.sub(r"'s$", "", x.lower())
        low.append(x)
        if "-" in x:
            low.extend(x.split("-"))  # "tell-tale" also counts as containing "tale"
    forms_set = inflections(lemma, forms)
    if " " in lemma:
        first = lemma.split()[0].lower()
        if lemma.lower() not in t.lower() and not any(f in low for f in inflections(first)):
            flags.append("missing_lemma")
    elif not any(x in forms_set for x in low):
        flags.append("missing_lemma")
    if len(words) < 3 or not re.match(r"[\"'“A-Z0-9]", t) or not re.search(r"[.!?。\"'”]$", t):
        flags.append("not_sentence")
    w = re.escape(lemma.lower())
    if pos == "adj" and lemma.lower().endswith("ed") and re.search(
            rf"\b(it|he|she|they|this|that|which|everything|all)\s+{w}\s+(on|upon)\b", t.lower()):
        flags.append("pos_mismatch")
    if any(n in words for n in ODD_NAMES):
        flags.append("odd_name")
    if example_is_charged(t, lemma):
        flags.append("charged")
    return flags


def example_reject_reason(text: str, lemma: str, pos: str, forms: list[str] = ()) -> str | None:
    """Why a sentence must not be selected. Odd names are kept out of this:
    they only sort later (example_preference)."""
    flags = set(example_flags(text, lemma, pos, forms))
    if "not_sentence" in flags:
        return "不是完整句"
    if "missing_lemma" in flags:
        return "例句沒有用到這個字或可信詞形"
    if "pos_mismatch" in flags:
        return "詞性不合"
    return None


def example_preference(text: str) -> tuple:
    """Sort key, lower first: a complete ordinary sentence beats a Tatoeba
    placeholder name (Ziri, Mennad, Baya) and a very long or very short line."""
    words = re.findall(r"[A-Za-z]+(?:['\-][A-Za-z]+)*", text or "")
    odd = 1 if any(name in words for name in ODD_NAMES) else 0
    return (odd, abs(len(text or "") - 45))


def bind_example_sense_ex(text: str, senses: list[dict], forms: list[str] = (),
                          fallback_main: bool = False) -> tuple[dict | None, str]:
    """Like ``bind_example_sense`` but also says how the sense was chosen.

    Evidence is ``gloss`` (a gloss shares a content word and beats every
    rival), ``single`` (only one ordinary sense), ``fallback`` (the first
    sense taken only because ``fallback_main`` allowed it: nothing in the
    sentence points at it, so a different sense may be the real one; card
    #354) or ``none`` (no sense bound).
    """
    skip = _STOP | {f.lower() for f in forms} | {w.lower() for w in (forms or [])}
    words = set(re.findall(r"[a-z]+", (text or "").lower())) - skip
    ranked = []
    for sense in senses:
        labels = {str(label).lower() for label in (sense.get("labels") or [])}
        if labels & {"obsolete", "archaic", "dated", "rare", "alt-of", "form-of"}:
            continue
        gloss = set(re.findall(r"[a-z]+", (sense.get("gloss") or "").lower())) - skip
        ranked.append((len(words & gloss), sense.get("ordinal") or 0, sense))
    if not ranked:
        return None, "none"
    ranked.sort(key=lambda row: (-row[0], row[1]))
    score, _ordinal, best = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else -1
    if score >= 1 and score > second:
        return best, "gloss"
    if len(ranked) == 1:
        return best, "single"
    if fallback_main:
        return best, "fallback"
    return None, "none"


def bind_example_sense(text: str, senses: list[dict], forms: list[str] = (),
                       fallback_main: bool = False) -> dict | None:
    """The sense this sentence illustrates, or None when it matches none.

    ``senses`` items need ``sense_key`` and may carry ``gloss``, ``labels``
    and ``ordinal``. A gloss that shares a content word wins; a single
    ordinary sense is used when the sentence does not point at a rival.
    """
    return bind_example_sense_ex(text, senses, forms, fallback_main)[0]


def rank_examples(examples: list[dict], lemma: str, pos: str, forms: list[str],
                  low_sense_ids: set) -> list[dict]:
    for e in examples:
        f = example_flags(e.get("text") or "", lemma, pos, forms)
        if e.get("sense_id") in low_sense_ids:
            f.append("low_priority_sense")
        e["quality_flags"] = f
    bad = {"missing_lemma", "not_sentence", "pos_mismatch", "low_priority_sense", "rejected"}
    # Charged sentences stay in the pack; a neutral one is offered first.
    return sorted(examples, key=lambda e: (bool(set(e["quality_flags"]) & bad),
                                           "charged" in e["quality_flags"],
                                           "odd_name" in e["quality_flags"]))


# --------------------------------------------------------------- pack hook
def load_json(name: str) -> dict:
    p = QUALITY_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def apply_pack(pack: dict, entry_flags: dict | None = None, overrides: dict | None = None) -> None:
    """Rank senses/examples, attach lint flags and reviewed overrides."""
    entry_flags = load_json("entry_flags.json") if entry_flags is None else entry_flags
    overrides = load_json("overrides.json") if overrides is None else overrides
    low_ids = {str(i) for i in overrides.get("low_priority_senses", [])}
    rejected_ex = set(overrides.get("rejected_examples", []))
    added = overrides.get("examples", {})
    for lx in pack.get("lexemes", []):
        key = f'{lx["normalized"]}|{lx["pos"]}'
        if key in entry_flags:
            lx["quality_flags"] = entry_flags[key]
        if lx.get("status") != "full":
            continue
        lx["senses"] = rank_senses(lx.get("senses") or [], low_ids)
        low_sense = {s["id"] for s in lx["senses"] if s["priority"] == "low"}
        exs = [dict(e) for e in added.get(key, [])] + list(lx.get("examples") or [])
        forms = [f.get("form") for f in lx.get("forms") or [] if f.get("form")]
        lx["examples"] = rank_examples(exs, lx["lemma"], lx["pos"], forms, low_sense)
        vulgar_ex = {int(i) for i in overrides.get("vulgar_examples", [])}
        for e in lx["examples"]:
            if e.get("id") in rejected_ex:
                e["quality_flags"].append("rejected")
            if e.get("id") in vulgar_ex and "vulgar" not in e["quality_flags"]:
                e["quality_flags"].append("vulgar")
        lx["examples"].sort(key=lambda e: "rejected" in e["quality_flags"])


# ------------------------------------------------- decisions (#191, owner)
def apply_decisions(pack: dict, decisions: dict | None = None) -> dict:
    """Owner decision 問題回報 #191 (2026-10-14), from quality/decisions.json
    written by tools/apply_quality_decisions.py:

    * redirect   {id: lemma_id}: an inflected form (tore) is a pointer to its
      lemma (tear): no CEFR, ``redirect_to`` set, listed in pack redirects;
      its pictures and examples are merged into the lemma's first sense.
    * strip_cefr [id]: fragments, names, brands, abbreviations: CEFR None.
    * set_cefr   {id: level}: a wrong level corrected to the rule's suggestion.

    Runs after rank_usages/assign_cards (which would otherwise reset them);
    idempotent. Returns per-action counts."""
    decisions = load_json("decisions.json") if decisions is None else decisions
    redirect = {int(k): int(v) for k, v in (decisions.get("redirect") or {}).items()}
    strip = {int(x) for x in decisions.get("strip_cefr") or []}
    set_cefr = {int(k): v for k, v in (decisions.get("set_cefr") or {}).items()}
    by_id = {lx["id"]: lx for lx in pack.get("lexemes", [])}
    counts = {"redirect": 0, "strip_cefr": 0, "set_cefr": 0, "merged_images": 0, "merged_examples": 0}
    redirects = pack.setdefault("redirects", {})
    for lid, level in set_cefr.items():
        lx = by_id.get(lid)
        if lx and lid not in redirect and lid not in strip:
            if lx.get("cefr") != level:
                lx.setdefault("cefr_before_rule", lx.get("cefr"))
            lx["cefr"], lx["cefr_source"] = level, "quality_rule"
            counts["set_cefr"] += 1
    for lid in strip:
        lx = by_id.get(lid)
        if lx and lid not in redirect:
            if lx.get("cefr") is not None:
                lx.setdefault("cefr_before_rule", lx.get("cefr"))
            lx["cefr"], lx["cefr_source"] = None, "quality_excluded"
            counts["strip_cefr"] += 1
    for lid, base_id in redirect.items():
        lx, base = by_id.get(lid), by_id.get(base_id)
        if not lx or not base or lid == base_id:
            continue
        if lx.get("cefr") is not None:
            lx.setdefault("cefr_before_rule", lx.get("cefr"))
        lx["cefr"], lx["cefr_source"] = None, "quality_redirect"
        lx["redirect_to"], lx["card"] = base_id, base["normalized"]
        lx["rare_usage"] = True
        redirects[str(lid)] = base_id
        counts["redirect"] += 1
        if base.get("status") != "full" or lx.get("status") != "full":
            continue
        # Merge what the form had into the lemma (pictures, checked examples).
        target = (base.get("senses") or [None])[0]
        if target is not None:
            have = {i.get("path") for s in base["senses"] for i in s.get("images") or []}
            for s in lx.get("senses") or []:
                for img in s.get("images") or []:
                    if img.get("path") not in have:
                        target.setdefault("images", []).append({**img, "merged_from": lx["lemma"]})
                        have.add(img.get("path"))
                        counts["merged_images"] += 1
        texts = {e.get("text") for e in base.get("examples") or []}
        for e in lx.get("examples") or []:
            if e.get("text") not in texts and not set(e.get("quality_flags") or []) & {
                    "missing_lemma", "not_sentence", "pos_mismatch", "rejected"}:
                base.setdefault("examples", []).append({**e, "merged_from": lx["lemma"],
                                                        "sense_id": None})
                texts.add(e.get("text"))
                counts["merged_examples"] += 1
    return counts

# --------------------------------------------- photo tag senses (#195)
_STOP = set("a an the of or and to in on for with by from as at is are be that this which "
            "any its it into such other used use usually especially something someone one "
            "etc e g not no than more less very".split())
CONCRETE = set("object device apparatus structure material physical visible flat picture image "
               "colour color screen shows surface made piece plant leaf leaves vessel container "
               "dish worn wear walls roof frame tool metal wood glass cloth fabric fibers "
               "electronic display rectangular paper plastic receive transmit scenery rear "
               "behind subject vascular bundle message words bearing".split())
ABSTRACT = set("act process faculty fact omen heritage past history information synonym style "
               "tendency topic discussion previous life ancestors relatives colleagues employees "
               "game argument resource event events agenda permit category".split())
PHOTO_CONTEXT = {"photo", "picture", "image", "scene", "visible", "object", "physical"}
# Specialist domains a photo of everyday things rarely means (window 視窗,
# ornament 裝飾音, texture 貼圖, transparent 公開, centered 心靜平和).
DOMAIN = set("computer computing software program programming user desktop "
             "data file music musical note chord melody mathematics mathematical chemistry "
             "biology law legal sport cricket baseball grammar linguistics emotionally mental "
             "public openly honest frank genre rendering pixel polygon phonology speech".split())


def tokens(text: str | None) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if w in _STOP or len(w) < 3:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                if len(w) > 4 and w[-1] == w[-2]:
                    w = w[:-1]  # transmitting -> transmit
                break
        out.add(w)
    return out


def choose_sense(candidates: list[dict], context: set[str], current_id=None,
                 tag_pos: str | None = None) -> tuple[dict | None, float, float]:
    """The sense of a photo tag that fits the photo: candidates are dicts
    {id, lexeme_pos, ordinal, definition, native, native_ai, labels, low}.
    Only senses with Chinese and not low priority compete (fallback: any sense
    with Chinese). Score = context overlap with the definition, concreteness
    (a photo shows things), dictionary order and translation source, the
    tagger's part of speech. Returns (best, best score, runner-up score)."""
    ok = [c for c in candidates if (c.get("native") or "").strip() and not c.get("low")]
    if not ok:
        ok = [c for c in candidates if (c.get("native") or "").strip()]
    if not ok:
        return None, 0.0, 0.0
    ctx = context | PHOTO_CONTEXT
    pos = {"adjective": "adj", "adverb": "adv"}.get(tag_pos or "", tag_pos)

    def score(c):
        d = tokens(c.get("definition"))
        s = 3.0 * len(d & ctx) + 1.5 * len(d & CONCRETE) - 2.0 * len(d & ABSTRACT)
        s -= 4.0 * len(d & DOMAIN)
        s -= 0.25 * (c.get("ordinal") or 0)
        s += 1.0 if not c.get("ordinal") else 0.0  # the dictionary's main sense
        s += 0.5 if not c.get("native_ai") else 0.0
        if pos and c.get("lexeme_pos") == pos:
            s += 1.0
        if c.get("id") == current_id:
            s += 0.3  # stability: keep a fitting binding
        return s

    ranked = sorted(ok, key=lambda c: (-score(c), c.get("ordinal") or 0))
    best = ranked[0]
    return best, score(best), (score(ranked[1]) if len(ranked) > 1 else float("-inf"))


def _publishable(senses: list[dict]) -> list[dict]:
    return [s for s in senses if (s.get("native") or "").strip() and s.get("priority") != "low"]


def photo_sense_candidates(lexemes: list[dict]) -> list[dict]:
    """choose_sense candidates for every publishable sense of ``lexemes``,
    carrying the lexeme id so a tag can move to a sister part of speech."""
    out = []
    for lx in lexemes:
        for n, se in enumerate(lx.get("senses") or []):
            if (se.get("native") or "").strip() and se.get("priority") != "low":
                out.append({"id": se["id"], "lexeme_id": lx["id"], "lexeme_pos": lx.get("pos"),
                            "ordinal": n, "definition": se.get("definition") or "",
                            "native": se.get("native"), "native_ai": se.get("native_ai"),
                            "labels": se.get("labels") or [], "low": False})
    return out


def fix_catalog_senses(pack: dict) -> int:
    """Pack-time guard (#195): a photo tag never shows a low-priority or
    Chinese-less sense. Tags on a redirected lexeme follow the redirect.

    Card #164: the replacement is chosen the way a fresh tag is — by the
    other words on the same photo, concreteness and the dictionary order
    (:func:`choose_sense`), not the lexeme's first main sense. When the
    tag's lexeme has no publishable sense at all (brick the adjective 極冷,
    natural the adverb), the sister parts of speech of the same spelling
    compete too, the main usage preferred, and the tag and its label move
    to that lexeme (``lexeme_id_before`` kept). Idempotent."""
    by_id = {lx["id"]: lx for lx in pack.get("lexemes", [])}
    redirects = {int(k): v for k, v in (pack.get("redirects") or {}).items()}
    sisters: dict[str, list[dict]] = {}
    for lx in pack.get("lexemes", []):
        if lx.get("status", "full") == "full" and lx.get("normalized"):
            sisters.setdefault(lx["normalized"], []).append(lx)
    changed = 0
    for im in pack.get("catalog_images") or []:
        for coll in (im.get("tags") or [], im.get("labels") or []):
            for t in coll:
                lid = t.get("lexeme_id")
                # Card #331: never move a tag onto a stub (faded -> fade the
                # noun); strip_stubs drops that redirect anyway.
                target = by_id.get(redirects.get(lid))
                if target and target.get("status", "full") == "full":
                    t["lexeme_id"] = target["id"]
        tags = im.get("tags") or []
        for t in tags:
            lx = by_id.get(t.get("lexeme_id")) or {}
            senses = lx.get("senses") or []
            cur = next((s for s in senses if s.get("id") == t.get("sense_id")), None)
            if cur and (cur.get("native") or "").strip() and cur.get("priority") != "low":
                continue
            tagged_here = {o.get("lexeme_id") for o in tags if o is not t}
            pool = [lx] if _publishable(senses) else sorted(
                (s for s in sisters.get(lx.get("normalized") or "", [])
                 if s is not lx and s["id"] not in tagged_here),
                key=lambda s: (s.get("usage_rank") if s.get("usage_rank") is not None else 9, s["id"]))
            cands = photo_sense_candidates(pool)
            if not cands:
                # Nothing publishable anywhere under this spelling: keep the
                # tag on a sense with Chinese so the album still names it.
                best = next((s for s in senses if (s.get("native") or "").strip()), None)
                best_lx = lx if best else None
            else:
                context = set()
                for o in tags:
                    other = by_id.get(o.get("lexeme_id"))
                    if other and other is not lx:
                        context |= tokens(other.get("lemma"))
                tag_pos = pool[0].get("pos") if pool and pool[0] is not lx else lx.get("pos")
                best, _, _ = choose_sense(cands, context, t.get("sense_id"), tag_pos)
                best_lx = by_id.get(best["lexeme_id"]) if best else None
            if best and best.get("id") != t.get("sense_id"):
                t.setdefault("sense_id_before", t.get("sense_id"))
                t["sense_id"], t["sense_fallback"] = best["id"], True
                if best_lx is not None and best_lx["id"] != t.get("lexeme_id"):
                    t.setdefault("lexeme_id_before", t.get("lexeme_id"))
                    for lb in im.get("labels") or []:
                        if lb.get("lexeme_id") == t["lexeme_id"]:
                            lb["lexeme_id"] = best_lx["id"]
                            lb["word"], lb["pos"] = best_lx.get("lemma"), best_lx.get("pos")
                    t["lexeme_id"] = best_lx["id"]
                changed += 1
        # P2: a photo tag's level is the card's level (after the pack's
        # CEFR decisions), never a separate value.
        for coll in (im.get("tags") or [], im.get("labels") or []):
            for t in coll:
                lx = by_id.get(t.get("lexeme_id"))
                if not lx:
                    continue
                if lx.get("cefr"):
                    t["cefr"] = lx["cefr"]
                    t["cefr_source"] = ("estimate" if lx.get("cefr_source") in
                                        ("frequency_estimate", "estimate", "local_calc",
                                         "ai_reviewed") else "cefr-j")
                else:
                    t.pop("cefr", None)
                    t.pop("cefr_source", None)
    return changed