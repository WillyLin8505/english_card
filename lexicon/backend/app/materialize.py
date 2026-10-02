"""Project adopted field values into the dictionary tables.

Target-language rows (lexemes, senses, forms, pronunciations, examples,
relations, etymology) are the union of what any direction adopted; the
native layers (sense / example / relation / etymology translations) are
kept per native language. The SQLite export then takes, for one
direction, only what that direction's policy adopted.

Lexeme ids stay stable: rows are updated in place, and a stub lexeme
(created earlier to link a related word) becomes the full entry, or is
redirected to it.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import catalog
from . import models as m
from .audio import ensure_audio
from .text import example_key, normalize_lemma, text_hash

FORM_POS = {"verb_base": "verb", "verb_past": "verb", "verb_past_participle": "verb",
            "verb_present_participle": "verb", "verb_third_person": "verb",
            "noun_plural": "noun", "adj_comparative": "adj", "adj_superlative": "adj",
            "fr_past_participle": "verb", "fr_feminine": "adj", "fr_plural": "adj",
            "fr_feminine_plural": "adj", **{f"fr_present_{p}": "verb" for p in
                                            ("1s", "2s", "3s", "1p", "2p", "3p")}}
REL_FIELDS = catalog.RELATION_FIELDS + ["derived_terms"]


def _values(s: Session, target: str, lemma: str) -> dict[str, dict[str, list]]:
    """native → field → items (only adopted, non-empty values)."""
    out: dict[str, dict[str, list]] = {}
    for fv in s.execute(select(m.FieldValue).where(m.FieldValue.target_language == target,
                                                   m.FieldValue.lemma == lemma)).scalars():
        if fv.items:
            out.setdefault(fv.native_language, {})[fv.field] = fv.items
    return out


def _union(values: dict[str, dict[str, list]], field_key: str) -> list[dict]:
    seen, out = set(), []
    for native in sorted(values):
        for it in values[native].get(field_key, []):
            k = it.get("key") or repr(sorted(it.items()))
            if k not in seen:
                seen.add(k)
                out.append(it)
    return out


_ACCENT_RANK = {"UK": 0, "RP": 0, "GB": 0, "US": 1}


def _accents(it: dict) -> list:
    a = it.get("accent")
    return list(a) if isinstance(a, list) else [a]


def main_accent(value) -> str | None:
    """The accent to label a pronunciation with: British if it is one of
    its accents (/ˈæpəl/ is tagged AU, CA, US, UK), else the first."""
    found = [a for a in (value if isinstance(value, list) else [value]) if a]
    return min(found, key=lambda a: _ACCENT_RANK.get(a, 2), default=None)


def british_first(rows: list, accent_of=_accents, value_of=lambda it: it.get("ipa") or "") -> list:
    """Spec section 7: British English is the default pronunciation, then
    American, then the rest in source order. A phonemic /…/ transcription
    comes before any narrow […] one: learners read the phonemic kind. A
    later etymology's sound (wind 纏繞 /waɪnd/) comes after all of these."""
    def rank(it) -> int:
        # /ˈwɪnd/ tagged [US, UK] is British too.
        found = accent_of(it)
        return min((_ACCENT_RANK.get(a or "", 2)
                    for a in (found if isinstance(found, list) else [found])), default=2)

    def later_etymology(it) -> bool:
        return isinstance(it, dict) and (it.get("etymology") or 1) > 1

    return sorted(rows, key=lambda it: (later_etymology(it),
                                        (value_of(it) or "").startswith("["), rank(it)))


def lexeme_for(s: Session, language: str, word: str, pos: str | None, create_stub=True):
    """A full lexeme for [word] (preferring [pos]), else a stub."""
    norm = normalize_lemma(word, language)
    rows = s.execute(select(m.Lexeme).where(m.Lexeme.language == language,
                                            m.Lexeme.normalized == norm)).scalars().all()
    full = [r for r in rows if r.status == "full"]
    pick = next((r for r in full if r.pos == pos), None) or (full[0] if full else None)
    if pick:
        return pick
    stub = next((r for r in rows if r.pos == (pos or "unknown")), None) or (rows[0] if rows else None)
    if stub or not create_stub:
        return stub
    stub = m.Lexeme(language=language, lemma=word, normalized=norm, pos=pos or "unknown",
                    status="stub")
    s.add(stub)
    s.flush()
    return stub


def _upgrade(s: Session, language: str, lemma: str, display: str, poses: list[str]):
    """The headword's full lexemes, one per part of speech, reusing ids."""
    rows = s.execute(select(m.Lexeme).where(m.Lexeme.language == language,
                                            m.Lexeme.normalized == lemma)).scalars().all()
    by_pos = {r.pos: r for r in rows}
    out = {}
    for pos in poses:
        lx = by_pos.get(pos)
        if lx is None:
            lx = m.Lexeme(language=language, lemma=display, normalized=lemma, pos=pos)
            s.add(lx)
            s.flush()
        lx.status, lx.lemma = "full", display
        out[pos] = lx
    # Stubs with an unknown part of speech → redirect to the main lexeme.
    main = out[poses[0]]
    for r in rows:
        if r.pos not in out and r.status == "stub":
            for rel in s.execute(select(m.LexemeRelation).where(
                    m.LexemeRelation.target_lexeme_id == r.id)).scalars().all():
                dup = s.execute(select(m.LexemeRelation.id).where(
                    m.LexemeRelation.lexeme_id == rel.lexeme_id,
                    m.LexemeRelation.relation == rel.relation,
                    m.LexemeRelation.target_lexeme_id == main.id)).first()
                if dup:
                    s.delete(rel)
            s.flush()
            s.execute(m.LexemeRelation.__table__.update().where(
                m.LexemeRelation.target_lexeme_id == r.id).values(target_lexeme_id=main.id))
            s.merge(m.LexemeRedirect(old_id=r.id, new_id=main.id))
            s.flush()
            s.delete(r)
    s.flush()
    return out


def materialize(s: Session, target: str, lemma: str, display: str | None = None) -> list[int]:
    values = _values(s, target, lemma)
    if not values:
        return []
    display = display or lemma
    u = lambda f: _union(values, f)  # noqa: E731
    senses_items = u("definition")
    poses = [i["pos"] for i in u("pos") if i.get("pos")]
    for it in senses_items:
        if it.get("pos") and it["pos"] not in poses:
            poses.append(it["pos"])
    if not poses:
        return []
    lexemes = _upgrade(s, target, lemma, display, poses)
    main = lexemes[poses[0]]
    ids = [lx.id for lx in lexemes.values()]

    # CEFR and frequency
    cefr = (u("cefr") or [{}])[0]
    freq = (u("frequency") or [{}])[0]
    for pos, lx in lexemes.items():
        by_pos = {k.rstrip(".").lower(): v for k, v in (cefr.get("by_pos") or {}).items()}
        lx.cefr = by_pos.get(pos) or by_pos.get({"adjective": "adj", "adverb": "adv"}.get(pos, pos)) \
            or cefr.get("level")
        lx.zipf = freq.get("zipf")

    # Senses and their definitions (target data)
    keep_senses: dict[int, set[str]] = {i: set() for i in ids}
    sense_rows: dict[str, list[m.Sense]] = {}
    per_lexeme_ord: dict[int, int] = {}
    for it in senses_items:
        lx = lexemes.get(it.get("pos")) or main
        sk = it.get("sense_key") or it.get("key")
        sense = s.execute(select(m.Sense).where(m.Sense.lexeme_id == lx.id,
                                                m.Sense.sense_key == sk)).scalar_one_or_none()
        if sense is None:
            sense = m.Sense(lexeme_id=lx.id, sense_key=sk)
            s.add(sense)
            s.flush()
        sense.ordinal = per_lexeme_ord.get(lx.id, 0)
        per_lexeme_ord[lx.id] = sense.ordinal + 1
        sense.labels = it.get("labels") or []
        keep_senses[lx.id].add(sk)
        sense_rows.setdefault(sk, []).append(sense)
        lang = it.get("gloss_language") or target
        d = s.execute(select(m.Definition).where(m.Definition.sense_id == sense.id,
                                                 m.Definition.language == lang)
                      ).scalar_one_or_none() or m.Definition(sense_id=sense.id, language=lang)
        d.text, d.source = it.get("gloss", ""), it.get("source", "")
        s.add(d)
    for lid, keys in keep_senses.items():
        q = delete(m.Sense).where(m.Sense.lexeme_id == lid)
        if keys:
            q = q.where(m.Sense.sense_key.not_in(keys))
        s.execute(q)
    s.flush()

    # Forms
    s.execute(delete(m.Form).where(m.Form.lexeme_id.in_(ids)))
    for f in catalog.FORM_FIELDS:
        want = FORM_POS.get(f)
        lx = lexemes.get(want) or (lexemes.get("noun") if want == "adj" else None)
        if lx is None:
            continue
        seen = set()
        for it in u(f):
            form = it.get("form", "")
            if form and form not in seen:
                seen.add(form)
                s.add(m.Form(lexeme_id=lx.id, field=f, form=form,
                             normalized=normalize_lemma(form, target), source=it.get("source", "")))

    # Pronunciations (shared by every part of speech of the headword)
    s.execute(delete(m.Pronunciation).where(m.Pronunciation.lexeme_id.in_(ids)))
    audio_assets = []
    for it in u("audio"):
        if it.get("tts"):
            audio_assets.append((None, it))
        elif it.get("url"):
            asset = ensure_audio(s, target, it, it.get("source", "kaikki"))
            if asset is not None and asset.status == "ready":
                audio_assets.append((asset, it))
    for lx in lexemes.values():
        n = 0
        for kind, f in (("ipa", "ipa"), ("phonemes", "phonemes"), ("syllables", "syllables"),
                        ("stress", "stress")):
            rows = british_first(u(f)) if f == "ipa" else u(f)
            for i, it in enumerate(rows):
                val = (it.get("ipa") or it.get("phonemes")
                       or "·".join(it.get("syllables") or []) or str(it.get("count") or "")
                       or it.get("pattern") or str(it.get("primary_syllable") or ""))
                s.add(m.Pronunciation(lexeme_id=lx.id, kind=kind, value=val,
                                      accent=main_accent(it.get("accent")),
                                      is_default=i == 0, source=it.get("source", ""), ordinal=n))
                n += 1
        first_audio = True
        for asset, it in british_first(audio_assets, lambda r: r[0].accent if r[0] else "~",
                                       lambda r: ""):
            s.add(m.Pronunciation(
                lexeme_id=lx.id, kind="tts" if asset is None else "audio",
                value=it.get("locale", "") if asset is None else "",
                accent=(it.get("accent") or [None])[0] if asset is not None else None,
                audio_asset_id=asset.id if asset is not None else None,
                is_default=first_audio and asset is not None, source=it.get("source", ""),
                ordinal=n))
            first_audio = first_audio and asset is None
            n += 1

    # Relations and derived words, linked to real (or stub) lexemes
    derivation = {i["word"].lower(): i for i in u("derivation_relation") if i.get("word")}
    derived_pos = {i["word"].lower(): i.get("pos") for i in u("derived_pos") if i.get("word")}
    keep_rel: set[int] = set()
    # The headword's own forms are not relation words (apple → apples).
    own_forms = {lemma.lower()} | {(it.get("form") or "").lower()
                                   for f in catalog.FORM_FIELDS for it in u(f)}
    for f in REL_FIELDS:
        for n, it in enumerate(u(f)):
            w = it.get("word", "")
            if not w or w.lower() in own_forms:
                continue
            pos = it.get("pos") if f != "derived_terms" else (derived_pos.get(w.lower())
                                                               or it.get("pos"))
            tgt = lexeme_for(s, target, w, pos)
            # Relation targets may be stubs. Preserve the frequency profile now;
            # a later full import replaces estimates with CEFR-J / wordfreq data.
            if tgt.zipf is None and it.get("zipf") is not None:
                tgt.zipf = it["zipf"]
            if tgt.cefr is None and it.get("cefr"):
                tgt.cefr = it["cefr"]
            if tgt.id in ids:
                continue
            src_lx = lexemes.get(it.get("pos")) if f != "derived_terms" else main
            src_lx = src_lx or main
            rel = s.execute(select(m.LexemeRelation).where(
                m.LexemeRelation.lexeme_id == src_lx.id, m.LexemeRelation.relation == f,
                m.LexemeRelation.target_lexeme_id == tgt.id)).scalar_one_or_none()
            if rel is None:
                rel = m.LexemeRelation(lexeme_id=src_lx.id, relation=f, target_lexeme_id=tgt.id)
                s.add(rel)
            rel.target_word, rel.source, rel.ordinal = w, it.get("source", ""), n
            rel.strength = it.get("score") or it.get("confidence")
            detail = {k: it[k] for k in ("note", "difference", "phonemes", "zipf", "rarity",
                                         "cefr", "cefr_source", "hide_by_default")
                      if it.get(k) is not None}
            if f == "derived_terms":
                d = derivation.get(w.lower())
                if d:
                    detail.update({k: d[k] for k in ("type", "affix", "label", "from_pos",
                                                     "to_pos") if d.get(k)})
                if pos:
                    detail["pos"] = pos
            rel.detail = detail
            sk = it.get("sense_key")
            rel.source_sense_id = sense_rows[sk][0].id if sk and sk in sense_rows else None
            s.flush()
            keep_rel.add(rel.id)
    q = delete(m.LexemeRelation).where(m.LexemeRelation.lexeme_id.in_(ids))
    if keep_rel:
        q = q.where(m.LexemeRelation.id.not_in(keep_rel))
    s.execute(q)

    # Etymology (the same for every part of speech of the headword)
    ety = {
        "root": [i.get("morpheme") for i in u("root")],
        "prefix": [i.get("morpheme") for i in u("prefix")],
        "suffix": [i.get("morpheme") for i in u("suffix")],
        "origin_language": (u("origin_language") or [{}])[0].get("language"),
        "original_form": (u("original_form") or [{}])[0].get("form"),
        "text": (u("etymology_text") or [{}])[0].get("text"),
    }
    for lx in lexemes.values():
        if any(ety.values()):
            row = s.get(m.Etymology, lx.id) or m.Etymology(lexeme_id=lx.id)
            for k, v in ety.items():
                setattr(row, k, v)
            s.add(row)
        else:
            s.execute(delete(m.Etymology).where(m.Etymology.lexeme_id == lx.id))

    # 構詞拆解 (the same for every part of speech of the headword)
    s.execute(delete(m.Morpheme).where(m.Morpheme.lexeme_id.in_(ids)))
    s.flush()
    morph_rows: dict[str, list[m.Morpheme]] = {}
    bd = (u("morphemes") or [None])[0]
    if bd:
        for lx in lexemes.values():
            for i, p in enumerate(bd.get("parts", [])):
                row = m.Morpheme(lexeme_id=lx.id, ordinal=i, part=str(p.get("part", ""))[:64],
                                 kind=p.get("kind", "root"), meaning=p.get("meaning"),
                                 free=bool(p.get("free")), source=bd.get("source", ""))
                s.add(row)
                morph_rows.setdefault(f"{i}:{p.get('part', '')}", []).append(row)
        s.flush()

    # Examples
    ex_sense = {i.get("example_key"): i.get("sense_key") for i in u("example_sense")}
    ex_level = {i.get("example_key"): i.get("level") for i in u("example_difficulty")}
    keep_ex: dict[int, set[str]] = {i: set() for i in ids}
    ex_rows: dict[str, m.Example] = {}
    for n, it in enumerate(u("example_sentences")):
        text = it.get("text", "")
        k = it.get("key") or example_key(text)
        sk = ex_sense.get(k) or it.get("sense_key")
        sense = sense_rows.get(sk, [None])[0] if sk else None
        lx_id = sense.lexeme_id if sense else main.id
        h = text_hash(text)
        ex = s.execute(select(m.Example).where(m.Example.lexeme_id == lx_id,
                                               m.Example.text_hash == h)).scalar_one_or_none()
        if ex is None:
            ex = m.Example(lexeme_id=lx_id, text_hash=h, language=target)
            s.add(ex)
        ex.text, ex.sense_id, ex.difficulty = text, sense.id if sense else None, ex_level.get(k)
        ex.source, ex.ordinal = it.get("source", ""), n
        ex.source_record_id = str(it.get("tatoeba_id") or "") or None
        ex.license = catalog.SOURCES[it["source"]].license if it.get("source") in catalog.SOURCES \
            else None
        s.flush()
        keep_ex[lx_id].add(h)
        ex_rows[k] = ex
    for lid, hashes in keep_ex.items():
        q = delete(m.Example).where(m.Example.lexeme_id == lid)
        if hashes:
            q = q.where(m.Example.text_hash.not_in(hashes))
        s.execute(q)
    s.flush()

    # Native layers, per native language
    for native, fields in values.items():
        _native_layer(s, native, fields, lexemes, sense_rows, ex_rows, ids)
        for it in fields.get("morphemes_native", []):
            for row in morph_rows.get(it.get("slot") or "", []):
                s.add(m.MorphemeTranslation(morpheme_id=row.id, native_language=native,
                                            text=it.get("text", ""), source=it.get("source", ""),
                                            is_ai=bool(it.get("ai"))))
    s.flush()
    return ids


def _native_layer(s, native, fields, lexemes, sense_rows, ex_rows, ids):
    # sense translations
    sense_ids = [sn.id for rows in sense_rows.values() for sn in rows]
    keep = set()
    for it in fields.get("native_definition", []):
        for sense in sense_rows.get(it.get("sense_key") or it.get("slot"), []):
            row = s.execute(select(m.SenseTranslation).where(
                m.SenseTranslation.sense_id == sense.id,
                m.SenseTranslation.native_language == native)).scalar_one_or_none() \
                or m.SenseTranslation(sense_id=sense.id, native_language=native)
            row.text, row.source = it.get("text", ""), it.get("source", "")
            row.is_ai = bool(it.get("ai"))
            row.is_override = it.get("source") == "user"
            s.add(row)
            keep.add(sense.id)
    if sense_ids:
        s.execute(delete(m.SenseTranslation).where(
            m.SenseTranslation.native_language == native,
            m.SenseTranslation.sense_id.in_([i for i in sense_ids if i not in keep])))
    # example translations
    keep_ex = set()
    for it in fields.get("example_translation", []):
        ex = ex_rows.get(it.get("example_key") or it.get("slot"))
        if ex is None:
            continue
        row = s.execute(select(m.ExampleTranslation).where(
            m.ExampleTranslation.example_id == ex.id,
            m.ExampleTranslation.native_language == native)).scalar_one_or_none() \
            or m.ExampleTranslation(example_id=ex.id, native_language=native)
        row.text, row.source = it.get("text", ""), it.get("source", "")
        row.source_record_id = str(it.get("tatoeba_id") or "") or None
        row.is_ai = bool(it.get("ai"))
        s.add(row)
        keep_ex.add(ex.id)
    all_ex = [e.id for e in ex_rows.values()]
    if all_ex:
        s.execute(delete(m.ExampleTranslation).where(
            m.ExampleTranslation.native_language == native,
            m.ExampleTranslation.example_id.in_([i for i in all_ex if i not in keep_ex])))
    # relation translations
    rels = s.execute(select(m.LexemeRelation).where(m.LexemeRelation.lexeme_id.in_(ids))
                     ).scalars().all()
    meanings = {}
    for f in catalog.RELATION_FIELDS:
        for it in fields.get(f"{f}_native", []):
            meanings[(f, (it.get("word") or it.get("slot") or "").lower())] = it
    for it in fields.get("derived_native_meaning", []):
        meanings[("derived_terms", (it.get("word") or it.get("slot") or "").lower())] = it
    for rel in rels:
        it = meanings.get((rel.relation, rel.target_word.lower()))
        row = s.execute(select(m.RelationTranslation).where(
            m.RelationTranslation.relation_id == rel.id,
            m.RelationTranslation.native_language == native)).scalar_one_or_none()
        if it is None:
            if row is not None:
                s.delete(row)
            continue
        row = row or m.RelationTranslation(relation_id=rel.id, native_language=native)
        row.text, row.source, row.is_ai = it.get("text", ""), it.get("source", ""), bool(it.get("ai"))
        s.add(row)
    # etymology translation
    ety = (fields.get("etymology_native") or [None])[0]
    for lx in lexemes.values():
        row = s.get(m.EtymologyTranslation, (lx.id, native))
        if ety:
            row = row or m.EtymologyTranslation(lexeme_id=lx.id, native_language=native)
            row.text, row.source, row.is_ai = ety.get("text", ""), ety.get("source", ""), \
                bool(ety.get("ai"))
            s.add(row)
        elif row is not None:
            s.delete(row)
