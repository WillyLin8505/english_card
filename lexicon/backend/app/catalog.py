"""What can be configured: languages, the exact fields (grouped in the
spec's blocks), the sources, which fields each source can supply for
which language direction, and the default source policies.

Spec section 08, 欄位級來源順位: every field is its own policy, keyed by
target language + native language + field. Nothing here is shared
between fields; a field with no policy steps is 「未設定」.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LANGUAGES = {
    "en": {"name": "English", "native_name": "English", "zh": "英文"},
    "fr": {"name": "French", "native_name": "Français", "zh": "法文"},
    "zh-TW": {"name": "Traditional Chinese", "native_name": "繁體中文", "zh": "繁體中文"},
}
PAIRS = [(t, n) for t in LANGUAGES for n in LANGUAGES if t != n]

STRATEGIES = {
    "FIRST_VALID": "第一個有效來源",
    "MERGE_UNIQUE": "合併去重",
    "FILL_MISSING": "逐項補缺",
    "BEST_SCORE": "最高可信度",
    "APPEND_LIMITED": "依序附加到上限",
}

BLOCKS = [
    ("basic", "基本資料"),
    ("pronunciation", "發音"),
    ("forms", "詞形變化"),
    ("relations", "詞彙關係"),
    ("derivation", "衍生詞"),
    ("etymology", "字根與詞源"),
    ("examples", "例句"),
    ("images", "詞義圖片"),
]


@dataclass(frozen=True)
class Field:
    key: str
    block: str
    label: str
    # "target": data about the target-language word, shareable by every
    # native language; "native": explanations in the learner's language.
    scope: str = "target"
    # Target languages the field exists for (None = all).
    languages: tuple[str, ...] | None = None
    # A per-item key lets FILL_MISSING fill one sense / example at a time.
    itemized: bool = False
    description: str = ""


FIELDS: list[Field] = [
    # 基本資料
    Field("pos", "basic", "詞性"),
    Field("definition", "basic", "逐義釋義", itemized=True, description="目標語言的每個詞義"),
    Field("native_definition", "basic", "母語釋義", "native", itemized=True,
          description="綁定到每個 sense 的母語釋義"),
    Field("cefr", "basic", "CEFR"),
    Field("frequency", "basic", "頻率"),
    Field("usage_labels", "basic", "用法／語域標籤"),
    # 發音
    Field("ipa", "pronunciation", "IPA"),
    Field("phonemes", "pronunciation", "音素", description="ARPAbet 等音素，不是 IPA"),
    Field("syllables", "pronunciation", "音節"),
    Field("stress", "pronunciation", "重音"),
    Field("accent_labels", "pronunciation", "口音標籤"),
    Field("audio", "pronunciation", "真人單字音檔"),
    Field("tts_fallback", "pronunciation", "TTS 備援", description="只有沒有真人音檔時才用"),
    # 詞形變化 — English
    Field("verb_base", "forms", "動詞原形", languages=("en",)),
    Field("verb_past", "forms", "過去式", languages=("en",)),
    Field("verb_past_participle", "forms", "過去分詞", languages=("en",)),
    Field("verb_present_participle", "forms", "現在分詞", languages=("en",)),
    Field("verb_third_person", "forms", "第三人稱單數", languages=("en",)),
    Field("noun_plural", "forms", "名詞複數", languages=("en",)),
    Field("adj_comparative", "forms", "形容詞比較級", languages=("en",)),
    Field("adj_superlative", "forms", "形容詞最高級", languages=("en",)),
    # 詞形變化 — French
    Field("fr_present_1s", "forms", "現在式 je", languages=("fr",)),
    Field("fr_present_2s", "forms", "現在式 tu", languages=("fr",)),
    Field("fr_present_3s", "forms", "現在式 il／elle", languages=("fr",)),
    Field("fr_present_1p", "forms", "現在式 nous", languages=("fr",)),
    Field("fr_present_2p", "forms", "現在式 vous", languages=("fr",)),
    Field("fr_present_3p", "forms", "現在式 ils／elles", languages=("fr",)),
    Field("fr_past_participle", "forms", "過去分詞", languages=("fr",)),
    Field("fr_feminine", "forms", "陰性", languages=("fr",)),
    Field("fr_plural", "forms", "複數", languages=("fr",)),
    Field("fr_feminine_plural", "forms", "陰性複數", languages=("fr",)),
    # 詞彙關係
    Field("synonyms", "relations", "同義詞"),
    Field("antonyms", "relations", "反義詞"),
    Field("hypernyms", "relations", "上位詞"),
    Field("hyponyms", "relations", "下位詞"),
    Field("related", "relations", "相關詞"),
    Field("homophones", "relations", "同音字"),
    Field("near_homophones", "relations", "近音字"),
    Field("similar_spelling", "relations", "拼字相近"),
    # 衍生詞
    Field("derived_terms", "derivation", "衍生詞清單"),
    Field("derivation_relation", "derivation", "衍生關係", itemized=True),
    Field("derived_pos", "derivation", "衍生詞詞性", itemized=True),
    Field("derived_native_meaning", "derivation", "衍生詞母語詞義", "native", itemized=True),
    # 字根與詞源
    Field("morphemes", "etymology", "構詞拆解",
          description="依順序拆成字首、字根、字尾，每段附意思（exterior → ex + -ter + -ior）"),
    Field("morphemes_native", "etymology", "構詞部件母語意思", "native", itemized=True,
          description="拆解出的每一段在母語的意思"),
    Field("root", "etymology", "字根"),
    Field("prefix", "etymology", "字首"),
    Field("suffix", "etymology", "字尾"),
    Field("origin_language", "etymology", "來源語"),
    Field("original_form", "etymology", "原始形式"),
    Field("etymology_text", "etymology", "詞源說明"),
    Field("etymology_native", "etymology", "母語詞源說明", "native"),
    # 例句
    Field("example_sentences", "examples", "目標語言例句", itemized=True),
    Field("example_difficulty", "examples", "例句難度", itemized=True),
    Field("example_sense", "examples", "對應 sense", itemized=True),
    Field("example_translation", "examples", "母語翻譯", "native", itemized=True),
    # 詞義圖片 — every sense finds its own images
    Field("sense_image", "images", "代表圖片", itemized=True),
    Field("context_image", "images", "情境圖片", itemized=True),
    Field("thumbnail", "images", "縮圖", itemized=True),
    Field("image_alt_native", "images", "母語替代文字", "native", itemized=True),
]
RELATION_FIELDS = [f.key for f in FIELDS if f.block == "relations"]
# Each relation type's words get their own native-meaning policy, placed
# right after the relation list itself.
for _rel in reversed(RELATION_FIELDS):
    _i = next(i for i, f in enumerate(FIELDS) if f.key == _rel)
    FIELDS.insert(_i + 1, Field(f"{_rel}_native", "relations", f"{FIELDS[_i].label}母語詞義",
                                "native", itemized=True,
                                description=f"每個{FIELDS[_i].label}各自的母語詞義"))
FIELD = {f.key: f for f in FIELDS}
RELATION_NATIVE = {f"{r}_native": r for r in RELATION_FIELDS}
FORM_FIELDS = [f.key for f in FIELDS if f.block == "forms"]


def fields_for(target: str) -> list[Field]:
    return [f for f in FIELDS if f.languages is None or target in f.languages]


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    kind: str  # dump | api | local | ai | tts
    license: str
    attribution: str
    url: str = ""
    # {target: {field: {native or "*"}}} — which directions are supported.
    supports: dict = field(default_factory=dict)
    # Why a field isn't supported, shown in the source menu.
    note: str = ""
    # False: declared (so policies can list it) but no adapter yet.
    implemented: bool = True


_KAIKKI_EN_TARGET = {
    "pos", "definition", "usage_labels", "ipa", "syllables", "accent_labels", "audio",
    "verb_base", "verb_past", "verb_past_participle", "verb_present_participle",
    "verb_third_person", "noun_plural", "adj_comparative", "adj_superlative",
    "synonyms", "antonyms", "hypernyms", "hyponyms", "related", "homophones",
    "derived_terms", "root", "prefix", "suffix", "origin_language", "original_form",
    "etymology_text", "example_sentences", "example_sense", "phonemes",
}
_KAIKKI_FR_TARGET = {
    "pos", "definition", "usage_labels", "ipa", "audio", "fr_present_1s", "fr_present_2s",
    "fr_present_3s", "fr_present_1p", "fr_present_2p", "fr_present_3p", "fr_past_participle",
    "fr_feminine", "fr_plural", "fr_feminine_plural", "synonyms", "antonyms", "related",
    "derived_terms", "etymology_text", "origin_language", "original_form", "example_sentences",
    "example_sense",
}
_KAIKKI_ZH_TARGET = {"pos", "definition", "usage_labels", "ipa", "audio", "synonyms", "antonyms",
                     "related", "derived_terms", "etymology_text", "example_sentences",
                     "example_sense"}
_RELS = RELATION_FIELDS


def _target(fields):
    return {f: {"*"} for f in fields}


SOURCES: dict[str, Source] = {s.key: s for s in [
    Source("kaikki", "Kaikki／Wiktionary", "dump", "CC BY-SA 4.0／GFDL",
           "Wiktionary contributors, via kaikki.org (Tatu Ylonen, wiktextract)",
           "https://kaikki.org/", {
               "en": {**_target(_KAIKKI_EN_TARGET),
                      # English entries carry sense-bound translation tables.
                      "native_definition": {"zh-TW", "fr"},
                      "derived_native_meaning": {"zh-TW", "fr"},
                      **{f"{r}_native": {"zh-TW", "fr"} for r in _RELS},
                      "morphemes": {"*"}, "morphemes_native": {"zh-TW", "fr"}},
               "fr": {**_target(_KAIKKI_FR_TARGET), "native_definition": {"en"}},
               "zh-TW": {**_target(_KAIKKI_ZH_TARGET), "native_definition": {"en"}},
           }, "翻譯表只在英文 Wiktionary 的英文詞條裡；法文、中文詞條的釋義是英文。"),
    Source("kaikki_wordlist", "本地字表計算", "local", "Apache-2.0／CC BY-SA 4.0（wordfreq 字表）",
           "wordfreq (Robyn Speer); CEFR-J Wordlist", "https://github.com/rspeer/wordfreq",
           {t: _target({"similar_spelling"}) for t in ("en", "fr")},
           "在本機字表裡找只差一個字母的詞。字表目前是 wordfreq 前 6 萬常用字＋CEFR-J；"
           "規格指定的 Kaikki 全量字表需 2–3 GB 資料包，尚未匯入。"),
    Source("oewn", "Open English WordNet", "dump", "CC BY 4.0",
           "Open English WordNet (McCrae et al.)", "https://en-word.net/",
           {"en": _target({"pos", "definition", "synonyms", "antonyms", "hypernyms", "hyponyms",
                           "related", "derived_terms", "derived_pos", "example_sentences",
                           "example_sense"})},
           "只有英文。"),
    Source("cmudict", "CMUdict", "dump", "BSD-2-Clause", "Carnegie Mellon University",
           "https://github.com/cmusphinx/cmudict",
           {"en": _target({"phonemes", "stress", "syllables", "homophones", "near_homophones",
                           "ipa"})},
           "美式英文音素（ARPAbet）；Wiktionary 沒有 IPA 時換寫成 IPA，標記為由音素轉換。"),
    Source("tatoeba", "Tatoeba", "dump", "CC BY 2.0 FR", "Tatoeba contributors",
           "https://tatoeba.org/", {
               t: {"example_sentences": {"*"},
                   "example_translation": {n for n in LANGUAGES if n != t}}
               for t in LANGUAGES}, "例句與逐句翻譯；不保存整句發音。"),
    Source("datamuse", "Datamuse", "api", "Datamuse API 使用條款", "Datamuse API",
           "https://www.datamuse.com/api/",
           {"en": _target({"synonyms", "antonyms", "hypernyms", "hyponyms", "related",
                           "homophones", "near_homophones", "similar_spelling", "frequency"})},
           "只有英文。"),
    Source("cefrj", "CEFR-J／Octanove 詞表", "local", "CEFR-J：引用即可使用；Octanove：CC BY-SA 4.0",
           "CEFR-J Wordlist (Tono Laboratory, TUFS); Octanove Labs",
           "https://github.com/openlanguageprofiles/olp-en-cefrj", {"en": _target({"cefr"})},
           "只有英文。"),
    Source("wordfreq", "wordfreq", "local", "Apache-2.0（程式）／CC BY-SA 4.0（資料）",
           "wordfreq (Robyn Speer)", "https://github.com/rspeer/wordfreq",
           {t: _target({"frequency"}) for t in LANGUAGES}),
    Source("local_calc", "本機規則計算", "local", "由其他欄位計算", "",
           "", {t: {**_target({"derivation_relation", "example_difficulty", "example_sense",
                               "stress", "cefr", "ipa", "noun_plural", "derived_pos"})}
                for t in LANGUAGES},
           "由已取得的欄位推算（例如由衍生詞字尾判斷衍生關係）。"),
    Source("lexicon", "詞庫內既有詞條", "local", "沿用該詞條的來源授權", "",
           "", {t: {"derived_native_meaning": {n for n in LANGUAGES if n != t},
                    **{f"{r}_native": {n for n in LANGUAGES if n != t} for r in _RELS},
                    "morphemes_native": {n for n in LANGUAGES if n != t},
                    "derived_pos": {"*"}} for t in LANGUAGES},
           "查詞庫裡已經建好的另一個詞條（例如衍生詞自己的詞條）。"),
    Source("ai_translate", "AI 翻譯", "ai", "AI 產生（標記為 AI 翻譯）",
           "Qwen3-VL on the local tagging service", "",
           {t: {f: {n for n in LANGUAGES if n != t} for f in (
               "native_definition", "example_translation", "derived_native_meaning",
               "etymology_native", "image_alt_native", "morphemes_native",
               *(f"{r}_native" for r in _RELS))}
            | _target({"example_sentences", "synonyms", "related"}) for t in LANGUAGES},
           "排在字典與例句庫之後：母語翻譯缺的才補；例句、同義詞、相關詞只補 A1–C2 仍不到 3 個的"
           "等級。全部標記為 AI；繁體中文一律用台灣用法。不產生英文釋義或構詞拆解。"),
    Source("system_tts", "系統 TTS", "tts", "裝置系統語音", "", "",
           {t: _target({"audio", "tts_fallback"}) for t in LANGUAGES},
           "不是真人音檔；只在真人音檔都失敗時作為播放備援。"),
    Source("morph_local", "本機構詞分析", "local",
           "本專案整理的構詞表（字首、字尾、拉丁／希臘字根）", "",
           "", {"en": {**_target({"morphemes", "root", "prefix", "suffix"}),
                       "morphemes_native": {"zh-TW"}}},
           "用字首、字尾與拉丁／希臘字根表比對，處理拼字變化（happi→happy），並參考詞源避免把"
           "古英語字硬拆成拉丁字根。只有英文；部件意思只有繁中（其他母語用 AI）。"),
    Source("wikimedia_commons", "Wikidata＋Wikimedia Commons", "api",
           "逐檔授權（只收 CC0／PD／CC BY）", "Wikimedia Commons contributors",
           "https://commons.wikimedia.org/",
           {t: _target({"sense_image", "context_image", "thumbnail", "audio"}) for t in LANGUAGES},
           "擷取工作自動抓取：依釋義、詞性與母語詞義把前 2 個 sense 對應 Wikidata 概念，每個 "
           "sense 下載 3 張授權合格的候選圖（附語意分數）進入審核佇列；不自動核准。"),
    Source("open_images", "Open Images", "dump", "逐張核對（CC BY 2.0 為主）", "Google Open Images",
           "https://storage.googleapis.com/openimages/web/index.html",
           {t: _target({"sense_image", "context_image", "thumbnail"}) for t in LANGUAGES},
           "adapter 尚未實作。", implemented=False),
    Source("smithsonian", "Smithsonian Open Access", "api", "只收 CC0", "Smithsonian Institution",
           "https://www.si.edu/openaccess",
           {t: _target({"sense_image", "context_image", "thumbnail"}) for t in LANGUAGES},
           "adapter 尚未實作。", implemented=False),
    Source("openverse", "Openverse", "api", "須回原站核對授權", "Openverse",
           "https://openverse.org/",
           {t: _target({"sense_image", "context_image", "thumbnail"}) for t in LANGUAGES},
           "只作最後搜尋入口；adapter 尚未實作。", implemented=False),
]}


def supports(source: str, target: str, native: str, field_key: str) -> tuple[bool, str]:
    """Whether [source] can supply [field_key] for target→native, and why not."""
    s = SOURCES[source]
    by_field = s.supports.get(target)
    if by_field is None:
        return False, f"不支援目標語言 {LANGUAGES[target]['zh']}"
    natives = by_field.get(field_key)
    if natives is None:
        return False, f"不提供「{FIELD[field_key].label}」"
    if "*" in natives or native in natives:
        return True, ""
    return False, f"不支援 {LANGUAGES[target]['zh']}→{LANGUAGES[native]['zh']} 這個方向"


# ── Default policies ──────────────────────────────────────────────────
# (sources in order, strategy, limit). English defaults are the spec's
# 英文預設 Policy table; fields the table doesn't list get sensible ones.

_IMAGE_SOURCES = ["wikimedia_commons", "open_images", "smithsonian", "openverse"]
_EN_DEFAULTS = {
    "pos": (["kaikki", "oewn"], "FILL_MISSING", None),
    "definition": (["kaikki", "oewn"], "FILL_MISSING", 12),
    "native_definition": (["kaikki"], "FILL_MISSING", None),
    "cefr": (["cefrj", "local_calc"], "FIRST_VALID", None),
    "frequency": (["wordfreq", "datamuse"], "FIRST_VALID", None),
    "usage_labels": (["kaikki"], "MERGE_UNIQUE", 10),
    "ipa": (["kaikki", "cmudict", "local_calc"], "FIRST_VALID", 6),
    "phonemes": (["cmudict", "kaikki"], "FIRST_VALID", 3),
    "syllables": (["kaikki", "cmudict"], "FIRST_VALID", 2),
    "stress": (["cmudict", "local_calc"], "FIRST_VALID", 2),
    "accent_labels": (["kaikki"], "MERGE_UNIQUE", 8),
    "audio": (["kaikki", "wikimedia_commons"], "MERGE_UNIQUE", 6),
    "tts_fallback": (["system_tts"], "FIRST_VALID", 1),
    "synonyms": (["oewn", "kaikki", "datamuse"], "MERGE_UNIQUE", 8),
    "antonyms": (["oewn", "kaikki", "datamuse"], "MERGE_UNIQUE", 5),
    "hypernyms": (["oewn", "kaikki", "datamuse"], "MERGE_UNIQUE", 5),
    "hyponyms": (["oewn", "kaikki", "datamuse"], "MERGE_UNIQUE", 8),
    "related": (["oewn", "kaikki", "datamuse"], "MERGE_UNIQUE", 8),
    "homophones": (["cmudict", "datamuse", "kaikki"], "MERGE_UNIQUE", 5),
    "near_homophones": (["cmudict", "datamuse", "kaikki"], "MERGE_UNIQUE", 5),
    "similar_spelling": (["kaikki_wordlist", "datamuse"], "MERGE_UNIQUE", 6),
    "derived_terms": (["kaikki", "oewn"], "MERGE_UNIQUE", 12),
    "derivation_relation": (["local_calc"], "FILL_MISSING", None),
    "derived_pos": (["lexicon", "oewn", "local_calc"], "FILL_MISSING", None),
    "derived_native_meaning": (["lexicon", "kaikki"], "FILL_MISSING", None),
    "morphemes": (["kaikki", "morph_local"], "FIRST_VALID", 1),
    "morphemes_native": (["morph_local", "lexicon", "kaikki"], "FILL_MISSING",
                         None),
    "root": (["kaikki", "morph_local"], "FILL_MISSING", None),
    "prefix": (["kaikki", "morph_local"], "FILL_MISSING", None),
    "suffix": (["kaikki", "morph_local"], "FILL_MISSING", None),
    "origin_language": (["kaikki"], "FIRST_VALID", 3),
    "original_form": (["kaikki"], "FIRST_VALID", 3),
    "etymology_text": (["kaikki"], "FILL_MISSING", None),
    "etymology_native": ([], "FIRST_VALID", None),
    "example_sentences": (["tatoeba", "kaikki", "oewn"], "APPEND_LIMITED", 30),
    "example_difficulty": (["local_calc"], "FILL_MISSING", None),
    "example_sense": (["kaikki", "local_calc"], "FILL_MISSING", None),
    "example_translation": (["tatoeba"], "FILL_MISSING", None),
    "sense_image": (_IMAGE_SOURCES, "APPEND_LIMITED", 3),
    "context_image": (_IMAGE_SOURCES, "APPEND_LIMITED", 3),
    "thumbnail": (_IMAGE_SOURCES, "APPEND_LIMITED", 3),
    "image_alt_native": ([], "FILL_MISSING", None),
}
for _f in FORM_FIELDS:
    _EN_DEFAULTS.setdefault(_f, (["kaikki"], "FIRST_VALID", 3))
_EN_DEFAULTS["noun_plural"] = (["kaikki", "local_calc"], "FIRST_VALID", 3)
for _r in RELATION_FIELDS:
    _EN_DEFAULTS[f"{_r}_native"] = (["lexicon", "kaikki"], "FILL_MISSING", None)
# Fields filled per CEFR level (A1–C2): (at least, at most) items each level
# keeps; a candidate's slot is its level (pipeline.level_candidates).
# Relation words keep three a level: each one needs a native meaning.
LEVELED = {"example_sentences": (3, 5), "synonyms": (3, 3), "related": (3, 3)}
# Example sentences a learner reads at a glance.
MAX_EXAMPLE_WORDS = 20

# Field states that are done: a value, the admin's value, 「查無」 (every
# source answered and a word simply has none: calendar has no antonym), or
# 「不適用」 (a noun has no past tense).
DONE = ("complete", "user_override", "none", "not_applicable")
# 「缺漏」: every source (AI last) was asked and a target is still unmet (a
# level under three example sentences, no British recording). Shown as a
# gap everywhere, but a fill-missing run doesn't ask the sources again.
SHORT = "short"
SETTLED = DONE + (SHORT,)
# Two recordings a word: British (the default) and American. Other accents
# (AU, CA, unnamed Lingua Libre speakers) are kept as extras.
AUDIO_ACCENTS = ("UK", "US")
# Fields with a target per slot: at least / at most items each slot keeps.
TARGETED = {**LEVELED, "audio": (1, 1)}
# Fields a word may simply not have.
MAY_BE_EMPTY = {"antonyms", "hypernyms", "hyponyms", "homophones", "near_homophones",
                "similar_spelling", "derived_terms", "usage_labels", "accent_labels",
                "origin_language", "original_form", "etymology_text", "prefix", "suffix",
                "adj_comparative", "adj_superlative", "noun_plural",
                # a headword that is itself a form (dappled, garnished) has none
                "verb_base", "verb_past", "verb_past_participle", "verb_present_participle",
                "verb_third_person"}
# Forms that belong to one part of speech.
FORM_POS = {"verb_base": "verb", "verb_past": "verb", "verb_past_participle": "verb",
            "verb_present_participle": "verb", "verb_third_person": "verb",
            "noun_plural": "noun", "adj_comparative": "adj", "adj_superlative": "adj"}
for _f in LEVELED:
    _src, _strategy, _limit = _EN_DEFAULTS[_f]
    _EN_DEFAULTS[_f] = ([*_src, "ai_translate"], _strategy, 30)
# Translations into the native language the dictionaries lack come from AI,
# always last and marked as AI.
AI_TRANSLATED = ("native_definition", "example_translation", "derived_native_meaning",
                 "morphemes_native", "etymology_native",
                 *(f"{_r}_native" for _r in RELATION_FIELDS))
for _f in AI_TRANSLATED:
    _src, _strategy, _limit = _EN_DEFAULTS[_f]
    _EN_DEFAULTS[_f] = ([*_src, "ai_translate"], _strategy, _limit)


def default_policy(target: str, native: str, field_key: str) -> tuple[list[str], str, int | None]:
    """Default steps for one field and direction: the English table,
    keeping only sources that support this direction. Empty = 未設定."""
    sources, strategy, limit = _EN_DEFAULTS[field_key]
    ok = [s for s in sources if supports(s, target, native, field_key)[0]]
    if not ok and field_key in ("definition", "pos"):
        ok = [s for s in ("kaikki",) if supports(s, target, native, field_key)[0]]
    return ok, strategy, limit


# Native names for labels the learner sees (localized_labels).
LABELS = {
    "pos:noun": {"zh-TW": "名詞", "fr": "nom", "en": "noun"},
    "pos:verb": {"zh-TW": "動詞", "fr": "verbe", "en": "verb"},
    "pos:adj": {"zh-TW": "形容詞", "fr": "adjectif", "en": "adjective"},
    "pos:adv": {"zh-TW": "副詞", "fr": "adverbe", "en": "adverb"},
    "pos:phrase": {"zh-TW": "片語", "fr": "locution", "en": "phrase"},
    "pos:prep": {"zh-TW": "介系詞", "fr": "préposition", "en": "preposition"},
    "pos:pron": {"zh-TW": "代名詞", "fr": "pronom", "en": "pronoun"},
    "pos:num": {"zh-TW": "數詞", "fr": "numéral", "en": "numeral"},
    "pos:intj": {"zh-TW": "感嘆詞", "fr": "interjection", "en": "interjection"},
    "pos:conj": {"zh-TW": "連接詞", "fr": "conjonction", "en": "conjunction"},
    "pos:det": {"zh-TW": "限定詞", "fr": "déterminant", "en": "determiner"},
    "accent:US": {"zh-TW": "美式", "fr": "américain", "en": "US"},
    "accent:UK": {"zh-TW": "英式", "fr": "britannique", "en": "UK"},
    "accent:AU": {"zh-TW": "澳洲", "fr": "australien", "en": "Australian"},
    "accent:CA": {"zh-TW": "加拿大", "fr": "canadien", "en": "Canadian"},
    **{f"form:{f.key}": {"zh-TW": f.label, "en": f.key.replace("_", " "), "fr": f.label}
       for f in FIELDS if f.block == "forms"},
    **{f"relation:{k}": v for k, v in {
        "synonyms": {"zh-TW": "同義詞", "fr": "synonyme", "en": "synonym"},
        "antonyms": {"zh-TW": "反義詞", "fr": "antonyme", "en": "antonym"},
        "hypernyms": {"zh-TW": "上位詞", "fr": "hyperonyme", "en": "hypernym"},
        "hyponyms": {"zh-TW": "下位詞", "fr": "hyponyme", "en": "hyponym"},
        "related": {"zh-TW": "相關詞", "fr": "mot apparenté", "en": "related"},
        "homophones": {"zh-TW": "同音字", "fr": "homophone", "en": "homophone"},
        "near_homophones": {"zh-TW": "近音字", "fr": "paronyme", "en": "near homophone"},
        "similar_spelling": {"zh-TW": "拼字相近", "fr": "orthographe proche", "en": "similar spelling"},
        "derived_terms": {"zh-TW": "衍生詞", "fr": "dérivé", "en": "derived term"},
    }.items()},
}
