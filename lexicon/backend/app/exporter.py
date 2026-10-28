"""Export for Flutter: one read-only SQLite per language direction, the
target language's audio media list, and manifest.json.

Content is what *this direction's* policies adopted (field_values for
target + native); ids are the stable dictionary ids (lexemes, senses,
examples, relations). Built in a temp folder, checked (foreign keys,
orphan audio, required fields, translation pairing, readability), then
renamed into place — a failed export leaves nothing that looks finished.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import re
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
from .quality import example_other_pos_only
from .function_words import is_noisy_function_word_relation
from .text import example_key, text_hash, is_column_word_list

SCHEMA_VERSION = 5  # 5: per-sense register (neutral / written / spoken / slang)

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
  labels TEXT NOT NULL DEFAULT '[]', register TEXT, source TEXT NOT NULL);
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
  duration_s REAL, source_page TEXT, source TEXT);
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


_media_sha: dict[str, tuple[int, int, str]] = {}


def _media_sha256(path: Path) -> str:
    """A media file's hash, re-read only when its size or mtime changes (card #380:
    every live pack hashed all 32,000 pictures again)."""
    st = path.stat()
    hit = _media_sha.get(str(path))
    if hit and hit[:2] == (st.st_size, st.st_mtime_ns):
        return hit[2]
    sha = _sha256(path)
    _media_sha[str(path)] = (st.st_size, st.st_mtime_ns, sha)
    return sha


# Spec 08: 同義詞與相關詞依關係詞本身的 CEFR 分級，A1～C2 每級 3 個.
_PER_LEVEL = {"synonyms", "related"}
_PER_LEVEL_MAX = 3


from .text import (STORE_UNSAFE_LABELS, clean_native, fr_unfit_text, offensive_native,  # noqa: E402
                   repair_learner_gloss, sense_native, unsafe_gloss)


# Whole-token swears the exact OFFENSIVE list misses (bitches, shite,
# fuckjuice). Same shape as scan_library's example/relation check.
_PROFANE_TOKEN = re.compile(
    r"^(?:fuck\w*|shit\w*|bitch\w*|cunt|dick|asshole|bastard|crap|whore|slut|nigger|faggot|retard\w*)$",
    re.I,
)
# Stem inside a compound (assfuck, dickhead, whorehouse). Not a substring
# of an ordinary word: dicker, dickey, benedick stay.
_PROFANE_STEM = re.compile(r"fuck|shit|bitch|cunt|slut|whore|nigger|nigga|faggot", re.I)
_DICK_SLUR = re.compile(
    r"dick(?:head|weed|wad|face|ride|stain|matize|tatorship)|(?:limp|tenta)dick",
    re.I,
)
_NOT_PROFANE = {
    "dicker", "dickey", "dicky", "dickie", "benedick", "benedict",
    "dickens", "dickinson", "dickenson",
}


def profane_token(token: str, *, name_dick: bool = False) -> bool:
    """True when this token is a swear or a swear compound."""
    from .text import OFFENSIVE
    raw = token or ""
    low = raw.lower()
    if not low or low in _NOT_PROFANE:
        return False
    if name_dick and low == "dick" and raw[:1].isupper():
        return False
    if low in OFFENSIVE or _PROFANE_TOKEN.fullmatch(low):
        return True
    # Plurals of listed words (卡 #226 r112: 「dildos」「fags」「cocks」 got through).
    if low.endswith("s") and (low[:-1] in OFFENSIVE or low.endswith("es") and low[:-2] in OFFENSIVE):
        return True
    return bool(_PROFANE_STEM.search(low) or _DICK_SLUR.search(low))


def _headword_forms(lemma: str) -> set[str]:
    """Inflections of the headword itself. A vulgar entry may use its own
    word in an example (slut / sluts); other entries may not."""
    w = (lemma or "").lower().strip()
    if not w:
        return set()
    forms = {w, w + "s", w + "es"}
    if len(w) > 1 and w.endswith("y") and w[-2] not in "aeiou":
        forms.add(w[:-1] + "ies")
    return forms


def unfit_example(text: str, lemma: str = "") -> bool:
    """A sentence with a swear word or slur (問題回報 #92: phone's 「Fucking
    hell…」, apple's 「…Flash crap!」, creditor's 「sons of bitches」).
    Capitalized Dick is a name. The headword's own inflections are allowed."""
    allowed = _headword_forms(lemma)
    for tok in re.findall(r"[A-Za-z]+", text or ""):
        if tok.lower() in allowed:
            continue
        if profane_token(tok, name_dick=True):
            return True
    return False


# 問題回報 #484: a headword that only ever appears as a name ("Brown" the surname,
# "Miss Smith", "Harry Potter", "Polish exams" = Polish, not polish). Place names keep
# the example (Pacific Ocean, Crater Lake, Western Europe).
_PLACE_WORDS = {
    "ocean", "sea", "river", "island", "islands", "lake", "mount", "mountain", "mountains",
    "bay", "gulf", "canal", "strait", "valley", "desert", "peninsula", "county", "province",
    "state", "states", "street", "road", "avenue", "square", "park", "falls", "city",
    "europe", "asia", "africa", "america", "australia", "antarctica", "pacific", "atlantic", "pole",
    "indian", "arctic", "japan", "china", "korea", "taiwan", "england", "france", "germany",
}
_NAME_TITLES = {"mr", "mrs", "ms", "miss", "dr", "professor", "prof", "sir", "madam", "uncle",
                "aunt", "captain", "president", "saint", "st", "queen", "king", "prince", "princess"}


def _run_gap(gap: str, prev_word: str) -> bool:
    """Words in one capitalised run are separated by spaces; 「Mr. Gravity」 keeps its dot."""
    return bool(re.fullmatch(r"\s*", gap)) or (
        bool(re.fullmatch(r"\.\s*", gap)) and prev_word.lower() in _NAME_TITLES)


def proper_noun_example(text: str, lemma: str = "") -> bool:
    """True when every use of the headword in the sentence is a capitalised name
    (問題回報 #484): a capital mid-sentence, a title before it, or a sentence-initial
    capital that is followed by another capital. A capitalised run with a place word
    is a place (地名保留). A sentence-initial capital alone is not evidence (Happy, Sure)."""
    forms = _headword_forms(lemma)
    if not forms or not text or lemma[:1].isupper():
        return False  # a proper-noun headword (Polish the nationality) keeps its capitals
    toks = list(re.finditer(r"[A-Za-z]+", text))
    names = 0
    for i, m in enumerate(toks):
        if m.group().lower() not in forms:
            continue
        w = m.group()
        if not w[0].isupper() or (w.isupper() and len(w) > 1):
            return False  # used as an ordinary word somewhere in the sentence
        lo, hi = i, i  # the capitalised run around the headword: 「Crater Lake」, 「Mr. Gravity」
        while lo > 0 and toks[lo - 1].group()[0].isupper() and _run_gap(text[toks[lo - 1].end():toks[lo].start()], toks[lo - 1].group()):
            lo -= 1
        while hi + 1 < len(toks) and toks[hi + 1].group()[0].isupper() and re.fullmatch(r"\s*", text[toks[hi].end():toks[hi + 1].start()]):
            hi += 1
        run = [t.group() for t in toks[lo:hi + 1]]
        if any(t.lower() in _PLACE_WORDS for t in run):
            return False
        before = text[:toks[lo].start()].rstrip()
        if any(t.lower() in _NAME_TITLES for t in run[:i - lo]):
            names += 1
        elif before and before[-1] not in ".!?\"“:":
            names += 1  # a capital in the middle of a sentence
        elif len(run) > 1:
            names += 1  # sentence-initial 「Mark Zuckerberg」, 「Chuck Norris」
        else:
            return False  # a sentence-initial capital alone is not evidence of a name
    return names > 0


def unfit_relation(field: str, word: str, lemma: str) -> bool:
    """Relation words a learner should not see (問題回報 #89): offensive
    words, and sound/spelling neighbours that are not real look-alikes —
    patio's 「p t」, latte's 「law day」, natural light's 「natural high」,
    pan's 「an」."""
    w, head = word.lower().strip(), lemma.lower().strip()
    if any(profane_token(tok) for tok in re.findall(r"[A-Za-z]+", word or "")):
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


_CONFUSABLE = ("near_homophones", "similar_spelling")  # the app's 「容易混淆的字」 section
_ZH_NOISE = re.compile(r"[\s。．.、，,；;：:！!？?「」『』\"'“”()（）]")


def zh_key(text: str | None) -> str:
    """A Chinese gloss without spaces and punctuation, to compare two glosses."""
    return _ZH_NOISE.sub("", text or "")


def _spelling_key(word: str) -> str:
    """British/American spellings map to one key: colour/color, centre/center, realise/realize."""
    w = word.lower()
    w = re.sub(r"(?<=[bclmnpstvgdkz])our", "or", w)
    w = w.replace("ise", "ize").replace("xion", "ction")
    if len(w) >= 5 and w.endswith("ce"):
        w = w[:-2] + "se"  # defence/defense, licence/license
    if len(w) >= 5 and w.endswith("re"):
        w = w[:-2] + "er"
    return w


def confusable_problem(word: str, head: str, target, zh: str | None,
                       head_zh: set[str]) -> str | None:
    """Why a 「容易混淆的字」 row is not shown to learners (問題回報 #420), or None.
    not_in_lexicon: the word is only a link stub, a learner cannot open it; same_meaning: its
    Chinese is the headword's own meaning (gulp→gul 「一口量」); spelling_variant: another
    spelling of the headword (color→colour), not a confusable word. Names and swear words
    are already dropped by unfit_relation."""
    if target.status != "full":
        return "not_in_lexicon"
    if zh and zh_key(zh) in head_zh:
        return "same_meaning"
    if word.lower() != head.lower() and _spelling_key(word) == _spelling_key(head):
        return "spelling_variant"
    return None


def _phoneme_key(value) -> str:
    if isinstance(value, (list, tuple)):
        value = " ".join(map(str, value))
    return re.sub(r"\d", "", str(value or "")).lower().replace(" ", "")


def homophone_problem(word: str, head: str, detail: dict, zipf, head_phonemes: set, their_phonemes: set, target=None) -> str | None:
    """Why a 同音字 row is hidden (問題回報 #526): only a common word that sounds the same is
    worth showing. rare: rarity worse than less_common (blue→bleu); spelling_variant: British
    spelling of the headword (connexion); not_same_sound: the phonemes differ (ear→air)."""
    if target is not None and target.status != "full":
        return "not_in_lexicon"  # a link stub, often a name (marc, kane, d'or)
    rarity = detail.get("rarity")
    if rarity in ("uncommon", "rare", "very_rare") or zipf is None or zipf < 4.0:
        return "rare"
    if word.lower() != head.lower() and _spelling_key(word) == _spelling_key(head):
        return "spelling_variant"
    if head_phonemes and their_phonemes and not (head_phonemes & their_phonemes):
        return "not_same_sound"
    return None


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
           fields: list[str] | None = None, idempotency_key: str | None = None,
           store_safe: bool = False) -> m.DictionaryRelease:
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
            s, db_path, target, native, fields, include_audio, tmp_dir, store_safe)
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
        # Windows keeps a directory rename from completing while any sqlite3
        # connection opened under tmp_dir (_build/_check/app_pack.build) is
        # still alive only by a reference cycle, not a missing close(): a
        # forced collect (問題回報 #217 debugging) reliably clears it before
        # the rename, instead of os.replace racing the cyclic GC.
        gc.collect()
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


def _build(s, db_path, target, native, fields, include_audio, tmp_dir, store_safe=False,
           copy_media=True):
    con = sqlite3.connect(db_path)
    con.executescript(DDL)  # foreign keys are checked after the build (PRAGMA foreign_key_check)
    values = _values(s, target, native)
    want = set(fields) if fields else None
    # Keep strong references and indexes for this snapshot. Per-candidate SELECTs
    # and Session.get() used over 100,000 round trips on a modest live pack.
    lexeme_by_id = {lx.id: lx for lx in s.scalars(select(m.Lexeme).order_by(m.Lexeme.id))}
    lexemes_by_lemma = {}
    for lx in lexeme_by_id.values():
        if lx.language == target and lx.status == 'full' and lx.normalized in values:
            lexemes_by_lemma.setdefault(lx.normalized, []).append(lx)
    full_ids = [lx.id for entries in lexemes_by_lemma.values() for lx in entries]

    def index_rows(model, key):
        index = {}
        for row in s.scalars(select(model).where(model.lexeme_id.in_(full_ids)).order_by(model.id)):
            index.setdefault((row.lexeme_id, key(row)), row)
        return index

    senses_index = index_rows(m.Sense, lambda row: row.sense_key)
    # Explicit reviewed translations must survive export even when the resolved
    # field still contains the original dictionary text (card #673).
    translation_overrides = {row.sense_id: row for row in s.scalars(
        select(m.SenseTranslation).where(
            m.SenseTranslation.native_language == native,
            m.SenseTranslation.is_override.is_(True)))}
    examples_index = index_rows(m.Example, lambda row: row.text_hash)
    relations_index = index_rows(m.LexemeRelation,
                                lambda row: (row.relation, row.target_word.lower()))
    forms_by_lexeme: dict[int, set[str]] = {}
    for lxid, form in s.execute(select(m.Form.lexeme_id, m.Form.form).where(m.Form.lexeme_id.in_(full_ids))):
        forms_by_lexeme.setdefault(lxid, set()).add(form)
    audio_by_url = {row.source_url: row for row in s.scalars(select(m.AudioAsset))}
    # 問題回報 #797 / card #677: ai_translate and the Qwen fill write example
    # translations only to example_translations (field_values has none), so the
    # export falls back to that table when the field value is missing.
    table_ex_tr = {row.example_id: row for row in s.scalars(select(m.ExampleTranslation).where(
        m.ExampleTranslation.native_language == native))}

    def first_for_ids(index, ids, key):
        matches = [index[(lxid, key)] for lxid in ids if (lxid, key) in index]
        return min(matches, key=lambda row: row.id) if matches else None

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

    has_sense = {lexeme_id for lexeme_id, _ in senses_index}
    for lemma, fvs in sorted(values.items()):
        lexemes = lexemes_by_lemma.get(lemma, [])
        # 問題回報 #303: a full lexeme without any sense (a part of speech whose
        # senses were all filtered) is a blank row in the app. Leave it out;
        # a relation that points at it still gets a stub link target below.
        blank = [lx for lx in lexemes if lx.id not in has_sense]
        if blank:
            counts["lexemes_without_senses"] = counts.get("lexemes_without_senses", 0) + len(blank)
            lexemes = [lx for lx in lexemes if lx.id in has_sense]
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
        registers = {i.get("sense_key") or i.get("slot"): i for i in items(lemma, "register")}
        sense_id_by_key: dict[str, int] = {}
        sense_lexeme: dict[int, int] = {}
        head_zh: set[str] = set()  # the headword's own Chinese meanings (問題回報 #420)
        ord_by_lx: dict[int, int] = {}
        # 問題回報 #389: number the senses by senses.ordinal (materialize's
        # order_senses, card352_reorder.py), not by the definition item order,
        # which keeps the source's historical order (assiette's plate was 5th).
        matched = []
        for it in items(lemma, "definition"):
            sk = it.get("sense_key") or it.get("key")
            sense = first_for_ids(senses_index, ids, sk)
            if sense is not None:
                matched.append((it, sk, sense))
        matched.sort(key=lambda t: t[2].ordinal)  # stable: equal ordinals keep item order
        for it, sk, sense in matched:
            n = ord_by_lx.get(sense.lexeme_id, 0)
            ord_by_lx[sense.lexeme_id] = n + 1
            reg = registers.get(sk) or {}
            tr = native_def.get(sk)
            override = translation_overrides.get(sense.id)
            if override is not None and (want is None or "native_definition" in want):
                tr = {"text": override.text, "source": override.source,
                      "ai": override.is_ai}
            labels = list(it.get("labels") or [])
            # 卡 #524: a sexual/excretory definition without a dictionary label counts as vulgar.
            if target != "en" and not (set(labels) & STORE_UNSAFE_LABELS) and unsafe_gloss(it.get("gloss")):
                labels.append("vulgar")
                reg = {**reg, "register": "vulgar"}
                counts["senses_gloss_vulgar"] = counts.get("senses_gloss_vulgar", 0) + 1
            # App Store build (問題回報 #271): drop vulgar/offensive/derogatory senses. Their
            # examples vanish too, since an example without a sense is skipped.
            if store_safe and (set(labels) & STORE_UNSAFE_LABELS
                               or reg.get("register") in STORE_UNSAFE_LABELS):
                counts["senses_filtered"] = counts.get("senses_filtered", 0) + 1
                continue
            gloss_zh = repair_learner_gloss(it.get("gloss") or "", tr.get("text") if tr else None)
            native_text, vulgar = sense_native(gloss_zh, labels)
            register = reg.get("register")
            if vulgar:  # keep coarse words, flag them 粗俗 (never drop)
                register = "vulgar"
                if "vulgar" not in labels:
                    labels.append("vulgar")
            con.execute("INSERT INTO senses VALUES (?,?,?,?,?,?,?,?)",
                        (sense.id, sense.lexeme_id, n, it.get("gloss", ""),
                         it.get("gloss_language") or target, json.dumps(labels),
                         register, it.get("source", "")))
            used(it.get("source"))
            counts["senses"] += 1
            sense_id_by_key[sk] = sense.id
            sense_lexeme[sense.id] = sense.lexeme_id
            if tr and native_text:
                head_zh.add(zh_key(native_text))
                con.execute("INSERT INTO sense_translations VALUES (?,?,?,?,?)",
                            (sense.id, native_text, tr.get("source", ""),
                             int(bool(tr.get("ai"))),
                             int(override is not None or tr.get("source") == "user")))
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
        # 問題回報 #588: the system-voice fallback (tts_fallback) is a pronunciation too.
        for it in [*items(lemma, "audio"), *items(lemma, "tts_fallback")]:
            if it.get("tts"):
                audio_rows.append((None, it))
                continue
            asset = audio_by_url.get(it.get('url'))
            if asset is not None and asset.status == "ready":
                audio_rows.append((asset, it))
                if asset.id not in audio_ids:
                    audio_ids[asset.id] = {"path": asset.path, "sha256": asset.sha256,
                                           "bytes": asset.size_bytes, "mime": asset.mime}
                    con.execute("INSERT INTO audio VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                (asset.id, asset.path, asset.sha256, asset.mime, asset.accent,
                                 asset.speaker, asset.license, asset.attribution,
                                 asset.source_url, asset.duration_s, asset.source_page,
                                 asset.source))
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
            ex = first_for_ids(examples_index, ids, text_hash(it.get('text', '')))
            if ex is None:
                continue
            if not (ex_tr.get(k) or {}).get("text") and ex.id in table_ex_tr:
                row = table_ex_tr[ex.id]
                ex_tr[k] = {"text": row.text, "source": row.source or "", "ai": row.is_ai}
            if is_column_word_list(it.get("text", ""), lemma) or unfit_example(it.get("text", ""), lemma) or (
                    proper_noun_example(it.get("text", ""), lemma)) or offensive_native(
                    (ex_tr.get(k) or {}).get("text")):
                continue
            if target != "en" and (fr_unfit_text(it.get("text", ""), lemma)
                                   or unfit_example((ex_tr.get(k) or {}).get("text", ""))):
                counts["examples_profane_foreign"] = counts.get("examples_profane_foreign", 0) + 1
                continue
            sid = sense_id_by_key.get(ex_sense.get(k) or it.get("sense_key") or "")
            # The learner pack has no UI for an unresolved usage. Keep such
            # examples in the master database for review, but never flatten
            # them into a card where they could illustrate the wrong sense.
            if sid is None:
                continue
            # 問題回報 #456: the sentence uses another part of speech's inflection.
            own_lx = sense_lexeme.get(sid)
            if own_lx is not None and example_other_pos_only(
                    it.get("text", ""), lemma, forms_by_lexeme.get(own_lx, ()),
                    {f for i in ids if i != own_lx for f in forms_by_lexeme.get(i, ())}):
                counts["examples_other_pos"] = counts.get("examples_other_pos", 0) + 1
                continue
            # The card that shows the sentence is the sense's entry, not the
            # master row's (the lowest lexeme id of the word, often the noun):
            # a verb-sense sentence under fear/noun was still shown on the noun
            # card (問題回報 #557).
            con.execute("INSERT INTO examples VALUES (?,?,?,?,?,?,?,?,?)",
                        (ex.id, own_lx if own_lx is not None else ex.lexeme_id, sid, ex.text,
                         ex_level.get(k), it.get("source", ""), ex.source_record_id, ex.license, n))
            used(it.get("source"))
            counts["examples"] += 1
            tr = ex_tr.get(k)
            if tr and tr.get("text"):
                zh = repair_learner_gloss(it.get("text") or "", tr["text"]) or tr["text"]
                con.execute("INSERT INTO example_translations VALUES (?,?,?,?)",
                            (ex.id, zh, tr.get("source", ""), int(bool(tr.get("ai")))))
                used(tr.get("source"))
                counts["example_translations"] += 1
        # relations + native meanings
        derived_pos = {i["word"].lower(): i.get("pos") for i in items(lemma, "derived_pos")
                       if i.get("word")}
        # The headword's own forms are not relation words (spec 08: 詞條本身
        # 的詞形不算; apple's derived terms must not list apples).
        own_forms = {lemma.lower()} | {(it.get("form") or "").lower()
                                       for ff in catalog.INFLECTION_FIELDS for it in items(lemma, ff)}
        def phoneme_set(word):
            return {_phoneme_key(i.get("phonemes")) for i in
                    (values[word].get("phonemes").items if word in values and
                     values[word].get("phonemes") is not None else [])} - {""}
        head_ph = phoneme_set(lemma)
        for f in catalog.RELATION_FIELDS + ["derived_terms"]:
            nat_field = "derived_native_meaning" if f == "derived_terms" else f"{f}_native"
            meanings = {(i.get("word") or i.get("slot") or "").lower(): i
                        for i in items(lemma, nat_field)}
            found = []
            for n, it in enumerate(items(lemma, f)):
                w = (it.get("word") or "").lower()
                if w in own_forms or unfit_relation(f, it.get("word") or "", lemma):
                    continue
                row = first_for_ids(relations_index, ids, (f, w))
                if row is None:
                    continue
                tgt = lexeme_by_id.get(row.target_lexeme_id)
                if tgt is None:
                    continue
                detail = row.detail or {}
                target_zipf = tgt.zipf if tgt.zipf is not None else detail.get("zipf")
                hidden = bool(detail.get("hide_by_default") or
                              (target_zipf is not None and target_zipf < 2.5))
                if not hidden and f in ("related", "hyponyms", "hypernyms"):  # card 694 / #822
                    hidden = is_noisy_function_word_relation(lemma, row.source)
                mean = meanings.get(w)
                zh = clean_native(repair_learner_gloss(row.target_word or w, mean.get("text"))) \
                    if mean else None
                if f in _CONFUSABLE and not hidden:
                    hidden = confusable_problem(w, lemma, tgt, zh, head_zh) is not None
                if f == "homophones" and not hidden:
                    hidden = homophone_problem(w, lemma, detail, target_zipf, head_ph,
                                              phoneme_set(w), tgt) is not None
                found.append((n, it, w, row, tgt, mean, detail, target_zipf,
                              tgt.cefr or detail.get("cefr"), hidden, zh))
            if f in _PER_LEVEL:
                found = per_level(found)
            for n, it, w, row, tgt, mean, detail, target_zipf, target_cefr, hidden, zh in found:
                if tgt.id not in exported and tgt.id not in stub_ids:
                    stub_ids.add(tgt.id)
                con.execute("INSERT INTO relations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (row.id, row.lexeme_id, f, tgt.id, row.target_word,
                             derived_pos.get(w) or it.get("pos") or (tgt.pos if tgt.pos != "unknown"
                                                                    else None),
                             row.source_sense_id if row.source_sense_id in sense_id_by_key.values()
                             else None, row.strength, json.dumps(row.detail or {},
                                                                 ensure_ascii=False),
                             zh,
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
                                 clean_native(repair_learner_gloss(
                                     " ".join(x for x in (p.get("part"), p.get("meaning")) if x),
                                     tr.get("text"))) if tr else None,
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
                             text, repair_learner_gloss(text, nat.get("text")),
                             nat.get("source"), int(bool(nat.get("ai")))))
                counts["etymologies"] += 1
    # Stub lexemes that relations point to (not exported as full entries)
    for sid in sorted(stub_ids - exported):
        lx = lexeme_by_id[sid]
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
    from .card_templates import published
    con.execute("INSERT INTO meta VALUES ('card_template', ?)",
                (json.dumps(published(s), ensure_ascii=False),))
    con.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    con.execute("INSERT INTO meta VALUES ('target_language', ?)", (target,))
    con.execute("INSERT INTO meta VALUES ('native_language', ?)", (native,))
    con.execute("INSERT INTO meta VALUES ('created_at', ?)",
                (datetime.now(timezone.utc).isoformat(),))
    image_files = _images(s, con, tmp_dir, counts, copy_media)
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


def _images(s, con, tmp_dir: Path, counts, copy_media=True) -> list[dict]:
    """Approved sense pictures (spec: 已核准詞義圖片清單): the thumbnail the
    app shows, each picture's licence and author, and its AI labels.
    copy_media=False (the live HTTP pack) lists them without copying files."""
    files = []
    for r in s.execute(sql_text("""
            SELECT si.id, si.sense_id, si.role, si.ordinal, si.semantic_score, a.path,
                   a.thumbnail_path, a.width, a.height, a.license_code, a.license_url, a.author,
                   a.attribution, a.page_url, a.tags
            FROM sense_images si JOIN image_assets a ON a.id = si.image_asset_id
            WHERE si.review_status = 'approved' AND a.status = 'ready'
              AND a.safety_status = 'safe'
            ORDER BY si.sense_id, si.role <> 'representative', si.ordinal, si.id""")).mappings():
        if not con.execute("SELECT 1 FROM senses WHERE id = ?", (r["sense_id"],)).fetchone():
            continue
        rel = r["thumbnail_path"] or r["path"]
        src = config.MEDIA / rel
        if not src.exists():
            continue
        if copy_media:
            dst = tmp_dir / "media" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        sha = _media_sha256(src)
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
        template = con.execute("SELECT value FROM meta WHERE key='card_template'").fetchone()
        template = json.loads(template[0]) if template else None
        add("card_template", True,
            f"已包含字卡版型 {template['id']} v{template['version']}" if template
            else "尚未發布字卡版型（使用 App 內建版型）", level="ok")
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
    # Read the exported snapshot, not a possibly newer concurrent publication.
    with sqlite3.connect(db_path) as con:
        template_row = con.execute("SELECT value FROM meta WHERE key='card_template'").fetchone()
    template = json.loads(template_row[0]) if template_row else None
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
        "card_template_version": template['version'] if template else None,
        "card_template_id": template['id'] if template else None,
        "counts": counts, "completeness": completeness,
        "licenses": [{"source": src, "name": catalog.SOURCES[src].name,
                      "license": catalog.SOURCES[src].license,
                      "attribution": catalog.SOURCES[src].attribution, "values": n}
                     for src, n in sorted(used_sources.items()) if src in catalog.SOURCES],
        "ai_values": ai, "checks": checks,
    }
