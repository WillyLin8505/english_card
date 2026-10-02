"""Resolves each of the 12 word-detail data categories by walking the
source-priority list in pipeline/priority.py and taking the first
adapter with a non-empty answer — the direct implementation of
spec-01-data-sources.html section 3.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from .priority import CATEGORY_METHODS, FIELD_SOURCES
from .schema import Definition, Derivation, ExampleSentence, Inflection, WordDetail

logger = logging.getLogger(__name__)


def resolve(
    word: str, category: str, adapters: Dict[str, Any]
) -> Tuple[Optional[Any], Optional[str]]:
    """Try each source in `FIELD_SOURCES[category]` order; return the
    first (result, source_name) where result is truthy, else (None, None).
    A source raising is logged and skipped, never crashes the build."""
    method_name = CATEGORY_METHODS[category]
    for source_name in FIELD_SOURCES[category]:
        adapter = adapters.get(source_name)
        if adapter is None:
            continue
        method = getattr(adapter, method_name, None)
        if method is None:
            continue
        try:
            result = method(word)
        except Exception:
            logger.exception("%s.%s(%r) failed", source_name, method_name, word)
            continue
        if result:
            return result, source_name
    return None, None


def build_word_detail(word: str, adapters: Dict[str, Any]) -> WordDetail:
    wd = WordDetail(word=word)

    lexical, src = resolve(word, "lexical", adapters)
    if lexical:
        wd.definitions = [Definition(**d) for d in lexical.get("definitions", [])]
        wd.definitions_source = src

    pron, src = resolve(word, "pronunciation", adapters)
    if pron:
        wd.ipa = pron.get("ipa")
        wd.arpabet = pron.get("arpabet")
        wd.ipa_source = src if pron.get("ipa") else None
        wd.arpabet_source = src if pron.get("arpabet") else None

    audio, src = resolve(word, "word_audio", adapters)
    if audio:
        wd.word_audio_url = audio.get("url")
        wd.word_audio_source = src

    syns, src = resolve(word, "synonyms", adapters)
    if syns:
        wd.synonyms = list(syns)
        wd.synonyms_source = src

    homs, src = resolve(word, "homophones", adapters)
    if homs:
        wd.homophones = list(homs)
        wd.homophones_source = src

    sims, src = resolve(word, "similar_spelling", adapters)
    if sims:
        wd.similar_spelling = list(sims)
        wd.similar_spelling_source = src

    infl, src = resolve(word, "inflections", adapters)
    if infl:
        wd.inflections = [Inflection(**i) for i in infl]
        wd.inflections_source = src

    deriv, src = resolve(word, "derivations", adapters)
    if deriv:
        wd.derivations = [Derivation(**d) for d in deriv]
        wd.derivations_source = src

    morph, src = resolve(word, "morphology", adapters)
    if morph:
        wd.root = morph.get("root")
        wd.affixes = morph.get("affixes") or []
        wd.morphology_source = src

    examples, src = resolve(word, "example_sentences", adapters)
    if examples:
        wd.example_sentences = [
            ExampleSentence(
                en=e["en"],
                zh=e.get("zh"),
                audio_url=e.get("audio_url"),
                source=src,
                zh_source=src if e.get("zh") else None,
                audio_source=src if e.get("audio_url") else None,
            )
            for e in examples
            if e.get("en")
        ]

    return wd
