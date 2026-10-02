"""Output schema for one word's word-detail-view data.

Every resolved field carries a `*_source` sibling naming which adapter
("kaikki" / "wordnet" / "cmudict" / "datamuse" / "tatoeba") actually
supplied it, so a reviewer can audit coverage and licensing per the
"排序理由" column of spec-01-data-sources.html without re-deriving it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class Definition:
    pos: str  # part of speech, e.g. "noun", "verb"
    gloss: str


@dataclass
class ExampleSentence:
    en: str
    zh: Optional[str] = None
    audio_url: Optional[str] = None
    source: Optional[str] = None          # source of the English sentence itself
    zh_source: Optional[str] = None
    audio_source: Optional[str] = None


@dataclass
class Inflection:
    form: str
    label: str  # e.g. "plural", "past tense", "3rd person singular"


@dataclass
class Derivation:
    word: str
    pos: Optional[str] = None


@dataclass
class WordDetail:
    word: str

    definitions: List[Definition] = field(default_factory=list)
    definitions_source: Optional[str] = None

    ipa: Optional[str] = None
    ipa_source: Optional[str] = None
    arpabet: Optional[str] = None
    arpabet_source: Optional[str] = None

    word_audio_url: Optional[str] = None
    word_audio_source: Optional[str] = None

    synonyms: List[str] = field(default_factory=list)
    synonyms_source: Optional[str] = None

    homophones: List[str] = field(default_factory=list)
    homophones_source: Optional[str] = None

    similar_spelling: List[str] = field(default_factory=list)
    similar_spelling_source: Optional[str] = None

    inflections: List[Inflection] = field(default_factory=list)
    inflections_source: Optional[str] = None

    derivations: List[Derivation] = field(default_factory=list)
    derivations_source: Optional[str] = None

    root: Optional[str] = None
    affixes: List[str] = field(default_factory=list)
    morphology_source: Optional[str] = None

    example_sentences: List[ExampleSentence] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)
