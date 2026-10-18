"""Which words need a fetched picture.

A learner looks up a spelling. The picture is the noun's: a verb, adjective,
or other part of speech of the same spelling shows that noun's pictures and
is not itself missing one. A spelling with no full noun (primary sense,
ordinal < 2) does not need a download. The missing-picture count, the fetch
queue, and the app pack's ``picture_ids`` all use this module.
"""
from __future__ import annotations

import re

from sqlalchemy import and_, func, select, text

from . import models as m

PICTURE_POS = "noun"
# auto_fetch and the missing count both stop after the first two senses.
PRIMARY_ORDINAL = 2
# How many different search phrases to try after the pictures were all rejected.
REJECTED_REFETCH_CAP = 2
_STOP = frozenset({
    "a", "an", "the", "of", "or", "and", "to", "in", "on", "for", "from", "with",
    "that", "which", "who", "whom", "whose", "is", "are", "was", "were", "be",
    "been", "being", "by", "as", "at", "into", "its", "it", "this", "these",
    "those", "something", "someone", "somebody", "also", "not", "no", "their",
    "his", "her", "than", "then", "such", "other", "another", "one", "used",
    "usually", "often", "when", "where", "while", "about", "over", "under",
    "between", "through", "without", "within", "very", "more", "most", "any",
    "some", "each", "both", "own", "same", "just", "only", "can", "may",
})


def needs_own_picture(pos: str, status: str, ordinals) -> bool:
    """True when this entry is a full noun with a primary sense."""
    if status != "full" or pos != PICTURE_POS:
        return False
    return any(int(o) < PRIMARY_ORDINAL for o in ordinals)


def sense_ordinals(lx: dict) -> list[int]:
    """Ordinals on a pack lexeme. A sense list without ordinals is the
    exported primary senses (ordinal 0, 1, …)."""
    senses = lx.get("senses") or []
    if not senses:
        return []
    if any("ordinal" in s for s in senses):
        return [int(s.get("ordinal", PRIMARY_ORDINAL)) for s in senses]
    return list(range(len(senses)))


def assign_picture_ids(lexemes: list[dict]) -> None:
    """Set ``picture_ids`` on every lexeme: the entries whose pictures it shows.

    A picture noun lists itself. Another part of speech lists the picture
    nouns of the same spelling. Anything else lists nothing (no picture).
    """
    groups: dict[str, list[dict]] = {}
    for lx in lexemes:
        if lx.get("status") != "full" or lx.get("redirect_to"):
            lx["picture_ids"] = []
            continue
        groups.setdefault(lx.get("normalized") or "", []).append(lx)
    for group in groups.values():
        heads = [lx["id"] for lx in group
                 if needs_own_picture(lx.get("pos") or "", lx.get("status") or "",
                                      sense_ordinals(lx))]
        head_set = set(heads)
        for lx in group:
            if lx["id"] in head_set:
                lx["picture_ids"] = [lx["id"]]
            elif heads:
                lx["picture_ids"] = list(heads)
            else:
                lx["picture_ids"] = []


def content_words(gloss: str | None, lemma: str) -> list[str]:
    """Distinct gloss words that can change a picture search."""
    skip = _STOP | {lemma.lower().strip()}
    out = []
    for word in re.findall(r"[a-z]+(?:'[a-z]+)?", (gloss or "").lower()):
        if word in skip or len(word) < 3 or word in out:
            continue
        out.append(word)
    return out


def next_query(lemma: str, gloss: str | None, retries_done: int) -> str | None:
    """The next search phrase after ``retries_done`` alternate tries, or None
    when the cap is used up or the gloss adds no new word."""
    if retries_done < 0 or retries_done >= REJECTED_REFETCH_CAP:
        return None
    words = content_words(gloss, lemma)
    if retries_done >= len(words):
        return None
    phrase = f"{lemma.strip().lower()} {words[retries_done]}"
    return phrase if phrase != lemma.strip().lower() else None


def lemma_needs_picture(s, language: str, lemma: str) -> bool:
    return s.scalar(text("""
        SELECT 1 FROM lexemes l
        JOIN senses sn ON sn.lexeme_id = l.id AND sn.ordinal < :k
        WHERE l.language = :language AND l.normalized = lower(:lemma)
          AND l.status = 'full' AND l.pos = :pos
        LIMIT 1
    """), {"k": PRIMARY_ORDINAL, "language": language, "lemma": lemma,
           "pos": PICTURE_POS}) is not None


def lemma_ineligible_for_fetch():
    """Queued lemma that already has full entries and none is a picture noun.

    A task with no lexeme yet stays eligible: the word may still be importing.
    """
    has_full = (
        select(m.Lexeme.id)
        .where(
            m.Lexeme.language == m.ImageFetchTask.target_language,
            m.Lexeme.normalized == func.lower(m.ImageFetchTask.lemma),
            m.Lexeme.status == "full",
        )
        .exists()
    )
    has_noun = (
        select(m.Lexeme.id)
        .join(m.Sense, m.Sense.lexeme_id == m.Lexeme.id)
        .where(
            m.Lexeme.language == m.ImageFetchTask.target_language,
            m.Lexeme.normalized == func.lower(m.ImageFetchTask.lemma),
            m.Lexeme.status == "full",
            m.Lexeme.pos == PICTURE_POS,
            m.Sense.ordinal < PRIMARY_ORDINAL,
        )
        .exists()
    )
    return and_(has_full, ~has_noun)


def missing_stats(s, language: str = "en") -> dict:
    """Board numbers: picture nouns that have no non-rejected picture."""
    words = s.scalar(text(
        "SELECT count(*) FROM lexemes WHERE language = :language AND status = 'full'"
    ), {"language": language})
    need = s.scalar(text("""
        SELECT count(*) FROM lexemes l
        WHERE l.language = :language AND l.status = 'full' AND l.pos = :pos
          AND EXISTS (SELECT 1 FROM senses sn WHERE sn.lexeme_id = l.id AND sn.ordinal < :k)
    """), {"language": language, "pos": PICTURE_POS, "k": PRIMARY_ORDINAL})
    missing = s.scalar(text("""
        SELECT count(*) FROM lexemes l
        WHERE l.language = :language AND l.status = 'full' AND l.pos = :pos
          AND EXISTS (SELECT 1 FROM senses sn WHERE sn.lexeme_id = l.id AND sn.ordinal < :k)
          AND NOT EXISTS (
            SELECT 1 FROM senses sn JOIN sense_images si ON si.sense_id = sn.id
            WHERE sn.lexeme_id = l.id AND si.review_status <> 'rejected')
    """), {"language": language, "pos": PICTURE_POS, "k": PRIMARY_ORDINAL})
    review = s.scalar(text("SELECT count(*) FROM sense_images WHERE review_status = 'pending'"))
    fetch = s.scalar(text(
        "SELECT count(*) FROM image_fetch_tasks WHERE status IN ('queued', 'running', 'requeue')"))
    return {"words": int(words or 0), "need": int(need or 0), "missing": int(missing or 0),
            "review": int(review or 0), "fetch": int(fetch or 0)}
