"""The order of a word's senses in the database (card #352, 問題回報 #350).

Kaikki lists senses in the Wiktionary entry's order, which is etymological
or historical, not by current use: assiette's 「plate」 is the fifth sense,
after an archaic 「manner of being seated」 and three domain senses (the
horse-racing seat, the nautical trim, the accounting basis). The DB ordinal
drives the picture need (first two senses), the French pack's picture
labels (serve_app.meaning_index) and the first sense on a card, so
materialize() orders the definition items with order_senses():

  1. current senses before out-of-use ones (archaic, obsolete, dated, rare,
     historical, dialectal, nonstandard … and the never-main vulgar labels —
     register labels such as informal or slang do not demote: gosse 「child,
     kid」 stays before 「testicle」); quality.rank_senses does the same in
     the pack;
  2. for a non-English headword, a domain-tagged sense (Kaikki topics or the
     figuratively tag) comes after the plain senses unless English
     Wiktionary lists the headword as a translation of one of its English
     words (face 「face (anatomy)」 and pied 「foot」 stay first; assiette's
     seat / trim / basis go after dish and plate);
  3. otherwise the dictionary's order (stable sort).

Items carry their Kaikki topics since this card; older items are looked up
in the Kaikki index by gloss.
"""
from __future__ import annotations

from functools import lru_cache

from .quality import LOW_SENSE_LABELS, NEVER_MAIN_LABELS, REGISTER_LABELS

# Labels about time, rarity or form, not register.
OUT_OF_USE_LABELS = (LOW_SENSE_LABELS - REGISTER_LABELS) | NEVER_MAIN_LABELS | {
    "low_priority", "nonstandard", "dialectal", "misspelling", "alternative",
    "pronunciation-spelling", "eye-dialect"}
DOMAIN_TAGS = {"figuratively", "figurative"}


def _labels(item: dict) -> set[str]:
    return {str(x).lower() for x in item.get("labels") or []}


def is_out_of_use(item: dict) -> bool:
    """An out-of-use or never-main sense: labelled so, or adopted at the
    adapter's low confidence (Kaikki LOW_TAGS such as dialectal that are
    not kept as labels)."""
    if _labels(item) & OUT_OF_USE_LABELS:
        return True
    try:
        return float(item.get("confidence", 1.0)) < 1.0 and item.get("source", "kaikki") == "kaikki"
    except (TypeError, ValueError):
        return False


def _kaikki_pos(e: dict) -> str | None:
    from .adapters.kaikki import POS
    return POS.get(str(e.get("pos") or ""))


@lru_cache(maxsize=100_000)
def kaikki_sense_info(target: str, lemma: str, pos: str, gloss: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(topics, tags) of the Kaikki sense whose first gloss is ``gloss`` —
    for items stored before this card, which carry neither topics nor the
    tags outside LABEL_TAGS (historical)."""
    from . import kaikki_index
    for e in kaikki_index.lookup(target, lemma) or []:
        if str(e.get("word", "")) != lemma or _kaikki_pos(e) != pos:
            continue
        for s in e.get("senses") or []:
            if (s.get("glosses") or [""])[0].strip() == gloss:
                return (tuple(sorted(set(s.get("topics") or []))),
                        tuple(sorted(str(t).lower() for t in s.get("tags") or [])))
    return (), ()


def topics_of(target: str, lemma: str, pos: str, gloss: str) -> tuple[str, ...]:
    return kaikki_sense_info(target, lemma, pos, gloss)[0]


def tags_of(target: str, lemma: str, pos: str, gloss: str) -> tuple[str, ...]:
    return kaikki_sense_info(target, lemma, pos, gloss)[1]


def _strip_reflexive(word: str) -> str:
    w = word.strip().lower()
    for p in ("se ", "s'", "s’"):
        if w.startswith(p):
            return w[len(p):].strip()
    return w


@lru_cache(maxsize=200_000)
def english_translates_to(english: str, pos: str, target: str, lemma: str) -> bool | None:
    """Does English Wiktionary list ``lemma`` among the ``target``-language
    translations of the English word (same part of speech)? None when the
    English word has no translation into that language at all (optics has
    none in French: nothing is learnt about optique)."""
    from . import kaikki_index
    from .adapters.kaikki import LANG_CODE
    code = LANG_CODE.get(target, target)
    want = lemma.strip().lower()
    seen = False
    for e in kaikki_index.lookup("en", english) or []:
        if str(e.get("word", "")).lower() != english or _kaikki_pos(e) != pos:
            continue
        trs = list(e.get("translations") or [])
        for s in e.get("senses") or []:
            trs += list(s.get("translations") or [])
        for t in trs:
            if t.get("lang_code") == code and t.get("word"):
                seen = True
                w = str(t["word"]).strip().lower()
                if w == want or (pos == "verb" and _strip_reflexive(w) == want):
                    return True
    return False if seen else None


def confirmed_by_english(item: dict, target: str, lemma: str) -> bool | None:
    """True: English Wiktionary lists the headword as a translation of one
    of the gloss's English words (or of a multiword term's head: 「geometric
    angle」 → angle). False: it lists other translations but not this word.
    None: no evidence either way."""
    from .images import english_label_terms
    pos = str(item.get("pos") or "")
    terms = []
    for t in english_label_terms(item.get("gloss")):
        terms.append(t)
        if " " in t:
            terms.append(t.rsplit(" ", 1)[-1])
    want = lemma.strip().lower()
    # A cognate gloss word is its own evidence (parti 「party」: English
    # Wiktionary files the French translation under political party).
    if any(_cognate(t, want) for t in terms):
        return True
    found = [english_translates_to(t, pos, target, lemma) for t in terms]
    if any(found):
        return True
    return False if any(f is False for f in found) else None


def _cognate(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < 4 or abs(len(a) - len(b)) > 1:
        return False
    # one edit (party / parti, lion / lion, scénario / scenario)
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i + 1:] == b[i:] or a[i:] == b[i + 1:]


def sense_rank(item: dict, target: str, lemma: str) -> int:
    """0 plain current sense · 1 unconfirmed domain sense · 2 out of use."""
    if is_out_of_use(item):
        return 2
    pos, gloss = str(item.get("pos") or ""), str(item.get("gloss") or "")
    topics = item.get("topics")
    if topics is None and set(tags_of(target, lemma, pos, gloss)) & OUT_OF_USE_LABELS:
        return 2  # historical etc.: a tag the stored item did not keep
    if target == "en":
        return 0
    if topics is None:
        topics = topics_of(target, lemma, pos, gloss)
    if (topics or _labels(item) & DOMAIN_TAGS) and confirmed_by_english(item, target, lemma) is False:
        return 1
    return 0


def order_senses(items: list[dict], target: str, lemma: str) -> list[dict]:
    """The definition items in the order their senses get ordinals."""
    return sorted(items, key=lambda it: sense_rank(it, target, lemma))
