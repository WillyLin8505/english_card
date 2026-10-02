"""Export for Flutter: one read-only SQLite per language direction, the
target language's audio media list, and manifest.json.

Content is what *this direction's* policies adopted (field_values for
target + native); ids are the stable dictionary ids (lexemes, senses,
examples, relations). Built in a temp folder, checked (foreign keys,
orphan audio, required fields, translation pairing, readability), then
renamed into place — a failed export leaves nothing that looks finished.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from . import catalog, config
from . import models as m
from .text import example_key, text_hash

SCHEMA_VERSION = 4  # 3: relation CEFR / frequency / rarity; 4: approved sense pictures

DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE labels (key TEXT PRIMARY KEY, text TEXT NOT NULL);
CREATE TABLE lexemes (
  id INTEGER PRIMARY KEY, language TEXT NOT NULL, lemma TEXT NOT NULL,
  normalized TEXT NOT NULL, pos TEXT NOT NULL, status TEXT NOT NULL,
  cefr TEXT, zipf REAL);
CREATE INDEX ix_lexemes_lookup ON lexemes(language, normalized, pos);
CREATE INDEX ix_lexemes_prefix ON lexemes(normalized COLLATE NOCASE);
CREATE TABLE lexeme_redirects (old_id INTEGER PRIMARY KEY,
  new_id INTEGER NOT NULL REFERENCES lexemes(id));
CREATE TABLE senses (
  id INTEGER PRIMARY KEY, lexeme_id INTEGER NOT NULL REFERENCES lexemes(id),
  ordinal INTEGER NOT NULL, definition TEXT NOT NULL, definition_language TEXT NOT NULL,
  labels TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL);
CREATE INDEX ix_senses_lexeme ON senses(lexeme_id, ordinal);
CREATE TABLE sense_translations (
  sense_id INTEGER PRIMARY KEY REFERENCES senses(id), text TEXT NOT NULL,
  source TEXT NOT NULL, is_ai INTEGER NOT NULL DEFAULT 0, is_override INTEGER NOT NULL DEFAULT 0);
CREATE TABLE forms (
  lexeme_id INTEGER NOT NULL REFERENCES lexemes(id), field TEXT NOT NULL,
  form TEXT NOT NULL, normalized TEXT NOT NULL, label TEXT, source TEXT NOT NULL,
  PRIMARY KEY (lexeme_id, field, form));
CREATE INDEX ix_forms_normalized ON forms(normalized);
CREATE TABLE audio (
  id INTEGER PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT,
  accent TEXT, speaker TEXT, license TEXT, attribution TEXT, source_url TEXT,
  duration_s REAL);
CREATE TABLE pronunciations (
  lexeme_id INTEGER NOT NULL REFERENCES lexemes(id), kind TEXT NOT NULL, value TEXT,
  accent TEXT, audio_id INTEGER REFERENCES audio(id), is_default INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL, ordinal INTEGER NOT NULL);
CREATE INDEX ix_pron_lexeme ON pronunciations(lexeme_id, ordinal);
CREATE TABLE examples (
  id INTEGER PRIMARY KEY, lexeme_id INTEGER NOT NULL REFERENCES lexemes(id),
  sense_id INTEGER REFERENCES senses(id), text TEXT NOT NULL, difficulty TEXT,
  source TEXT NOT NULL, source_record_id TEXT, license TEXT, ordinal INTEGER NOT NULL);
CREATE INDEX ix_examples_lexeme ON examples(lexeme_id, ordinal);
CREATE TABLE example_translations (
  example_id INTEGER PRIMARY KEY REFERENCES examples(id), text TEXT NOT NULL,
  source TEXT NOT NULL, is_ai INTEGER NOT NULL DEFAULT 0);
CREATE TABLE relations (
  id INTEGER PRIMARY KEY, lexeme_id INTEGER NOT NULL REFERENCES lexemes(id),
  relation TEXT NOT NULL, target_lexeme_id INTEGER NOT NULL REFERENCES lexemes(id),
  target_word TEXT NOT NULL, target_pos TEXT, source_sense_id INTEGER REFERENCES senses(id),
  strength REAL, detail TEXT NOT NULL DEFAULT '{}', native_meaning TEXT, native_source TEXT,
  native_is_ai INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL, ordinal INTEGER NOT NULL,
  target_cefr TEXT, target_zipf REAL, rarity TEXT,
  hide_by_default INTEGER NOT NULL DEFAULT 0);
CREATE INDEX ix_relations_lexeme ON relations(lexeme_id, relation, ordinal);
CREATE TABLE etymology (
  lexeme_id INTEGER PRIMARY KEY REFERENCES lexemes(id), root TEXT, prefix TEXT, suffix TEXT,
  origin_language TEXT, original_form TEXT, text TEXT, native_text TEXT, native_source TEXT,
  native_is_ai INTEGER NOT NULL DEFAULT 0);
CREATE TABLE morphemes (
  lexeme_id INTEGER NOT NULL REFERENCES lexemes(id), ordinal INTEGER NOT NULL,
  part TEXT NOT NULL, kind TEXT NOT NULL, meaning TEXT, free INTEGER NOT NULL DEFAULT 0,
  native_meaning TEXT, native_source TEXT, native_is_ai INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL, PRIMARY KEY (lexeme_id, ordinal));
CREATE TABLE sense_images (
  id INTEGER PRIMARY KEY, sense_id INTEGER NOT NULL REFERENCES senses(id), role TEXT NOT NULL,
  ordinal INTEGER NOT NULL, path TEXT NOT NULL, width INTEGER, height INTEGER, sha256 TEXT,
  license TEXT NOT NULL, license_url TEXT, author TEXT, attribution TEXT, page_url TEXT,
  semantic_score REAL, tags TEXT NOT NULL DEFAULT '[]');
CREATE INDEX ix_sense_images_sense ON sense_images(sense_id, ordinal);
CREATE TABLE field_status (
  lexeme_id INTEGER NOT NULL REFERENCES lexemes(id), field TEXT NOT NULL,
  status TEXT NOT NULL, missing TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (lexeme_id, field));
"""


class ExportError(ValueError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


# Spec 08: 同義詞與相關詞依關係詞本身的 CEFR 分級，A1～C2 每級 3 個.
_PER_LEVEL = {"synonyms", "related"}
_PER_LEVEL_MAX = 3


from .text import clean_native, offensive_native  # noqa: E402


def unfit_example(text: str) -> bool:
    """A sentence with a swear word or slur (問題回報 #92: phone's 「Fucking
    hell…」, apple's 「…Flash crap!」). Capitalized Dick is a name."""
    import re
    from .text import OFFENSIVE
    for tok in re.findall(r"[A-Za-z]+", text or ""):
        low = tok.lower()
        if low in OFFENSIVE and not (low == "dick" and tok[0].isupper()):
            return True
    return False


def unfit_relation(field: str, word: str, lemma: str) -> bool:
    """Relation words a learner should not see (問題回報 #89): offensive
    words, and sound/spelling neighbours that are not real look-alikes —
    patio's 「p t」, latte's 「law day」, natural light's 「natural high」,
    pan's 「an」."""
    from .text import OFFENSIVE
    w, head = word.lower().strip(), lemma.lower().strip()
    if w in OFFENSIVE or any(t in OFFENSIVE for t in w.split()):
        return True
    # 「st.」, 「Poaceae on Wikipedia.Wikipedia」; a capitalized word for a
    # lower-case headword is a name (book: Good Book, Word)
    if "." in w or not any(ch.isalpha() for ch in w) or (
            word[:1].isupper() and not lemma[:1].isupper()):  # also 📚 for book
        return True
    if field in ("homophones", "near_homophones", "similar_spelling"):
        parts = w.split()
        if len(w) <= 2 or any(len(t) == 1 for t in parts):
            return True
        if len(parts) > 1 and " " not in head:
            return True
        if " " in head and (set(parts) & set(head.split()) or len(parts) != len(head.split())):
            return True  # natural light: natural high; latte art: heart to heart
    return False


def per_level(found: list[tuple]) -> list[tuple]:
    """At most three shown words per CEFR level for synonyms and related
    words, those with a native meaning first, then in source order. Hidden
    (very rare) words are kept for the record; they are never shown."""
    keep, by_level = [], {}
    ranked = sorted(found, key=lambda x: (x[9], x[5] is None, x[0]))
    for item in ranked:
        level, hidden = item[8], item[9]
        if not hidden:
            if by_level.get(level, 0) >= _PER_LEVEL_MAX:
                continue
            by_level[level] = by_level.get(level, 0) + 1
        keep.append(item)
    return sorted(keep, key=lambda x: x[0])


def export(s: Session, target: str, native: str, *, include_audio: bool = True,
           fields: list[str] | None = None, idempotency_key: str | None = None) -> m.DictionaryRelease:
    if idempotency_key:
        found = s.execute(select(m.DictionaryRelease).where(
            m.DictionaryRelease.idempotency_key == idempotency_key)).scalar_one_or_none()
        if found is not None:
            return found
    if target not in catalog.LANGUAGES or native not in catalog.LANGUAGES or target == native:
        raise ExportError("target_language 和 native_language 必填且不可相同")
    rel = m.DictionaryRelease(target_language=target, native_language=native,
                              include_audio=include_audio, status="building",
                              idempotency_key=idempotency_key, checks=[])
    s.add(rel)
    s.flush()
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M")
    base = f"language-data-{target}-{native}-{stamp}"
    config.EXPORTS.mkdir(parents=True, exist_ok=True)
    final_dir = config.EXPORTS / base
    if final_dir.exists():
        base = f"{base}-{rel.id}"
        final_dir = config.EXPORTS / base
    tmp_dir = config.EXPORTS / f".tmp-{uuid.uuid4().hex}"
    tmp_dir.mkdir()
    savepoint = None
    try:
        db_path = tmp_dir / f"{base}.sqlite"
        counts, completeness, used_sources, audio_files = _build(
            s, db_path, target, native, fields, include_audio, tmp_dir)
        checks = _check(db_path, tmp_dir, include_audio)
        failed = [c for c in checks if c["level"] == "error"]
        rel.checks = checks
        if failed:
            raise ExportError("；".join(c["message"] for c in failed))
        sha = _sha256(db_path)
        # The same package as one JSON file for the Flutter app (all platforms).
        from .app_pack import build as build_pack
        pack_path = tmp_dir / f"{base}.json"
        pack_path.write_text(json.dumps(build_pack(db_path), ensure_ascii=False,
                                        separators=(",", ":")), encoding="utf-8")
        media = {"language": target, "files": audio_files}
        (tmp_dir / f"media-{target}.json").write_text(json.dumps(media, ensure_ascii=False,
                                                                 indent=1), encoding="utf-8")
        manifest = _manifest(s, target, native, base, sha, db_path, counts, completeness,
                             used_sources, audio_files, include_audio, checks)
        text = json.dumps(manifest, ensure_ascii=False, indent=1, default=str)
        (tmp_dir / "manifest.json").write_text(text, encoding="utf-8")
        # Record the release before the folder appears, so a database error
        # can't leave a finished-looking package behind.
        savepoint = s.begin_nested()
        rel.status, rel.file_name, rel.sha256 = "ready", base, sha
        rel.size_bytes = db_path.stat().st_size
        rel.manifest = json.loads(text)
        s.flush()
        savepoint.commit()
        os.replace(tmp_dir, final_dir)  # atomic: the folder appears complete or not at all
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if savepoint is not None and savepoint.is_active:
            savepoint.rollback()
        rel.status, rel.error = "failed", f"{type(e).__name__}: {e}"[:2000]
        rel.file_name = rel.sha256 = rel.manifest = None
    s.flush()
    return rel


def _values(s, target, native):
    out: dict[str, dict[str, m.FieldValue]] = {}
    for fv in s.execute(select(m.FieldValue).where(m.FieldValue.target_language == target,
                                                   m.FieldValue.native_language == native)
                        ).scalars():
        out.setdefault(fv.lemma, {})[fv.field] = fv
    return out


def _build(s, db_path, target, native, fields, include_audio, tmp_dir):
    con = sqlite3.connect(db_path)
    con.executescript(DDL)  # foreign keys are checked after the build (PRAGMA foreign_key_check)
    values = _values(s, target, native)
    want = set(fields) if fields else None

    def items(lemma, f):
        if want is not None and f not in want:
            return []
        fv = values[lemma].get(f)
        return fv.items if fv is not None else []

    counts = {k: 0 for k in ("lexemes", "stubs", "senses", "sense_translations", "forms",
                             "morphemes", "morpheme_translations",
                             "pronunciations", "audio", "examples", "example_translations",
                             "relations", "relation_translations", "etymologies", "images")}
    used_sources: dict[str, int] = {}
    audio_ids: dict[int, dict] = {}
    stub_ids: set[int] = set()
    exported: set[int] = set()

    def used(src, n=1):
        if src:
            used_sources[src] = used_sources.get(src, 0) + n

    for lemma, fvs in sorted(values.items()):
        lexemes = s.execute(select(m.Lexeme).where(m.Lexeme.language == target,
                                                   m.Lexeme.normalized == lemma,
                                                   m.Lexeme.status == "full")).scalars().all()
        if not lexemes:
            continue
        by_pos = {lx.pos: lx for lx in lexemes}
        main = next((by_pos[i["pos"]] for i in items(lemma, "pos") if i.get("pos") in by_pos),
                    lexemes[0])
        for lx in lexemes:
            con.execute("INSERT INTO lexemes VALUES (?,?,?,?,?,?,?,?)",
                        (lx.id, lx.language, lx.lemma, lx.normalized, lx.pos, "full", lx.cefr,
                         lx.zipf))
            exported.add(lx.id)
            counts["lexemes"] += 1
            for f, fv in fvs.items():
                if want is None or f in want:
                    con.execute("INSERT INTO field_status VALUES (?,?,?,?)",
                                (lx.id, f, fv.status, json.dumps(fv.missing or [])))
        ids = [lx.id for lx in lexemes]
        # senses + translations
        native_def = {i.get("sense_key") or i.get("slot"): i for i in items(lemma, "native_definition")}
        sense_id_by_key: dict[str, int] = {}
        ord_by_lx: dict[int, int] = {}
        for it in items(lemma, "definition"):
            sk = it.get("sense_key") or it.get("key")
            sense = s.execute(select(m.Sense).where(m.Sense.lexeme_id.in_(ids),
                                                    m.Sense.sense_key == sk)).scalars().first()
            if sense is None:
                continue
            n = ord_by_lx.get(sense.lexeme_id, 0)
            ord_by_lx[sense.lexeme_id] = n + 1
            con.execute("INSERT INTO senses VALUES (?,?,?,?,?,?,?)",
                        (sense.id, sense.lexeme_id, n, it.get("gloss", ""),
                         it.get("gloss_language") or target, json.dumps(it.get("labels") or []),
                         it.get("source", "")))
            used(it.get("source"))
            counts["senses"] += 1
            sense_id_by_key[sk] = sense.id
            tr = native_def.get(sk)
            if tr and clean_native(tr.get("text")):
                con.execute("INSERT INTO sense_translations VALUES (?,?,?,?,?)",
                            (sense.id, clean_native(tr["text"]), tr.get("source", ""),
                             int(bool(tr.get("ai"))),
                             int(tr.get("source") == "user")))
                used(tr.get("source"))
                counts["sense_translations"] += 1
        # forms
        from .materialize import FORM_POS, british_first, main_accent
        from .text import normalize_lemma
        for f in catalog.FORM_FIELDS:
            lx = by_pos.get(FORM_POS.get(f, "")) or (by_pos.get("noun") if FORM_POS.get(f) == "adj"
                                                    else None)
            if lx is None:
                continue
            seen = set()
            for it in items(lemma, f):
                form = it.get("form")
                if form and form not in seen:
                    seen.add(form)
                    con.execute("INSERT INTO forms VALUES (?,?,?,?,?,?)",
                                (lx.id, f, form, normalize_lemma(form, target),
                                 _label(f"form:{f}", native), it.get("source", "")))
                    used(it.get("source"))
                    counts["forms"] += 1
        # pronunciations + audio
        audio_rows = []
        for it in items(lemma, "audio"):
            if it.get("tts"):
                audio_rows.append((None, it))
                continue
            asset = s.execute(select(m.AudioAsset).where(
                m.AudioAsset.source_url == it.get("url"))).scalar_one_or_none()
            if asset is not None and asset.status == "ready":
                audio_rows.append((asset, it))
                if asset.id not in audio_ids:
                    audio_ids[asset.id] = {"path": asset.path, "sha256": asset.sha256,
                                           "bytes": asset.size_bytes, "mime": asset.mime}
                    con.execute("INSERT INTO audio VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (asset.id, asset.path, asset.sha256, asset.mime, asset.accent,
                                 asset.speaker, asset.license, asset.attribution,
                                 asset.source_url, asset.duration_s))
                    counts["audio"] += 1
                    if include_audio:
                        src = config.MEDIA / asset.path
                        dst = tmp_dir / "media" / asset.path
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        if src.exists():
                            shutil.copy2(src, dst)
        for lx in lexemes:
            n = 0
            for kind in ("ipa", "phonemes", "syllables", "stress"):
                rows = items(lemma, kind)
                for i, it in enumerate(british_first(rows) if kind == "ipa" else rows):
                    val = (it.get("ipa") or it.get("phonemes") or "·".join(it.get("syllables") or [])
                           or str(it.get("count") or it.get("pattern")
                                  or it.get("primary_syllable") or ""))
                    acc = main_accent(it.get("accent"))
                    con.execute("INSERT INTO pronunciations VALUES (?,?,?,?,?,?,?,?)",
                                (lx.id, kind, val, acc, None, int(i == 0), it.get("source", ""), n))
                    used(it.get("source"))
                    n += 1
            first = True
            for asset, it in british_first(audio_rows, lambda r: r[0].accent if r[0] else "~",
                                           lambda r: ""):
                con.execute("INSERT INTO pronunciations VALUES (?,?,?,?,?,?,?,?)",
                            (lx.id, "tts" if asset is None else "audio",
                             it.get("locale", "") if asset is None else "",
                             None if asset is None else asset.accent,
                             None if asset is None else asset.id,
                             int(first and asset is not None), it.get("source", ""), n))
                first = first and asset is None
                n += 1
                used(it.get("source"))
            counts["pronunciations"] += n
        # examples + translations
        ex_tr = {i.get("example_key") or i.get("slot"): i for i in items(lemma, "example_translation")}
        ex_sense = {i.get("example_key"): i.get("sense_key") for i in items(lemma, "example_sense")}
        ex_level = {i.get("example_key"): i.get("level") for i in items(lemma, "example_difficulty")}
        for n, it in enumerate(items(lemma, "example_sentences")):
            k = it.get("key") or example_key(it.get("text", ""))
            ex = s.execute(select(m.Example).where(
                m.Example.lexeme_id.in_(ids),
                m.Example.text_hash == text_hash(it.get("text", "")))).scalars().first()
            if ex is None:
                continue
            if unfit_example(it.get("text", "")) or offensive_native(
                    (ex_tr.get(k) or {}).get("text")):
                continue
            sid = sense_id_by_key.get(ex_sense.get(k) or it.get("sense_key") or "")
            # The learner pack has no UI for an unresolved usage. Keep such
            # examples in the master database for review, but never flatten
            # them into a card where they could illustrate the wrong sense.
            if sid is None:
                continue
            con.execute("INSERT INTO examples VALUES (?,?,?,?,?,?,?,?,?)",
                        (ex.id, ex.lexeme_id, sid, ex.text, ex_level.get(k), it.get("source", ""),
                         ex.source_record_id, ex.license, n))
            used(it.get("source"))
            counts["examples"] += 1
            tr = ex_tr.get(k)
            if tr and tr.get("text"):
                con.execute("INSERT INTO example_translations VALUES (?,?,?,?)",
                            (ex.id, tr["text"], tr.get("source", ""), int(bool(tr.get("ai")))))
                used(tr.get("source"))
                counts["example_translations"] += 1
        # relations + native meanings
        derived_pos = {i["word"].lower(): i.get("pos") for i in items(lemma, "derived_pos")
                       if i.get("word")}
        # The headword's own forms are not relation words (spec 08: 詞條本身
        # 的詞形不算; apple's derived terms must not list apples).
        own_forms = {lemma.lower()} | {(it.get("form") or "").lower()
                                       for ff in catalog.FORM_FIELDS for it in items(lemma, ff)}
        for f in catalog.RELATION_FIELDS + ["derived_terms"]:
            nat_field = "derived_native_meaning" if f == "derived_terms" else f"{f}_native"
            meanings = {(i.get("word") or i.get("slot") or "").lower(): i
                        for i in items(lemma, nat_field)}
            found = []
            for n, it in enumerate(items(lemma, f)):
                w = (it.get("word") or "").lower()
                if w in own_forms or unfit_relation(f, it.get("word") or "", lemma):
                    continue
                row = s.execute(select(m.LexemeRelation).where(
                    m.LexemeRelation.lexeme_id.in_(ids), m.LexemeRelation.relation == f,
                    func.lower(m.LexemeRelation.target_word) == w)).scalars().first()
                if row is None:
                    continue
                tgt = s.get(m.Lexeme, row.target_lexeme_id)
                if tgt is None:
                    continue
                detail = row.detail or {}
                target_zipf = tgt.zipf if tgt.zipf is not None else detail.get("zipf")
                hidden = bool(detail.get("hide_by_default") or
                              (target_zipf is not None and target_zipf < 2.5))
                found.append((n, it, w, row, tgt, meanings.get(w), detail, target_zipf,
                              tgt.cefr or detail.get("cefr"), hidden))
            if f in _PER_LEVEL:
                found = per_level(found)
            for n, it, w, row, tgt, mean, detail, target_zipf, target_cefr, hidden in found:
                if tgt.id not in exported and tgt.id not in stub_ids:
                    stub_ids.add(tgt.id)
                con.execute("INSERT INTO relations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (row.id, row.lexeme_id, f, tgt.id, row.target_word,
                             derived_pos.get(w) or it.get("pos") or (tgt.pos if tgt.pos != "unknown"
                                                                    else None),
                             row.source_sense_id if row.source_sense_id in sense_id_by_key.values()
                             else None, row.strength, json.dumps(row.detail or {},
                                                                 ensure_ascii=False),
                             clean_native(mean.get("text")) if mean else None,
                             mean.get("source") if mean else None,
                             int(bool(mean and mean.get("ai"))), it.get("source", ""), n,
                             target_cefr, target_zipf, detail.get("rarity"), int(hidden)))
                used(it.get("source"))
                counts["relations"] += 1
                if mean:
                    counts["relation_translations"] += 1
                    used(mean.get("source"))
        # 構詞拆解
        bd = (items(lemma, "morphemes") or [None])[0]
        if bd:
            nat = {i.get("slot"): i for i in items(lemma, "morphemes_native")}
            for lx in lexemes:
                for n, p in enumerate(bd.get("parts", [])):
                    tr = nat.get(f"{n}:{p.get('part', '')}")
                    con.execute("INSERT INTO morphemes VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (lx.id, n, p.get("part", ""), p.get("kind", "root"),
                                 p.get("meaning"), int(bool(p.get("free"))),
                                 clean_native(tr.get("text")) if tr else None,
                                 tr.get("source") if tr else None,
                                 int(bool(tr and tr.get("ai"))), bd.get("source", "")))
                    counts["morphemes"] += 1
                    counts["morpheme_translations"] += bool(tr)
            used(bd.get("source"))
        # etymology
        ety = {k: [i.get("morpheme") for i in items(lemma, k)] for k in ("root", "prefix", "suffix")}
        origin = (items(lemma, "origin_language") or [{}])[0].get("language")
        orig_form = (items(lemma, "original_form") or [{}])[0].get("form")
        text = (items(lemma, "etymology_text") or [{}])[0].get("text")
        nat = (items(lemma, "etymology_native") or [{}])[0]
        if any(ety.values()) or origin or orig_form or text:
            for lx in lexemes:
                con.execute("INSERT INTO etymology VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (lx.id, json.dumps(ety["root"], ensure_ascii=False),
                             json.dumps(ety["prefix"], ensure_ascii=False),
                             json.dumps(ety["suffix"], ensure_ascii=False), origin, orig_form,
                             text, nat.get("text"), nat.get("source"), int(bool(nat.get("ai")))))
                counts["etymologies"] += 1
    # Stub lexemes that relations point to (not exported as full entries)
    for sid in sorted(stub_ids - exported):
        lx = s.get(m.Lexeme, sid)
        # Not a full entry in this package: a link target only.
        con.execute("INSERT INTO lexemes VALUES (?,?,?,?,?,?,?,?)",
                    (lx.id, lx.language, lx.lemma, lx.normalized, lx.pos, "stub", lx.cefr,
                     lx.zipf))
        counts["stubs"] += 1
    for r in s.execute(select(m.LexemeRedirect)).scalars():
        if r.new_id in exported or r.new_id in stub_ids:
            con.execute("INSERT INTO lexeme_redirects VALUES (?,?)", (r.old_id, r.new_id))
    for key, texts in catalog.LABELS.items():
        if texts.get(native):
            con.execute("INSERT INTO labels VALUES (?,?)", (key, texts[native]))
    for f in catalog.FIELDS:
        con.execute("INSERT OR IGNORE INTO labels VALUES (?,?)", (f"field:{f.key}", f.label
                                                                  if native == "zh-TW" else f.key))
    con.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    con.execute("INSERT INTO meta VALUES ('target_language', ?)", (target,))
    con.execute("INSERT INTO meta VALUES ('native_language', ?)", (native,))
    con.execute("INSERT INTO meta VALUES ('created_at', ?)",
                (datetime.now(timezone.utc).isoformat(),))
    image_files = _images(s, con, tmp_dir, counts)
    con.commit()
    con.close()
    completeness = {}
    for f in catalog.fields_for(target):
        if want is not None and f.key not in want:
            continue
        sts = [fvs[f.key].status for fvs in values.values() if f.key in fvs]
        if sts:
            ok = sum(st in catalog.DONE for st in sts)
            completeness[f.key] = {"complete": ok, "total": len(sts),
                                   "rate": round(ok / len(sts), 3)}
    audio_files = [{"id": k, **v} for k, v in sorted(audio_ids.items())]
    audio_files += image_files
    return counts, completeness, used_sources, audio_files


def _images(s, con, tmp_dir: Path, counts) -> list[dict]:
    """Approved sense pictures (spec: 已核准詞義圖片清單): the thumbnail the
    app shows, each picture's licence and author, and its AI labels."""
    files = []
    for r in s.execute(sql_text("""
            SELECT si.id, si.sense_id, si.role, si.ordinal, si.semantic_score, a.path,
                   a.thumbnail_path, a.width, a.height, a.license_code, a.license_url, a.author,
                   a.attribution, a.page_url, a.tags
            FROM sense_images si JOIN image_assets a ON a.id = si.image_asset_id
            WHERE si.review_status = 'approved' AND a.status = 'ready'
            ORDER BY si.sense_id, si.role <> 'representative', si.ordinal, si.id""")).mappings():
        if not con.execute("SELECT 1 FROM senses WHERE id = ?", (r["sense_id"],)).fetchone():
            continue
        rel = r["thumbnail_path"] or r["path"]
        src = config.MEDIA / rel
        if not src.exists():
            continue
        dst = tmp_dir / "media" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        sha = _sha256(dst)
        con.execute("INSERT INTO sense_images VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r["id"], r["sense_id"], r["role"], r["ordinal"], rel.replace("\\", "/"),
                     r["width"], r["height"], sha, r["license_code"], r["license_url"], r["author"],
                     r["attribution"], r["page_url"], r["semantic_score"],
                     json.dumps(r["tags"] or [], ensure_ascii=False)))
        counts["images"] += 1
        files.append({"kind": "image", "id": r["id"], "path": rel.replace("\\", "/"),
                      "sha256": sha, "license": r["license_code"], "author": r["author"],
                      "page_url": r["page_url"]})
    return files


def _label(key, native):
    return catalog.LABELS.get(key, {}).get(native)


def _check(db_path: Path, folder: Path, include_audio: bool) -> list[dict]:
    checks = []

    def add(name, ok, message, level="error"):
        checks.append({"check": name, "ok": ok, "message": message,
                       "level": "ok" if ok else level})

    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        add("readable", integrity == "ok", f"SQLite 可讀取（integrity_check: {integrity}）")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        add("foreign_keys", not fk, "外鍵完整" if not fk else f"{len(fk)} 筆外鍵錯誤：{fk[:5]}")
        n = con.execute("SELECT count(*) FROM lexemes WHERE status = 'full'").fetchone()[0]
        add("has_entries", n > 0, f"{n} 個正式詞條" if n else "沒有任何詞條（先執行擷取工作）")
        bad = con.execute("SELECT count(*) FROM lexemes WHERE lemma = '' OR pos = ''").fetchone()[0]
        add("required_fields", bad == 0, "詞條必要欄位齊全" if not bad else f"{bad} 個詞條缺拼字或詞性")
        empty = con.execute("SELECT count(*) FROM senses WHERE definition = ''").fetchone()[0]
        add("definitions", empty == 0, "每個 sense 都有釋義" if not empty else f"{empty} 個 sense 沒有釋義")
        nosense = con.execute("SELECT count(*) FROM lexemes l WHERE status = 'full' AND NOT EXISTS"
                              " (SELECT 1 FROM senses s WHERE s.lexeme_id = l.id)").fetchone()[0]
        add("senses", nosense == 0, "每個正式詞條至少一個 sense" if not nosense
            else f"{nosense} 個詞條沒有 sense", level="warning")
        orphan_tr = con.execute("SELECT count(*) FROM example_translations t LEFT JOIN examples e"
                                " ON e.id = t.example_id WHERE e.id IS NULL").fetchone()[0]
        add("translation_pairs", orphan_tr == 0, "例句翻譯都配對到例句" if not orphan_tr
            else f"{orphan_tr} 筆例句翻譯沒有對應例句")
        orphan_audio = con.execute("SELECT count(*) FROM audio a WHERE NOT EXISTS (SELECT 1 FROM"
                                   " pronunciations p WHERE p.audio_id = a.id)").fetchone()[0]
        add("orphan_audio", orphan_audio == 0, "沒有孤立音檔" if not orphan_audio
            else f"{orphan_audio} 個音檔沒有詞條使用")
        if include_audio:
            missing = [r[0] for r in con.execute("SELECT path FROM audio")
                       if not (folder / "media" / r[0]).exists()]
            add("audio_files", not missing, "音檔路徑都可解析" if not missing
                else f"{len(missing)} 個音檔找不到：{missing[:3]}")
        pics = con.execute("SELECT path, license FROM sense_images").fetchall()
        lost = [p for p, _ in pics if not (folder / "media" / p).exists()]
        bad = [p for p, lic in pics if not lic]
        add("image_files", not lost and not bad,
            f"{len(pics)} 張已核准圖片路徑與授權都可解析" if not lost and not bad
            else f"{len(lost)} 張圖片找不到、{len(bad)} 張缺授權")
        add("card_template", True, "尚未發布字卡版型（manifest 記為 null）", level="ok")
        con.close()
    except sqlite3.Error as e:
        add("readable", False, f"SQLite 無法讀取：{e}")
    return checks


def _manifest(s, target, native, base, sha, db_path, counts, completeness, used_sources,
              audio_files, include_audio, checks):
    snaps = [{"source": r.source, "language": r.language, "version": r.version,
              "sha256": r.sha256, "retrieved_at": r.retrieved_at}
             for r in s.execute(select(m.SourceSnapshot).where(
                 m.SourceSnapshot.active.is_(True))).scalars()]
    pols = s.execute(select(m.SourcePolicy.field, m.SourcePolicy.version).where(
        m.SourcePolicy.target_language == target, m.SourcePolicy.native_language == native)).all()
    policy_versions = {f: v for f, v in sorted(pols)}
    policy_hash = hashlib.sha256(json.dumps(policy_versions, sort_keys=True).encode()).hexdigest()
    ai = sum(n for src, n in used_sources.items() if src == "ai_translate")
    return {
        "schema_version": SCHEMA_VERSION, "target_language": target, "native_language": native,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": {"file": f"{base}.sqlite", "sha256": sha, "bytes": db_path.stat().st_size},
        "media_list": {"file": f"media-{target}.json", "count": len(audio_files),
                       "included": include_audio},
        "app_pack": {"file": f"{base}.json",
                     "sha256": _sha256(db_path.with_suffix(".json"))},
        "source_snapshots": snaps,
        "policy_versions": policy_versions, "policy_hash": policy_hash,
        "card_template_version": None,
        "counts": counts, "completeness": completeness,
        "licenses": [{"source": src, "name": catalog.SOURCES[src].name,
                      "license": catalog.SOURCES[src].license,
                      "attribution": catalog.SOURCES[src].attribution, "values": n}
                     for src, n in sorted(used_sources.items()) if src in catalog.SOURCES],
        "ai_values": ai, "checks": checks,
    }
