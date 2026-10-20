"""Picture labels by meaning in another language's pack (#347/#350).

Vision labels are English words (#331). In another language's pack a picture
shared by meaning (#336) is bound to one word only, so it also names the
target words whose main sense means one of the picture's approved English
words (chat → cat, table → table). serve_app.catalog_snapshot publishes these
labels; images.share_by_meaning counts them before sharing a picture (#368).
"""
from __future__ import annotations

import time

from sqlalchemy import select, text

from . import models as m


def meaning_index(session, target, with_candidates=False):
    """English label words of the target language's main senses (#347).

    Returns ({sense_id: [english, ...]}, {(english, pos): (lexeme_id, sense_id)}):
    the English words are every item of the sense's English meaning (#350:
    ombre 「shade, shadow」 names a picture's shadow too), the first being
    images.label_word's. When several words share one English word, the main
    sense wins, then an earlier item, then a meaning that is the word itself
    (not a gloss), then the easier CEFR level, then the older entry.

    A deeper sense (ordinal >= PRIMARY_ORDINAL) counts too when it is a
    plain current sense and English Wiktionary lists the word as a
    translation of that English word (card #352: motif 「pattern」 is its
    third sense, flèche 「spire」 its sixth; passer 「to sit (an exam)」 is
    not a translation of sit)."""
    from .picture_need import PRIMARY_ORDINAL
    from .search_terms import reviewed, sense_label_terms
    from .sense_order import english_translates_to, sense_rank
    rows = session.execute(text(
        "SELECT l.id, l.pos, l.cefr, sn.id, sn.ordinal,"
        " (SELECT t.text FROM sense_translations t WHERE t.sense_id = sn.id"
        "  AND t.native_language = 'en' ORDER BY t.id LIMIT 1),"
        " (SELECT d.text FROM definitions d WHERE d.sense_id = sn.id"
        "  AND d.language IN (:lang, 'en') ORDER BY (d.language = :lang) DESC, d.id LIMIT 1),"
        " l.lemma, sn.labels, l.normalized, sn.sense_key"
        " FROM lexemes l JOIN senses sn ON sn.lexeme_id = l.id"
        " WHERE l.language = :lang AND l.status = 'full'"),
        {'lang': target}).all()
    bands = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    sense_label, ranked, candidates = {}, {}, {}
    for lexeme_id, pos, cefr, sense_id, ordinal, meaning, gloss, lemma, labels, normalized, sense_key in rows:
        # A sense reviewed under card #384 names only its recorded term (or nothing).
        terms = sense_label_terms(target, normalized, pos, sense_key, meaning, gloss)
        if not terms:
            continue
        if ordinal >= PRIMARY_ORDINAL:
            if target == 'en' or sense_rank({'pos': pos, 'gloss': gloss or '', 'labels': labels or []},
                                            target, lemma) != 0:
                continue
            terms = [t for t in terms if english_translates_to(t, pos, target, lemma) is True]
            if not terms:
                continue
        sense_label[sense_id] = terms
        level = bands.index(cefr) if cefr in bands else len(bands)
        own = terms if reviewed(target, normalized, pos, sense_key)[0] else sense_label_terms(
            target, normalized, pos, sense_key, meaning)
        for position, english in enumerate(terms):
            rank = (ordinal, position, english not in own, level, lexeme_id)
            key = (english, pos)
            candidates.setdefault(key, []).append((rank, lexeme_id, sense_id, lemma))
            if key not in ranked or rank < ranked[key][0]:
                ranked[key] = (rank, (lexeme_id, sense_id))
    by_meaning = {key: hit for key, (_, hit) in ranked.items()}
    if with_candidates:
        return sense_label, by_meaning, {k: sorted(v) for k, v in candidates.items() if len(v) > 1}
    return sense_label, by_meaning


def add_meaning_tags(session, target, tags, full_words, by_meaning, rivals):
    """Append to ``tags`` ({asset_id: [tag, ...]}) the target words each
    picture names through its approved English words (#347)."""
    if not by_meaning or not tags:
        return
    from .sense_order import english_sense_translations
    for asset_id, english, pos, bound_gloss in session.execute(text(
            "SELECT si.image_asset_id, l.normalized, l.pos,"
            " (SELECT d.text FROM definitions d WHERE d.sense_id = x.id AND d.language = 'en'"
            "  ORDER BY d.id LIMIT 1) FROM sense_images si"
            " JOIN senses x ON x.id = si.sense_id JOIN lexemes l ON l.id = x.lexeme_id"
            " WHERE si.review_status = 'approved' AND l.language = 'en' AND l.status = 'full'"
            " AND si.image_asset_id = ANY(:ids) ORDER BY si.id"), {'ids': list(tags)}):
        hit = by_meaning.get((english, pos))
        # Several target words share this English word: the one English
        # Wiktionary lists under the picture's own English sense wins
        # (card #358: the plate photo is assiette, not plaque).
        if hit and (english, pos) in rivals and bound_gloss:
            on_sense = english_sense_translations(english, pos, target, bound_gloss)
            if on_sense and hit[1] and not any(c[2] == hit[1] and c[3].lower() in on_sense
                                             for c in rivals[(english, pos)]):
                pick = next((c for c in rivals[(english, pos)] if c[3].lower() in on_sense), None)
                if pick and not any(t['lexeme_id'] == pick[1] for t in tags[asset_id]):
                    hit = (pick[1], pick[2])
        if hit and hit[0] in full_words:
            tags[asset_id].append({'lexeme_id': hit[0], 'sense_id': hit[1],
                                   'review_status': 'approved', 'origin': 'meaning'})


INDEX_TTL = 600  # meaning_index reads every sense (~30 s for French)


def cached_index(session, target):
    """meaning_index with candidates, reused for INDEX_TTL seconds while the
    target's full words and their senses stay the same: an import job shares
    pictures for many words in a row."""
    # Counts / max IDs miss edits to an existing meaning or sense order.
    # Keep the cache in this session so uncommitted imports cannot leak to
    # another worker's transaction, and fingerprint the actual index inputs.
    stamp = tuple(session.execute(text(
        "SELECT count(*), sum(hashtextextended(ROW(l.id, l.pos, l.cefr, l.lemma,"
        " sn.id, sn.ordinal, sn.labels, t.text, d.text)::text, 0)::numeric)"
        " FROM lexemes l JOIN senses sn ON sn.lexeme_id = l.id"
        " LEFT JOIN sense_translations t ON t.sense_id = sn.id AND t.native_language = 'en'"
        " LEFT JOIN definitions d ON d.sense_id = sn.id AND d.language IN (:lang, 'en')"
        " WHERE l.language = :lang AND l.status = 'full'"), {'lang': target}).one())
    cache = session.info.setdefault('meaning_label_indexes', {})
    hit = cache.get(target)
    if hit is None or hit[1] != stamp or time.monotonic() - hit[0] > INDEX_TTL:
        hit = (time.monotonic(), stamp, meaning_index(session, target, True))
        cache[target] = hit
    return hit[2]


def label_context(session, target):
    """Reuse one full-word set and meaning index for a sharing call."""
    full = set(session.scalars(select(m.Lexeme.id).where(
        m.Lexeme.language == target, m.Lexeme.status == 'full')).all())
    index = ({}, {}, {}) if target == 'en' else cached_index(session, target)
    return full, index


def pack_label_words(session, target, asset_id, extra_lexeme_id=None, *, context=None) -> set[int]:
    """The target words a picture would show in the target language's pack
    (catalog_snapshot's labels), counting ``extra_lexeme_id`` as bound too."""
    full, (_, by_meaning, rivals) = context if context is not None else label_context(session, target)
    tags = {asset_id: [{'lexeme_id': lexeme_id} for lexeme_id in session.scalars(
        select(m.Sense.lexeme_id).join(m.SenseImage, m.SenseImage.sense_id == m.Sense.id).where(
            m.SenseImage.image_asset_id == asset_id,
            m.SenseImage.review_status == 'approved').order_by(m.SenseImage.id)).all() if lexeme_id in full]}
    # The real pack starts with every explicit binding, including the new
    # one, before choosing between competing translations (#358).
    if extra_lexeme_id in full:
        tags[asset_id].append({'lexeme_id': extra_lexeme_id})
    if target != 'en':
        add_meaning_tags(session, target, tags, full, by_meaning, rivals)
    return {t['lexeme_id'] for t in tags[asset_id]}
