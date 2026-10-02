"""Source-priority table, transcribed verbatim from spec-01-data-sources.html
section 3 ("英文學習資料來源"). This is the single source of truth for
which adapter is tried first/second/third for each of the 12 data
categories — keep it in sync with the spec document if that ever changes.

Each category maps to an ordered list of adapter names. `merge.resolve()`
walks the list in order and returns the first adapter that has a
non-empty answer, plus the source that won so callers can audit "為什麼
用這個來源".
"""

from __future__ import annotations

from typing import Dict, List

# category -> (adapter method name, ordered adapter names: 首選, 次選, 補充...)
FIELD_SOURCES: Dict[str, List[str]] = {
    # 單字、釋義、詞性
    "lexical": ["kaikki", "wordnet"],
    # 發音音標／音素
    "pronunciation": ["kaikki", "cmudict"],
    # 單字真人發音
    "word_audio": ["kaikki"],
    # 近義字／意思相近
    "synonyms": ["wordnet", "kaikki", "datamuse"],
    # 同音字／發音相近
    "homophones": ["cmudict", "datamuse", "kaikki"],
    # 拼字相近
    "similar_spelling": ["kaikki_wordlist", "datamuse"],
    # 詞形變化，如過去式、複數
    "inflections": ["kaikki"],
    # 詞性衍生，如 happy -> happiness
    "derivations": ["kaikki", "wordnet"],
    # 字根、字尾／後綴
    "morphology": ["kaikki"],
    # 英文例句
    "example_sentences": ["tatoeba", "kaikki", "wordnet"],
    # 例句中文翻譯
    "sentence_translation": ["tatoeba"],
    # 整句真人發音
    "sentence_audio": ["tatoeba"],
}

# Method each adapter must expose to serve a category (None = not sourced
# per-word, handled specially in merge.py, e.g. sentence_translation).
CATEGORY_METHODS: Dict[str, str] = {
    "lexical": "get_lexical",
    "pronunciation": "get_pronunciation",
    "word_audio": "get_word_audio",
    "synonyms": "get_synonyms",
    "homophones": "get_homophones",
    "similar_spelling": "get_similar_spelling",
    "inflections": "get_inflections",
    "derivations": "get_derivations",
    "morphology": "get_morphology",
    "example_sentences": "get_example_sentences",
}
