"""The SourceAdapter interface (spec section 08, 來源 Adapter 與資料候選值).

Every source implements download_snapshot(), lookup(), normalize() and
validate(); media sources also implement download_audio(). lookup()
fetches the raw record for a headword, normalize() turns it into
Candidates for one exact field, validate() rejects bad ones with a reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime, timezone
from typing import Any

from .. import catalog
from ..text import (CJK, fold, looks_simplified, native_latin_issue, normalize_lemma, taiwanize,
                    is_column_word_list)
from .http import SourceError  # noqa: F401 — re-exported for adapters


@dataclass
class Candidate:
    field: str
    language: str
    value: dict
    key: str  # dedupe key within the field
    source: str = ""
    slot: str = ""  # the unit FILL_MISSING fills: a sense, an example, a word …
    source_record_id: str = ""
    confidence: float = 1.0
    license: str = ""
    attribution: str = ""
    raw_value: Any = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid: bool = True
    invalid_reason: str | None = None
    snapshot_id: int | None = None

    def public(self) -> dict:
        return {"value": self.value, "key": self.key, "slot": self.slot,
                "source": self.source, "source_record_id": self.source_record_id,
                "confidence": round(self.confidence, 3), "language": self.language,
                "valid": self.valid, "invalid_reason": self.invalid_reason}


@dataclass
class Context:
    """One headword being processed for one language direction."""
    target: str
    native: str
    lemma: str  # normalized headword
    display: str = ""  # as written
    # Items adopted so far this run, by field (dependencies of later fields).
    resolved: dict[str, list[dict]] = field(default_factory=dict)
    refresh: bool = False
    timeout: float = 20
    retries: int = 2
    session: Any = None  # SQLAlchemy session, for the lexicon adapter
    memo: dict = field(default_factory=dict)  # per-run raw records, by source

    def items(self, field_key: str) -> list[dict]:
        return self.resolved.get(field_key) or []


class SourceAdapter:
    key: str = ""

    @property
    def meta(self) -> catalog.Source:
        return catalog.SOURCES[self.key]

    # ── snapshots ──
    def download_snapshot(self, language: str, snapshot_dir) -> dict:
        """Download a versioned copy of the source into raw-data/. Returns
        {"version", "url", "path", "files", "row_count", "details"}."""
        raise NotImplementedError(f"{self.meta.name} 沒有可下載的快照（即時 API 或本機計算）")

    # ── lookup ──
    def fetch(self, ctx: Context) -> Any:
        """The raw record(s) for ctx.lemma. Memoized per run."""
        return None

    def raw(self, ctx: Context) -> Any:
        k = (self.key, ctx.target, ctx.lemma)
        if k not in ctx.memo:
            ctx.memo[k] = self.fetch(ctx)
        return ctx.memo[k]

    def normalize(self, field_key: str, raw: Any, ctx: Context) -> list[Candidate]:
        return []

    def lookup(self, field_key: str, ctx: Context) -> list[Candidate]:
        cands = self.normalize(field_key, self.raw(ctx), ctx)
        for c in cands:
            c.source = self.key
            c.license = c.license or self.meta.license
            c.attribution = c.attribution or self.meta.attribution
            reason = self.validate(c, ctx)
            if reason:
                c.valid, c.invalid_reason = False, reason
        return cands

    # ── validation ──
    def validate(self, c: Candidate, ctx: Context) -> str | None:
        localize(c, ctx)
        return validate(c, ctx)

    def download_audio(self, item: dict, dest_dir):
        raise NotImplementedError


# ── Word frequency: common words first ─────────────────────────────

WF_LANG = {"en": "en", "fr": "fr", "zh-TW": "zh"}


def zipf(word: str, language: str) -> float:
    try:
        from wordfreq import zipf_frequency
        return zipf_frequency(word, WF_LANG.get(language, language))
    except ImportError:
        return 3.0


def frequency_profile(value: float) -> dict:
    """Learner-facing rarity plus a conservative CEFR estimate.

    CEFR is vocabulary-specific when CEFR-J has a record. This fallback is
    explicitly marked as a frequency estimate so clients never present it as
    an official CEFR classification.
    """
    if value >= 5.0:
        rarity, level = "common", "A1"
    elif value >= 4.5:
        rarity, level = "everyday", "A2"
    elif value >= 4.0:
        rarity, level = "less_common", "B1"
    elif value >= 3.5:
        rarity, level = "uncommon", "B2"
    elif value >= 3.0:
        rarity, level = "rare", "C1"
    else:
        rarity, level = "very_rare", "C2"
    return {"zipf": value, "rarity": rarity, "cefr": level,
            "cefr_source": "frequency_estimate", "hide_by_default": value < 2.5}


def by_frequency(cands: list[Candidate], language: str, floor: float | None = None
                 ) -> list[Candidate]:
    """Relation words, most common first (a learner needs "happiness"
    before "happyish"); rare ones lose confidence, and words under
    [floor] (unknown or junk spellings) are dropped."""
    scored = [(round(zipf(c.value.get("word", ""), language), 1), c) for c in cands]
    out = []
    for z, c in sorted(scored, key=lambda zc: -zc[0]):
        if floor is not None and z < floor:
            continue
        if z < 1.5:
            c.confidence = round(c.confidence * 0.6, 3)
        for key, value in frequency_profile(z).items():
            c.value.setdefault(key, value)
        out.append(c)
    return out


# ── Shared validation rules ───────────────────────────────────────────

def localize(c: Candidate, ctx: Context) -> None:
    """Chinese for Taiwan: Mainland words and variants become the ones
    used in Taiwan (意大利麵 → 義大利麵, 芝士 → 起司) in every language pair
    with zh-TW, whichever source the text came from."""
    if "zh-TW" not in (ctx.target, ctx.native, c.language):
        return
    c.value = taiwanize(c.value)
    if c.field == "native_definition" and c.language == "zh-TW" and c.value.get("text"):
        from ..text import normalize_native_gloss
        c.value["text"] = normalize_native_gloss(c.value["text"])
    if CJK.search(c.key or ""):
        c.key = taiwanize(c.key)
    if CJK.search(c.slot or ""):
        c.slot = taiwanize(c.slot)



ARPABET = re.compile(r"^[A-Z]{1,2}[012]?( [A-Z]{1,2}[012]?)*( \| [A-Z]{1,2}[012]?( [A-Z]{1,2}[012]?)*)*$")
IPA_CHARS = re.compile(r"[ˈˌəɪʊɛæɑɔʌθðʃʒŋɹɜɒɐɚɝ̃ːʁɥøœ]")
WORDISH = re.compile(r"^[\w'’\- .]+$", re.UNICODE)


@lru_cache(maxsize=50_000)
def is_proper_noun(word: str, language: str) -> bool:
    """Only a name in the dictionary: every Kaikki entry spelled this way
    (any case) is a proper noun — people (brett, woolf), places (Antarctica,
    Lake Victoria), brands. A capitalised common noun (Bengal tiger) or a
    word that is also common (stein, toby) is not. False without the index."""
    from .. import kaikki_index
    entries = kaikki_index.lookup(language, word) or []
    same = [e for e in entries if str(e.get("word", "")).lower() == word.lower()]
    return bool(same) and all(e.get("pos") == "name" for e in same)


# A sense like these doesn't make an inflected form a word of its own
# (runs 「the runs」 slang for diarrhoea, eaten 「in compounds」).
MINOR_SENSE_TAGS = {"obsolete", "archaic", "dated", "rare", "slang", "humorous", "nonstandard",
                    "vulgar", "derogatory", "offensive", "euphemistic", "poetic", "dialectal",
                    "in-compounds", "alt-of", "abbreviation", "clipping", "misspelling"}


@lru_cache(maxsize=50_000)
def inflection_bases(word: str, language: str) -> tuple[str, ...]:
    """The words an inflected form belongs to, when the dictionary gives it
    no meaning of its own: runs → run, children → child, leaves → leaf and
    leave. Empty for a form that is also a word (lying 說謊的, spotted
    有斑點的, tethered) and without the index (問題回報 #51)."""
    from .. import kaikki_index
    w = word.strip().lower()
    entries = [e for e in kaikki_index.lookup(language, w) or []
               if str(e.get("word", "")).lower() == w and e.get("pos") != "name"]
    bases: list[str] = []
    for e in entries:
        for s in e.get("senses") or []:
            if s.get("form_of"):
                bases += [str(f.get("word") or "") for f in s["form_of"]]
            elif (s.get("glosses") or [""])[0].strip() \
                    and not MINOR_SENSE_TAGS & set(s.get("tags") or []):
                return ()  # a meaning of its own
    # Lower case (apples → apple, not the brand Apple) and in use (children
    # → child, not the dialectal childer).
    return tuple(b for b in dict.fromkeys(bases)
                 if b and b == b.lower() and b != w and " " not in b and zipf(b, language) >= 2.5)


ACT_NOUN = re.compile(r"^(the|an?)\s+(act|action|process|practice)\b", re.I)


@lru_cache(maxsize=1)
def _listed_levels() -> dict[str, int]:
    """A word's easiest CEFR-J / Octanove level, as an index (A1 = 0)."""
    from .local import LEVELS, cefr_list
    return {w: min(LEVELS.index(lv) for lv in hit[1].values())
            for w, hit in cefr_list().items() if hit and hit[1]}


@lru_cache(maxsize=50_000)
def card_base(word: str, language: str) -> str | None:
    """The word whose card a form shares (問題回報 #51, owner 2026-10-14:
    詞形變化跟原形共用同一張卡片): runs → run, and a form whose own meaning
    is still the participle's — tethered 被拴住的 → tether, dried → dry,
    lying 躺著的、說謊的 → lie (an adjective, an adverb or 「the act of …」 in
    the same etymology as the form). Not another word spelt the same: left
    左邊 (another etymology), building 建築物, glasses 眼鏡, painting 畫
    (things of their own); nor a word learners study on its own (tired,
    excited: listed at an easier level than tire, excite, so met first).
    None without the index."""
    from .. import kaikki_index
    w = word.strip().lower()
    pure = inflection_bases(w, language)
    if pure:
        return pure[0] if len(pure) == 1 else None  # leaves: leaf or leave
    if " " in w:
        return None
    entries = [e for e in kaikki_index.lookup(language, w) or []
               if str(e.get("word", "")).lower() == w and e.get("pos") != "name"]

    def own(e):
        return [s for s in e.get("senses") or [] if not s.get("form_of")
                and (s.get("glosses") or [""])[0].strip()
                and not MINOR_SENSE_TAGS & set(s.get("tags") or [])]

    first = next((e for e in entries if own(e)), None)
    if first is None:
        return None
    ety = first.get("etymology_number")
    same = [e for e in entries if e.get("etymology_number") == ety]
    for e in same:
        for s in own(e):
            if e.get("pos") not in ("adj", "adv") and not (
                    e.get("pos") == "noun" and ACT_NOUN.match(s["glosses"][0])):
                return None  # a thing of its own (building, glasses)
    bases = [str(f.get("word") or "") for e in same for s in e.get("senses") or []
             for f in s.get("form_of") or []]
    bases = [b for b in dict.fromkeys(bases)
             if b and b == b.lower() and b != w and zipf(b, language) >= 2.5]
    if not bases:
        return None
    base = max(bases, key=lambda b: zipf(b, language))
    if language == "en":
        levels = _listed_levels()
        if w in levels and levels[w] < levels.get(base, 99):
            return None  # tired A1 before tire: a word of its own to learners
    return base


def validate(c: Candidate, ctx: Context) -> str | None:
    v = c.value
    f = c.field
    text = v.get("text") or v.get("gloss") or ""
    if f == "ipa":
        ipa = v.get("ipa", "")
        if not ipa or not (ipa.startswith(("/", "[")) and ipa.endswith(("/", "]"))):
            return "IPA 必須以 /…/ 或 […] 標示"
        if ARPABET.match(ipa.strip("/[]")):
            return "這是 ARPAbet 音素，不是 IPA"
    elif f == "phonemes":
        if not ARPABET.match(v.get("phonemes", "")):
            return "不是 ARPAbet 音素序列"
    elif f == "audio":
        if v.get("tts"):
            return None
        url = v.get("url", "")
        if not url.startswith("https://") or not re.search(r"\.(mp3|ogg|oga|wav|flac|opus)$",
                                                           url, re.I):
            return "音檔網址不是 https 的 mp3／ogg／wav／flac"
    elif f in catalog.FORM_FIELDS:
        form = v.get("form", "")
        if not form or not WORDISH.match(form) or len(form) > 64:
            return "詞形不是單一詞"
        if ctx.target == "en":
            # Dictionary dumps occasionally attach a neighbouring spelling
            # as an inflection (for example pan -> pen).  A source label is
            # not enough evidence: reject forms that cannot be produced from
            # the headword (or the shared base of an inflected headword).
            from .local import plausible_form
            if not plausible_form(v.get("base") or ctx.lemma, form):
                return "詞形和詞條的拼字變化不合理"
    elif f in ("definition",):
        if not text or len(text) < 2:
            return "空白釋義"
        if len(text) > 600:
            return "釋義過長"
    elif f == "register":
        if v.get("register") not in {"neutral", "written", "spoken", "slang"}:
            return "語體必須是 neutral／written／spoken／slang"
        if not v.get("sense_key"):
            return "語體沒有對應詞義"
    elif f == "example_sentences":
        if not text:
            return "空白例句"
        if is_column_word_list(text, ctx.lemma):
            return "詞彙欄位清單，不是學習例句"
        if len(text) > 240:
            return "例句過長（> 240 字元）"
        if ctx.target == "en" and len(text.split()) < 3:
            return "少於 3 個字，不像完整句子"
        if ctx.target != "zh-TW" and len(text.split()) > catalog.MAX_EXAMPLE_WORDS:
            return f"超過 {catalog.MAX_EXAMPLE_WORDS} 個字"
        if ctx.target == "en":
            from ..quality import example_flags as _example_flags
            from .local import word_forms as _word_forms
            if "not_sentence" in _example_flags(text, ctx.lemma, "", list(_word_forms(ctx))):
                return "不是完整句"
        if not ctx.target.startswith("zh"):
            # Import lazily: local imports Candidate from this module.
            from .local import word_forms
            forms = word_forms(ctx)
            folded = f" {fold(text)} "
            if not any(f" {fold(x)} " in folded for x in forms if x):
                return "例句沒有用到這個字或可信詞形"
    elif f == "morphemes":
        from ..morphology import reconstructs
        parts = v.get("parts") or []
        if not parts:
            return "沒有拆解結果"
        if any(p.get("kind") not in ("prefix", "root", "suffix") or not p.get("part")
               for p in parts):
            return "部件格式錯誤（需要 part 與 prefix／root／suffix）"
        word = ctx.display or ctx.lemma
        if not (reconstructs(word, [p.get("text") or p["part"] for p in parts])
                or reconstructs(word, [p["part"] for p in parts])):
            return "拆出的部件拼不回原字"
    elif catalog.FIELD.get(f) and catalog.FIELD[f].scope == "native":
        if not text:
            return "空白翻譯"
        if c.language == "zh-TW":
            if not CJK.search(text):
                return "不是中文"
            if looks_simplified(text):
                return "簡體字（繁中資料包需繁體）"
            latin = native_latin_issue(text)
            if latin:
                return f"夾雜拉丁字母／殘字：{latin}"
        if len(text) > 400:
            return "翻譯過長"
    elif f in catalog.RELATION_FIELDS or f == "derived_terms":
        w = v.get("word", "")
        if not w or len(w) > 64:
            return "空白或過長的詞"
        if normalize_lemma(w, ctx.target) == ctx.lemma:
            return "和詞條本身相同"
        # Spec: 排除人名、品牌…及其他專有名詞 (問題回報 #22).
        if is_proper_noun(w, ctx.target):
            return "專有名詞（人名、地名、品牌），不收為關係詞"
    return None
