"""The SourceAdapter interface (spec section 08, 來源 Adapter 與資料候選值).

Every source implements download_snapshot(), lookup(), normalize() and
validate(); media sources also implement download_audio(). lookup()
fetches the raw record for a headword, normalize() turns it into
Candidates for one exact field, validate() rejects bad ones with a reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .. import catalog
from ..text import CJK, fold, looks_simplified, normalize_lemma, taiwanize
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
    if CJK.search(c.key or ""):
        c.key = taiwanize(c.key)
    if CJK.search(c.slot or ""):
        c.slot = taiwanize(c.slot)



ARPABET = re.compile(r"^[A-Z]{1,2}[012]?( [A-Z]{1,2}[012]?)*( \| [A-Z]{1,2}[012]?( [A-Z]{1,2}[012]?)*)*$")
IPA_CHARS = re.compile(r"[ˈˌəɪʊɛæɑɔʌθðʃʒŋɹɜɒɐɚɝ̃ːʁɥøœ]")
WORDISH = re.compile(r"^[\w'’\- .]+$", re.UNICODE)


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
    elif f == "example_sentences":
        if not text:
            return "空白例句"
        if len(text) > 240:
            return "例句過長（> 240 字元）"
        if ctx.target == "en" and len(text.split()) < 3:
            return "少於 3 個字，不像完整句子"
        if ctx.target != "zh-TW" and len(text.split()) > catalog.MAX_EXAMPLE_WORDS:
            return f"超過 {catalog.MAX_EXAMPLE_WORDS} 個字"
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
        if len(text) > 400:
            return "翻譯過長"
    elif f in catalog.RELATION_FIELDS or f == "derived_terms":
        w = v.get("word", "")
        if not w or len(w) > 64:
            return "空白或過長的詞"
        if normalize_lemma(w, ctx.target) == ctx.lemma:
            return "和詞條本身相同"
    return None
