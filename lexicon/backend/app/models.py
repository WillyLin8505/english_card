"""PostgreSQL data model (spec section 08, PostgreSQL 資料模型).

Two layers:
- Evidence: field_candidates keeps every value every source returned;
  field_values keeps what the Resolver adopted under the current policy;
  field_provenance traces each adopted value to its source and snapshot;
  user_overrides always win. These are keyed by headword (target
  language + normalized lemma), because sources answer per headword.
- Dictionary: lexemes (one per language + lemma + part of speech),
  senses, translations bound to sense_id, forms, pronunciations, examples,
  relations … projected from field_values, and exported to SQLite.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint, column, func, literal_column)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Json = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Languages and sources ─────────────────────────────────────────────

class Language(Base):
    __tablename__ = "languages"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    native_name: Mapped[str] = mapped_column(String(64))


class LanguagePair(Base):
    __tablename__ = "language_pairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_language: Mapped[str] = mapped_column(ForeignKey("languages.code"))
    native_language: Mapped[str] = mapped_column(ForeignKey("languages.code"))
    __table_args__ = (UniqueConstraint("target_language", "native_language"),)


class Source(Base):
    __tablename__ = "sources"
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16))
    license: Mapped[str] = mapped_column(Text)
    attribution: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    implemented: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SourceCapability(Base):
    """Which fields a source declares for which direction; native_language
    '*' means any native language (a target-language field)."""
    __tablename__ = "source_capabilities"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(ForeignKey("sources.key", ondelete="CASCADE"))
    target_language: Mapped[str] = mapped_column(String(16))
    native_language: Mapped[str] = mapped_column(String(16))
    field: Mapped[str] = mapped_column(String(48))
    __table_args__ = (UniqueConstraint("source", "target_language", "native_language", "field"),)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(ForeignKey("sources.key"))
    language: Mapped[str] = mapped_column(String(32), default="")
    version: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    path: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued/downloading/ready/failed
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(Json, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


# ── Field-level source policies ───────────────────────────────────────

class SourcePolicy(Base):
    """One policy per target language + native language + exact field."""
    __tablename__ = "source_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    native_language: Mapped[str] = mapped_column(String(16))
    field: Mapped[str] = mapped_column(String(48))
    strategy: Mapped[str] = mapped_column(String(16))
    max_items: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_test: Mapped[dict | None] = mapped_column(Json)
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (UniqueConstraint("target_language", "native_language", "field"),)


class SourcePolicyStep(Base):
    __tablename__ = "source_policy_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("source_policies.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(ForeignKey("sources.key"))
    position: Mapped[int] = mapped_column(Integer)  # gapped: 1000, 2000, …
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    timeout_s: Mapped[float] = mapped_column(Float, default=20)
    retries: Mapped[int] = mapped_column(Integer, default=2)
    min_confidence: Mapped[float] = mapped_column(Float, default=0)
    max_results: Mapped[int | None] = mapped_column(Integer)
    continue_on_failure: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("policy_id", "source"),
                      Index("ix_policy_steps_order", "policy_id", "position"))


# ── Headword evidence: candidates, adopted values, provenance ─────────

class FieldCandidate(Base):
    __tablename__ = "field_candidates"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    lemma: Mapped[str] = mapped_column(String(128))  # normalized headword
    native_language: Mapped[str] = mapped_column(String(16))  # '*' for target fields
    field: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(16))  # language of the value itself
    item_key: Mapped[str] = mapped_column(Text)  # dedupe key
    slot: Mapped[str] = mapped_column(Text, default="")  # what FILL_MISSING fills
    value: Mapped[dict] = mapped_column(Json)
    source_record_id: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1)
    license: Mapped[str] = mapped_column(Text, default="")
    attribution: Mapped[str] = mapped_column(Text, default="")
    raw_value: Mapped[dict | None] = mapped_column(Json)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    invalid_reason: Mapped[str | None] = mapped_column(Text)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id"))
    retrieved_at: Mapped[datetime] = _now()
    __table_args__ = (
        UniqueConstraint("target_language", "lemma", "native_language", "field", "source",
                         "item_key", name="uq_candidate"),
        Index("ix_candidates_word", "target_language", "lemma", "native_language", "field"),
    )


class SourceLookup(Base):
    """That a source was asked for a headword + field, and what happened,
    so a policy change can re-resolve without asking again."""
    __tablename__ = "source_lookups"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    lemma: Mapped[str] = mapped_column(String(128))
    native_language: Mapped[str] = mapped_column(String(16))
    field: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # succeeded/missing/failed/unsupported
    count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    looked_up_at: Mapped[datetime] = _updated()
    __table_args__ = (UniqueConstraint("target_language", "lemma", "native_language", "field",
                                       "source", name="uq_lookup"),)


class FieldValue(Base):
    __tablename__ = "field_values"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    lemma: Mapped[str] = mapped_column(String(128))
    native_language: Mapped[str] = mapped_column(String(16))
    field: Mapped[str] = mapped_column(String(48))
    # complete / partial / missing / failed / user_override / unsupported / unset
    status: Mapped[str] = mapped_column(String(16))
    items: Mapped[list] = mapped_column(Json, default=list)
    missing: Mapped[list] = mapped_column(Json, default=list)  # slots still missing
    policy_version: Mapped[int | None] = mapped_column(Integer)
    resolved_at: Mapped[datetime] = _updated()
    __table_args__ = (UniqueConstraint("target_language", "lemma", "native_language", "field",
                                       name="uq_field_value"),)


class FieldProvenance(Base):
    __tablename__ = "field_provenance"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    field_value_id: Mapped[int] = mapped_column(ForeignKey("field_values.id", ondelete="CASCADE"))
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("field_candidates.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(32))
    item_key: Mapped[str] = mapped_column(Text)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id"))
    strategy: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer)
    processed_at: Mapped[datetime] = _now()
    __table_args__ = (Index("ix_provenance_value", "field_value_id"),)


class UserOverride(Base):
    """A manual value: the Resolver never replaces it."""
    __tablename__ = "user_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    lemma: Mapped[str] = mapped_column(String(128))
    native_language: Mapped[str] = mapped_column(String(16))
    field: Mapped[str] = mapped_column(String(48))
    items: Mapped[list] = mapped_column(Json)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (UniqueConstraint("target_language", "lemma", "native_language", "field",
                                       name="uq_override"),)


# ── Dictionary ────────────────────────────────────────────────────────

class Lexeme(Base):
    __tablename__ = "lexemes"
    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(ForeignKey("languages.code"))
    lemma: Mapped[str] = mapped_column(String(128))
    normalized: Mapped[str] = mapped_column(String(128))
    pos: Mapped[str] = mapped_column(String(16))
    # full: imported; stub: created to link a relation / derived word
    status: Mapped[str] = mapped_column(String(16), default="full")
    cefr: Mapped[str | None] = mapped_column(String(4))
    zipf: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        UniqueConstraint("language", "normalized", "pos", name="uq_lexeme"),
        Index("ix_lexemes_trgm", "normalized", postgresql_using="gin",
              postgresql_ops={"normalized": "gin_trgm_ops"}),
    )


class LexemeRedirect(Base):
    """Old lexeme ids that were merged: the app keeps stable ids."""
    __tablename__ = "lexeme_redirects"
    old_id: Mapped[int] = mapped_column(primary_key=True)
    new_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = _now()


class Sense(Base):
    __tablename__ = "senses"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    sense_key: Mapped[str] = mapped_column(String(40))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    labels: Mapped[list] = mapped_column(Json, default=list)
    synset_id: Mapped[int | None] = mapped_column(ForeignKey("synsets.id"))
    __table_args__ = (UniqueConstraint("lexeme_id", "sense_key"),)


class Definition(Base):
    __tablename__ = "definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"))
    language: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("sense_id", "language"),)


class SenseTranslation(Base):
    """Native-language meaning, bound to one sense."""
    __tablename__ = "sense_translations"
    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"))
    native_language: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("sense_id", "native_language"),)


class LocalizedLabel(Base):
    __tablename__ = "localized_labels"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64))  # pos:noun, accent:UK, form:verb_past …
    language: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("key", "language"),)


class Form(Base):
    __tablename__ = "forms"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    field: Mapped[str] = mapped_column(String(48))
    form: Mapped[str] = mapped_column(String(128))
    normalized: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("lexeme_id", "field", "form"),
                      Index("ix_forms_normalized", "normalized"))


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(String(16))
    accent: Mapped[str | None] = mapped_column(String(32))
    speaker: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    source_url: Mapped[str] = mapped_column(Text)
    source_page: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    mime: Mapped[str | None] = mapped_column(String(32))
    duration_s: Mapped[float | None] = mapped_column(Float)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    path: Mapped[str | None] = mapped_column(Text)  # relative to media/
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/ready/failed
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint("source_url"),)


class Pronunciation(Base):
    __tablename__ = "pronunciations"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # ipa/phonemes/syllables/stress/audio/tts
    value: Mapped[str] = mapped_column(Text, default="")
    accent: Mapped[str | None] = mapped_column(String(32))
    audio_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="SET NULL"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)


class Synset(Base):
    __tablename__ = "synsets"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(64))
    pos: Mapped[str | None] = mapped_column(String(16))
    __table_args__ = (UniqueConstraint("source", "external_id"),)


class SemanticRelation(Base):
    """Synset-to-synset relations (WordNet hypernymy …)."""
    __tablename__ = "semantic_relations"
    id: Mapped[int] = mapped_column(primary_key=True)
    synset_id: Mapped[int] = mapped_column(ForeignKey("synsets.id", ondelete="CASCADE"))
    target_synset_id: Mapped[int] = mapped_column(ForeignKey("synsets.id", ondelete="CASCADE"))
    relation: Mapped[str] = mapped_column(String(32))


class LexemeRelation(Base):
    """synonyms, antonyms, …, similar spelling, derived terms: each links
    to a real lexeme (a stub one if the word isn't imported yet)."""
    __tablename__ = "lexeme_relations"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    source_sense_id: Mapped[int | None] = mapped_column(ForeignKey("senses.id", ondelete="SET NULL"))
    relation: Mapped[str] = mapped_column(String(32))  # the field key
    target_lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    target_word: Mapped[str] = mapped_column(String(128))
    strength: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[dict] = mapped_column(Json, default=dict)  # score, difference, affix …
    source: Mapped[str] = mapped_column(String(32))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("lexeme_id", "relation", "target_lexeme_id"),)


class RelationTargetSense(Base):
    __tablename__ = "relation_target_senses"
    relation_id: Mapped[int] = mapped_column(
        ForeignKey("lexeme_relations.id", ondelete="CASCADE"), primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"),
                                          primary_key=True)


class RelationTranslation(Base):
    """The related word's meaning in the learner's language."""
    __tablename__ = "relation_translations"
    id: Mapped[int] = mapped_column(primary_key=True)
    relation_id: Mapped[int] = mapped_column(ForeignKey("lexeme_relations.id", ondelete="CASCADE"))
    native_language: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("relation_id", "native_language"),)


class Etymology(Base):
    __tablename__ = "etymologies"
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"),
                                           primary_key=True)
    root: Mapped[list] = mapped_column(Json, default=list)
    prefix: Mapped[list] = mapped_column(Json, default=list)
    suffix: Mapped[list] = mapped_column(Json, default=list)
    origin_language: Mapped[str | None] = mapped_column(Text)
    original_form: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)


class EtymologyTranslation(Base):
    __tablename__ = "etymology_translations"
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"),
                                           primary_key=True)
    native_language: Mapped[str] = mapped_column(String(16), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)


class Morpheme(Base):
    """構詞拆解: one part of a lexeme's breakdown, in order (ex- · -ter · -ior)."""
    __tablename__ = "morphemes"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    part: Mapped[str] = mapped_column(String(64))  # shown: "ex-", "happy", "-ness"
    kind: Mapped[str] = mapped_column(String(8))  # prefix / root / suffix
    meaning: Mapped[str | None] = mapped_column(Text)  # English
    free: Mapped[bool] = mapped_column(Boolean, default=False)  # an English word itself
    source: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("lexeme_id", "ordinal"),)


class MorphemeTranslation(Base):
    __tablename__ = "morpheme_translations"
    id: Mapped[int] = mapped_column(primary_key=True)
    morpheme_id: Mapped[int] = mapped_column(ForeignKey("morphemes.id", ondelete="CASCADE"))
    native_language: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("morpheme_id", "native_language"),)


class Example(Base):
    __tablename__ = "examples"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    sense_id: Mapped[int | None] = mapped_column(ForeignKey("senses.id", ondelete="SET NULL"))
    language: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(40))  # normalized-text hash: dedupe
    difficulty: Mapped[str | None] = mapped_column(String(4))
    source: Mapped[str] = mapped_column(String(32))
    source_record_id: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("lexeme_id", "text_hash"),)


class ExampleTranslation(Base):
    __tablename__ = "example_translations"
    id: Mapped[int] = mapped_column(primary_key=True)
    example_id: Mapped[int] = mapped_column(ForeignKey("examples.id", ondelete="CASCADE"))
    native_language: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    source_record_id: Mapped[str | None] = mapped_column(Text)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("example_id", "native_language"),)


# ── Images (schema only for now; see README) ──────────────────────────

class ImageAsset(Base):
    __tablename__ = "image_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    source_image_id: Mapped[str] = mapped_column(Text)
    page_url: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    license_code: Mapped[str | None] = mapped_column(String(32))
    license_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mime: Mapped[str | None] = mapped_column(String(32))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    phash: Mapped[str | None] = mapped_column(String(32))
    path: Mapped[str | None] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    safety_status: Mapped[str] = mapped_column(String(16), default="unchecked")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # What the local vision model sees in the picture, as the app's photo
    # labels: [{"word", "pos", "point": [x, y] (fractions)}]. The worker tags
    # every downloaded picture while no import job is waiting.
    tags: Mapped[list | None] = mapped_column(Json)
    # Labels under the pass score (images.TAG_PASS): shown in the library only.
    dropped_tags: Mapped[list | None] = mapped_column(Json)
    tag_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/done/failed
    tag_model: Mapped[str | None] = mapped_column(String(64))
    tagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImageCandidate(Base):
    __tablename__ = "image_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(32))
    query: Mapped[str | None] = mapped_column(Text)
    concept_id: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict] = mapped_column("metadata", Json, default=dict)
    image_asset_id: Mapped[int | None] = mapped_column(ForeignKey("image_assets.id"))
    score: Mapped[float | None] = mapped_column(Float)


class SenseImage(Base):
    __tablename__ = "sense_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"))
    image_asset_id: Mapped[int] = mapped_column(ForeignKey("image_assets.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # representative/context
    semantic_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    alt_native: Mapped[dict] = mapped_column(Json, default=dict)


class ImageReview(Base):
    __tablename__ = "image_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    sense_image_id: Mapped[int] = mapped_column(ForeignKey("sense_images.id", ondelete="CASCADE"))
    decision: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()


# ── Card templates (schema only for now; see README) ──────────────────

class CardTemplate(Base):
    __tablename__ = "card_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    native_language: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    draft: Mapped[dict] = mapped_column(Json, default=dict)
    published_version: Mapped[int | None] = mapped_column(Integer)


class CardTemplateVersion(Base):
    __tablename__ = "card_template_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("card_templates.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    layout: Mapped[dict] = mapped_column(Json)
    published_at: Mapped[datetime] = _now()


class CardTemplateSection(Base):
    __tablename__ = "card_template_sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("card_template_versions.id", ondelete="CASCADE"))
    section: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    ordinal: Mapped[int] = mapped_column(Integer)
    settings: Mapped[dict] = mapped_column(Json, default=dict)


# ── Requests from the app ─────────────────────────────────────────────

class MissingLexemeRequest(Base):
    __tablename__ = "missing_lexeme_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    lemma: Mapped[str] = mapped_column(String(128))
    pos: Mapped[str | None] = mapped_column(String(16))
    count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint("target_language", "lemma", "pos"),)


class MissingLocalizationRequest(Base):
    __tablename__ = "missing_localization_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="CASCADE"))
    native_language: Mapped[str] = mapped_column(String(16))
    field: Mapped[str | None] = mapped_column(String(48))
    count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint("lexeme_id", "native_language", "field"),)


class DictionaryRelease(Base):
    __tablename__ = "dictionary_releases"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    native_language: Mapped[str] = mapped_column(String(16))
    file_name: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    include_audio: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="building")  # building/ready/failed
    manifest: Mapped[dict | None] = mapped_column(Json)
    checks: Mapped[list] = mapped_column(Json, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = _now()


# ── Jobs ──────────────────────────────────────────────────────────────

JOB_STATES = ("queued", "running", "pausing", "paused", "cancelling", "cancelled", "completed",
              "completed_with_errors", "failed")
ATTEMPT_STATES = ("pending", "running", "succeeded", "missing", "retrying", "failed", "skipped")


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    native_language: Mapped[str] = mapped_column(String(16))
    # fill_missing / force_refresh / validate_only / dry_run / reresolve
    mode: Mapped[str] = mapped_column(String(16))
    words: Mapped[list] = mapped_column(Json)
    fields: Mapped[list] = mapped_column(Json)
    sources: Mapped[list | None] = mapped_column(Json)  # None = every policy source
    status: Mapped[str] = mapped_column(String(24), default="queued")
    total: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint: Mapped[int] = mapped_column(Integer, default=0)  # words finished
    counts: Mapped[dict] = mapped_column(Json, default=dict)
    worker_id: Mapped[str | None] = mapped_column(String(64))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_of: Mapped[int | None] = mapped_column(ForeignKey("import_jobs.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    error: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_jobs_status", "status", "created_at"),)


class ImageFetchTask(Base):
    """A deferred image lookup so dictionary text never waits on Wikimedia."""
    __tablename__ = "image_fetch_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_language: Mapped[str] = mapped_column(String(16))
    native_language: Mapped[str] = mapped_column(String(16))
    lemma: Mapped[str] = mapped_column(String(128))
    fields: Mapped[list] = mapped_column(Json, default=list)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("target_language", "native_language", "lemma",
                         name="uq_image_fetch_task_word"),
        Index("ix_image_fetch_tasks_status", "status", "created_at"),
    )


class ImportJobStep(Base):
    """Per job, field and source step: how it went."""
    __tablename__ = "import_job_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"))
    field: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    missing: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    retried: Mapped[int] = mapped_column(Integer, default=0)
    ms_total: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (UniqueConstraint("job_id", "field", "source"),)


class ImportAttempt(Base):
    __tablename__ = "import_attempts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"))
    lemma: Mapped[str] = mapped_column(String(128))
    field: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    count: Mapped[int] = mapped_column(Integer, default=0)
    ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (UniqueConstraint("job_id", "lemma", "field", "source"),
                      Index("ix_attempts_job_status", "job_id", "status"))


class ImportError_(Base):
    __tablename__ = "import_errors"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"))
    lemma: Mapped[str] = mapped_column(String(128))
    field: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(32))
    error_type: Mapped[str] = mapped_column(String(32))  # timeout/http/parse/validation/…
    message: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_record_id: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (Index("ix_errors_job", "job_id"),)


class JobLog(Base):
    __tablename__ = "import_job_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(8), default="info")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (Index("ix_job_logs_job", "job_id", "id"),)


class ApiUsage(Base):
    __tablename__ = "api_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    day: Mapped[str] = mapped_column(String(10))  # yyyy-mm-dd
    requests: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    ms_total: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (UniqueConstraint("source", "day"),)


class Wordlist(Base):
    """Word lists a job can take its words from."""
    __tablename__ = "wordlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    words: Mapped[list] = mapped_column(Json)
    __table_args__ = (UniqueConstraint("language", "name"),)


# ── Tatoeba bulk export (imported by a Source Snapshot) ───────────────

class TatoebaSentence(Base):
    __tablename__ = "tatoeba_sentences"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    lang: Mapped[str] = mapped_column(String(8))
    text: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(64))
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id",
                                                               ondelete="SET NULL"))
    __table_args__ = (
        Index("ix_tatoeba_lang_md5", "lang", func.md5(column("text"))),
        Index("ix_tatoeba_tsv", func.to_tsvector(literal_column("'simple'::regconfig"),
                                                 column("text")), postgresql_using="gin"),
    )


class TatoebaLink(Base):
    __tablename__ = "tatoeba_links"
    a: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    b: Mapped[int] = mapped_column(BigInteger, primary_key=True)


# ── 問題回報 (issues found while testing, and requirements not built yet) ──

class IssueReport(Base):
    """One problem or unfinished requirement, tracked on the 問題回報 page.

    kind: bug (問題) · todo (未完成需求) · decision (待決定)
    status: open · in_progress · needs_decision · fixed · wont_fix
    """
    __tablename__ = "issue_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="bug")
    status: Mapped[str] = mapped_column(String(16), default="open")
    severity: Mapped[str] = mapped_column(String(8), default="medium")
    area: Mapped[str] = mapped_column(String(16), default="app")
    title: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[str | None] = mapped_column(Text)
    expected: Mapped[str | None] = mapped_column(Text)
    actual: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(Json)       # choices for a decision
    decision: Mapped[str | None] = mapped_column(Text)
    target_language: Mapped[str | None] = mapped_column(String(16))
    native_language: Mapped[str | None] = mapped_column(String(16))
    lemma: Mapped[str | None] = mapped_column(Text)
    code_ref: Mapped[str | None] = mapped_column(Text)
    spec_ref: Mapped[str | None] = mapped_column(Text)
    reporter: Mapped[str] = mapped_column(String(32), default="manual")
    history: Mapped[list] = mapped_column(Json, default=list)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_issue_reports_status", "status", "kind"),)
