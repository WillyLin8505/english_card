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


def inflection_base(lemma: str, entries: list[dict], cefr_words: dict) -> str | None:
    """tore → tear, fleeing → flee, tenants → tenant."""
    word = lemma.lower()
    bases = []
    for pos, s in _senses(entries):
        if pos == "name":
            continue
        if not set(s.get("tags") or []) & _INFLECTION_TAGS:
            continue  # empress (feminine of emperor) is a word of its own
        for f in s.get("form_of") or []:
            b = (f.get("word") or "").lower()
            if b and b != word:
                bases.append(b)
    if not bases or word in cefr_words:
        return None
    if not _substantive(entries) or any(b in cefr_words for b in bases):
        return next((b for b in bases if b in cefr_words), bases[0])
    first = entries[0]["senses"][0] if entries and entries[0].get("senses") else {}
    if first.get("form_of") and set(first.get("tags") or []) & _INFLECTION_TAGS:
        return bases[0]
    return None


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
            and not inflection_base(lemma, entries, cefr_words)):
        out["person_name"] = "人名"
    if len(tokens) == 1:
        base = inflection_base(lemma, entries, cefr_words)
        if base:
            out["inflected_form"] = base
    elif not listed:
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
def sense_is_low(sense: dict, has_dictionary_before: bool) -> bool:
    labels = {str(x).lower() for x in sense.get("labels") or []}
    if labels & LOW_SENSE_LABELS or "low_priority" in labels:
        return True
    # Owner decision #84: an AI translation is a sub-sense description when a
    # dictionary translation of the word already exists.
    return bool(sense.get("native_ai")) and has_dictionary_before


def rank_senses(senses: list[dict], low_keys: set[str] | None = None) -> list[dict]:
    """Main senses first (original order kept), low ones marked and after."""
    seen_dict = False
    for s in senses:
        low = sense_is_low(s, seen_dict) or _sense_key(s) in (low_keys or set())
        s["priority"] = "low" if low else "main"
        if low and "low_priority" not in s.setdefault("labels", []):
            s["labels"] = [*s["labels"], "low_priority"]
        if not low and s.get("native") and not s.get("native_ai"):
            seen_dict = True
    return sorted(senses, key=lambda s: s["priority"] == "low")


def _sense_key(s: dict) -> str:
    return str(s.get("id"))


# ---------------------------------------------------------------- examples
def inflections(lemma: str, forms: list[str] = ()) -> set[str]:
    w = lemma.lower()
    out = {w, w + "s", w + "es", w + "ed", w + "d", w + "ing", w + "er", w + "est", *map(str.lower, forms)}
    if w.endswith("e"):
        out |= {w[:-1] + "ing", w[:-1] + "ed"}
    if w.endswith("y"):
        out |= {w[:-1] + "ies", w[:-1] + "ied", w[:-1] + "ier", w[:-1] + "iest"}
    if len(w) > 2 and w[-1] not in "aeiouwxy" and w[-2] in "aeiou":
        out |= {w + w[-1] + "ed", w + w[-1] + "ing", w + w[-1] + "er"}
    if w.endswith("ed"):
        out |= {w[:-2], w[:-1], w[:-2] + "ing", w[:-2] + "s"}
    return out


def example_flags(text: str, lemma: str, pos: str, forms: list[str] = ()) -> list[str]:
    flags = []
    t = (text or "").strip()
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", t)
    low = [re.sub(r"'s$", "", x.lower()) for x in words]
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
    return flags


def rank_examples(examples: list[dict], lemma: str, pos: str, forms: list[str],
                  low_sense_ids: set) -> list[dict]:
    for e in examples:
        f = example_flags(e.get("text") or "", lemma, pos, forms)
        if e.get("sense_id") in low_sense_ids:
            f.append("low_priority_sense")
        e["quality_flags"] = f
    bad = {"missing_lemma", "not_sentence", "pos_mismatch", "low_priority_sense", "rejected"}
    return sorted(examples, key=lambda e: (bool(set(e["quality_flags"]) & bad),
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
        for e in lx["examples"]:
            if e.get("id") in rejected_ex:
                e["quality_flags"].append("rejected")
        lx["examples"].sort(key=lambda e: "rejected" in e["quality_flags"])
