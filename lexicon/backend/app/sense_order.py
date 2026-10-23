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
  3. hand-reviewed common senses first (PREFERRED_GLOSSES for French,
     quality/en_common_senses.json for English — card #381: train's first
     Kaikki sense is a dress's train);
  4. for English, the etymology whose current senses have the largest
     Wiktionary translation tables first (card #539: second 「unit of
     time」 before 「number two in a series」, down 「feathers」 before 「a
     negative aspect」) — Kaikki's etymology-N label no longer demotes an
     established sense (adapters/kaikki.py established_sense);
  5. otherwise the dictionary's order (stable sort).

Items carry their Kaikki topics since this card; older items are looked up
in the Kaikki index by gloss.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .quality import LOW_SENSE_LABELS, NEVER_MAIN_LABELS, REGISTER_LABELS

# Labels about time, rarity or form, not register.
OUT_OF_USE_LABELS = (LOW_SENSE_LABELS - REGISTER_LABELS) | NEVER_MAIN_LABELS | {
    "low_priority", "nonstandard", "dialectal", "misspelling", "alternative",
    "pronunciation-spelling", "eye-dialect"}
DOMAIN_TAGS = {"figuratively", "figurative"}
# Topics that do not make a sense a domain sense: body parts and food are
# core learner vocabulary (poitrine 「chest」, foie 「liver」, recette 「recipe」).
EVERYDAY_TOPICS = {"anatomy", "medicine", "sciences", "pathology", "food", "cooking",
                   "lifestyle", "clothing", "fashion", "family"}


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
def kaikki_sense_info(target: str, lemma: str, pos: str, gloss: str) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """(topics, tags, etymology number) of the Kaikki sense whose first
    gloss is ``gloss`` — for items stored before this card, which carry
    neither topics nor the tags outside LABEL_TAGS (historical)."""
    from . import kaikki_index
    for e in kaikki_index.lookup(target, lemma) or []:
        if str(e.get("word", "")) != lemma or _kaikki_pos(e) != pos:
            continue
        for s in e.get("senses") or []:
            if (s.get("glosses") or [""])[0].strip() == gloss:
                return (tuple(sorted(set(s.get("topics") or []))),
                        tuple(sorted(str(t).lower() for t in s.get("tags") or [])),
                        str(e.get("etymology_number") or "1"))
    return (), (), ""


@lru_cache(maxsize=50_000)
def etymology_weights(target: str, lemma: str, pos: str) -> tuple[tuple[str, int], ...]:
    """((etymology number, weight), …) of the Kaikki entries of ``lemma``
    in ``pos``: the weight is the sum of the translation-table sizes of the
    etymology's current senses — how established its meanings are (card
    #539: second's 「unit of time」 etymology outweighs 「number two」's)."""
    from . import kaikki_index
    from .adapters.kaikki import LOW_TAGS, translation_counts
    weights: dict[str, int] = {}
    for e in kaikki_index.lookup(target, lemma) or []:
        if str(e.get("word", "")) != lemma or _kaikki_pos(e) != pos:
            continue
        ety = str(e.get("etymology_number") or "1")
        weights.setdefault(ety, 0)
        for s, n in zip(e.get("senses") or [], translation_counts(e)):
            tags = {str(t).lower() for t in s.get("tags") or []}
            if not tags & (OUT_OF_USE_LABELS | LOW_TAGS):
                weights[ety] += n
    return tuple(weights.items())


def _etymology_group_rank(item: dict, target: str, lemma: str) -> int:
    """English only: the rank of the item's etymology among the headword's
    etymologies in that part of speech, heaviest translation evidence
    first; Wiktionary's order breaks ties. 0 when the word has one
    etymology or the sense is not found in the index."""
    if target != "en":
        return 0
    pos, gloss = str(item.get("pos") or ""), str(item.get("gloss") or "")
    weights = dict(etymology_weights(target, lemma, pos))
    if len(weights) < 2:
        return 0
    ety = kaikki_sense_info(target, lemma, pos, gloss)[2]
    if ety not in weights:
        return 0
    order = sorted(weights, key=lambda k: (-weights[k], int(k) if k.isdigit() else 0))
    return order.index(ety)


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

    def is_lemma(t) -> bool:
        w = str(t.get("word") or "").strip().lower()
        return w == want or (pos == "verb" and _strip_reflexive(w) == want)

    for e in kaikki_index.lookup("en", english) or []:
        if str(e.get("word", "")).lower() != english or _kaikki_pos(e) != pos:
            continue
        senses = e.get("senses") or []
        # (translation, indexes of the English senses it belongs to)
        attached = [(t, [i]) for i, s in enumerate(senses) for t in s.get("translations") or []]
        attached += [(t, _attached_senses(t, senses)) for t in e.get("translations") or []]
        for t, idx in attached:
            if t.get("lang_code") != code or not t.get("word"):
                continue
            seen = True
            if not is_lemma(t):
                continue
            # The word counts when English Wiktionary attaches it to one of
            # the English word's first three senses or to a plain one — not
            # only to a deep domain sense (trim lists assiette under 「the
            # manner in which a vessel floats」, its 5th sense, nautical).
            if idx is None or any(i < 3 or not senses[i].get("topics") for i in idx if i < len(senses)):
                return True
    return False if seen else None


_SENSE_STOP = frozenset({"a", "an", "the", "of", "in", "on", "or", "and", "to", "for", "by",
                         "with", "which", "that", "is", "as", "etc", "see", "also"})


def _attached_senses(t: dict, senses: list[dict]) -> list[int] | None:
    """Indexes of the English senses an entry-level translation belongs
    to: the senses whose gloss shares most words with the translation
    table's title, else the highest Kaikki _dis1 weights; None when
    unknown."""
    title = {w for w in re.findall(r"[a-z']+", str(t.get("sense") or "").lower())} - _SENSE_STOP
    if title and senses:
        scores = []
        for s in senses:
            words = set(re.findall(r"[a-z']+", (s.get("glosses") or [""])[0].lower())) - _SENSE_STOP
            scores.append(len(title & words))
        best = max(scores)
        if best >= max(2, len(title) // 2):
            return [i for i, sc in enumerate(scores) if sc == best]
    raw = str(t.get("_dis1") or "").split()
    try:
        weights = [int(x) for x in raw]
    except ValueError:
        return None
    if not weights or max(weights) <= 0:
        return None
    top = max(weights)
    return [i for i, w in enumerate(weights) if w == top]


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
    domain = set(topics or ()) - EVERYDAY_TOPICS or _labels(item) & DOMAIN_TAGS
    if domain and confirmed_by_english(item, target, lemma) is False:
        return 1
    return 0


# Card #357: plain senses of one word have no frequency data (Kaikki order is
# arbitrary), so the senses a picture needs are curated by hand, most common
# first: (lemma, pos) -> English gloss prefixes. Unlisted senses keep their order.
PREFERRED_GLOSSES = {
    ("fr", "motif", "noun"): ("motive", "pattern", "motif"),
    ("fr", "bord", "noun"): ("border", "rim", "side"),
    ("fr", "flèche", "noun"): ("arrow", "spire", "pointer"),
    ("fr", "forme", "noun"): ("shape (physical", "form", "shape"),
    ("fr", "poignée", "noun"): ("handle", "grip", "handful (amount", "handful", "handshake"),
    ("fr", "carrière", "noun"): ("career", "quarry", "racecourse"),
}


@lru_cache(maxsize=1)
def english_common_senses() -> dict:
    """Card #381 (問題回報 #341): English senses reviewed as the common ones,
    'lemma|pos' -> {first: [gloss prefixes], zh, zh_ai, low} (quality/
    en_common_senses.json). Kaikki's English order is historical too: train's
    first sense is a dress's train, capital's is money, pen's an enclosure."""
    import json
    from .quality import QUALITY_DIR
    p = QUALITY_DIR / "en_common_senses.json"
    return json.loads(p.read_text(encoding="utf-8")).get("words", {}) if p.exists() else {}


def _preferred_index(item: dict, target: str, lemma: str) -> int:
    pos = str(item.get("pos") or "")
    prefs = PREFERRED_GLOSSES.get((target, lemma, pos))
    if prefs is None and target == "en":
        prefs = tuple(p.lower() for p in english_common_senses().get(f"{lemma}|{pos}", {}).get("first", ()))
    if not prefs:
        return 0
    gloss = str(item.get("gloss") or "").lower()
    for i, p in enumerate(prefs):
        if gloss.startswith(p):
            return i
    return len(prefs)


def order_senses(items: list[dict], target: str, lemma: str) -> list[dict]:
    """The definition items in the order their senses get ordinals:
    current senses first, then the reviewed common ones, then (English) the
    etymology with the most established senses — second 「unit of time」
    before 「number two in a series」 (card #539); Wiktionary's order last."""
    return sorted(items, key=lambda it: (sense_rank(it, target, lemma), _preferred_index(it, target, lemma),
                                         _etymology_group_rank(it, target, lemma)))

def english_sense_translations(english: str, pos: str, target: str, gloss: str) -> set[str] | None:
    """The ``target``-language words English Wiktionary lists under the one
    English sense whose gloss is ``gloss`` (plate 「A slightly curved but
    almost flat dish」 → assiette, plat). None when no sense matches the gloss
    or the English word has no translation for that sense (card #358)."""
    from . import kaikki_index
    from .adapters.kaikki import LANG_CODE
    code = LANG_CODE.get(target, target)
    norm = lambda x: " ".join(re.findall(r"[a-z']+", str(x).lower()))
    want = norm(gloss)
    if not want:
        return None
    words: set[str] | None = None
    for e in kaikki_index.lookup("en", english) or []:
        if str(e.get("word", "")).lower() != english or _kaikki_pos(e) != pos:
            continue
        senses = e.get("senses") or []
        hit = [i for i, s in enumerate(senses) if norm((s.get("glosses") or [""])[0]) == want]
        if not hit:
            continue
        found = {str(t["word"]).strip().lower() for i in hit for t in senses[i].get("translations") or []
                 if t.get("lang_code") == code and t.get("word")}
        for t in e.get("translations") or []:
            if t.get("lang_code") == code and t.get("word") and set(_attached_senses(t, senses) or ()) & set(hit):
                found.add(str(t["word"]).strip().lower())
        if found:
            words = (words or set()) | found
    return words

