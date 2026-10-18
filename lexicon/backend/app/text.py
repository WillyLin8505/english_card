"""Normalization shared by adapters, the resolver and the exporter."""

from __future__ import annotations

import hashlib
import re
import unicodedata

CJK = re.compile(r"[㐀-鿿豈-﫿]")


def is_column_word_list(text: str, lemma: str) -> bool:
    """Recognize short, lowercase compound-word columns, not general prose.

    Keep the original text in source records. Do not infer grammaticality from
    a missing full stop: ordinary prose and short utterances remain eligible.
    """
    parts = [p.strip() for p in re.split(r"\t+|[\u2002-\u200a]{2,}| {3,}", text or "") if p.strip()]
    head = (lemma or "").strip().lower()
    return bool(head) and len(parts) >= 2 and all(
        p == p.lower() and re.fullmatch(r"[a-z'’ -]+", p)
        and len(p.split()) <= 4 and (p == head or p.endswith(' ' + head))
        for p in parts)


def normalize_lemma(word: str, language: str = "en") -> str:
    """Case, Unicode and whitespace folding for lookups (diacritics kept:
    French "côte" and "cote" are different words)."""
    w = unicodedata.normalize("NFC", word or "").strip()
    w = re.sub(r"\s+", " ", w)
    w = w.replace("’", "'")
    return w if language.startswith("zh") else w.lower()


def fold(text: str) -> str:
    """Loose form for comparing sentences and glosses."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def entry_type_of(normalized: str) -> str:
    """spec-01 §7 片語標籤: a multi-token normalized form is a phrase; no
    source reliably distinguishes phrasal verb / idiom / collocation / fixed
    expression yet, so stay with the generic, never-guessed "phrase"."""
    return "phrase" if " " in (normalized or "").strip() else "word"


def text_hash(text: str) -> str:
    return hashlib.sha1(fold(text).encode("utf-8")).hexdigest()


def sense_key(pos: str, gloss: str) -> str:
    return hashlib.sha1(f"{pos}|{fold(gloss)}".encode("utf-8")).hexdigest()[:12]


def example_key(text: str) -> str:
    return text_hash(text)[:12]


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-zà-ÿœæ']+", (text or "").lower())


_cc = {}


def opencc(config: str, text: str) -> str | None:
    """OpenCC conversion (s2twp: Simplified → Taiwan Traditional), if installed."""
    try:
        if config not in _cc:
            import opencc as oc
            _cc[config] = oc.OpenCC(config)
        return _cc[config].convert(text)
    except ImportError:
        return None


_script_tables: tuple[frozenset, frozenset] | None = None


def _script_chars() -> tuple[frozenset, frozenset] | None:
    """(Simplified-only, Traditional-only) characters from OpenCC's
    character tables, or None without them. A character both scripts write
    (台, 岩, 里, 污, 后, 面) is in neither."""
    global _script_tables
    if _script_tables is None:
        try:
            import os
            import opencc as oc
        except ImportError:
            return None
        folder = os.path.join(os.path.dirname(oc.__file__), "dictionary")
        tables = []
        for name in ("STCharacters.txt", "TSCharacters.txt"):
            path = os.path.join(folder, name)
            if not os.path.exists(path):
                return None
            only = set()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    k, _, v = line.rstrip("\n").partition("\t")
                    if len(k) == 1 and v and k not in v.split():
                        only.add(k)
            tables.append(only)
        simp = (tables[0] | set(SIMPLIFIED_IN_TAIWAN)) - set(WRITTEN_IN_TAIWAN)  # 雇用
        _script_tables = (frozenset(simp), frozenset(tables[1]))
    return _script_tables


# Characters OpenCC respells inside some phrases although Taiwan writes
# them that way too (工作台, 岩壁, 染污, 排泄, 折痕, 家具, 和弦, 雇用).
# 群 and 床 are Taiwan-standard too; STCharacters also lists historical
# variants (羣/牀), which does not make these two characters Simplified.
WRITTEN_IN_TAIWAN = "台岩污泄托睾卷折布注弦胡拐克回同扣彩欲蒙栗雇檐痹家具群床"


def looks_simplified(text: str) -> bool:
    """More Simplified-only characters than Traditional-only ones, counted
    character by character. Text written only in characters both scripts
    use is Simplified when OpenCC respells it the way Taiwan doesn't
    (之后 → 之後, 意大利面 → 意大利麵), not for spellings Taiwan uses as well
    (工作台, 岩壁 — these were rejected as Simplified, 問題回報 #24)."""
    chars = _script_chars()
    if chars is not None:
        simp, trad = chars
        n_simp = sum(ch in simp for ch in text)
        n_trad = sum(ch in trad for ch in text)
        if n_simp or n_trad:
            return n_simp > n_trad
        to_tw = opencc("s2tw", text)
        return bool(to_tw) and len(to_tw) == len(text) and any(
            a != b and a not in WRITTEN_IN_TAIWAN for a, b in zip(text, to_tw))
    # Without the tables: the Taiwan-standard conversion (plain s2t also
    # rewrites 吃 as 喫).
    to_trad, to_simp = opencc("s2tw", text), opencc("t2s", text)
    if to_trad is None or to_simp is None or len(to_trad) != len(text) \
            or len(to_simp) != len(text):
        return bool(to_trad and to_trad != text)
    simp_only = sum(a != b for a, b in zip(text, to_trad))
    trad_only = sum(a != b for a, b in zip(text, to_simp))
    return simp_only > trad_only


# ── Taiwan usage ──────────────────────────────────────────────────────
# Sources often give Mainland words written in Traditional characters
# (意大利麵, 芝士, 視頻). Simplified text goes through OpenCC s2twp once;
# Traditional text only gets Taiwan character variants and the words below.
# (OpenCC's phrase table is not used on Traditional text: it is meant for a
# single pass over Mainland text and rewrites Taiwanese 程序, 文件, 社區.)
# Only whole words that can't be read inside another word are listed —
# not 的士 (國家的士兵), 面包 alone (外面包裝 — only 片面包, 烤面包 … are
# listed), 小區 (大小區別). A word mapped to
# itself is protected; every result is protected too, so converting twice
# changes nothing (柳橙汁 stays 柳橙汁).
TW_WORDS = """
站臺 月臺|站台 月臺|芝士 起司|奶酪 乳酪|酸奶 優格|酸奶油 酸奶油|黃油 奶油|淡奶油 鮮奶油|蛋黃醬 美乃滋|色拉 沙拉|沙律 沙拉
西紅柿 番茄|土豆 馬鈴薯|薯片 洋芋片|馬鈴薯片 馬鈴薯片|菠蘿 鳳梨|菠蘿麵包 菠蘿麵包|菠蘿包 菠蘿包
獼猴桃 奇異果|牛油果 酪梨|鱷梨 酪梨|車釐子 櫻桃|橙子 柳橙|橙汁 柳橙汁|西蘭花 花椰菜|花菜 花椰菜
捲心菜 高麗菜|卷心菜 高麗菜|圓白菜 高麗菜|紅薯 地瓜|三文魚 鮭魚|金槍魚 鮪魚|冰激凌 冰淇淋|冰激淩 冰淇淋
冰棍 冰棒|方便麵 泡麵|意大利 義大利|通心粉 通心麵|曲奇 餅乾|蛋撻 蛋塔|朱古力 巧克力|法棍 法國麵包
牛角包 可頌|羊角麵包 可頌|匹薩 披薩|漢堡包 漢堡|煙肉 培根|盒飯 便當|飯盒 便當盒|快餐 速食|外賣員 外送員
外賣 外帶|勺子 湯匙|調羹 湯匙|菜板 砧板|案板 砧板|切菜板 砧板|錫紙 鋁箔紙|電飯煲 電鍋|電飯鍋 電鍋
高壓鍋 壓力鍋|洗潔精 洗碗精|洗衣液 洗衣精|洗髮水 洗髮精|沐浴露 沐浴乳|護髮素 潤髮乳|衛生巾 衛生棉
衛生間 洗手間|空調 冷氣|中央空調 中央空調|空氣淨化器 空氣清淨機|出租車 計程車|公交車 公車|公共汽車 公車
摩托車 機車|自行車 腳踏車|地鐵 捷運|人行橫道 斑馬線|駕駛證 駕照|筆記本電腦 筆記型電腦|手提電腦 筆記型電腦|手提計算機 筆記型電腦
智能手機 智慧型手機|人工智能 人工智慧|數碼 數位|充電寶 行動電源|移動電話 行動電話|打印機 印表機|打印 列印
硬盤 硬碟|U盤 隨身碟|光盤 光碟|軟件 軟體|硬件 硬體|視頻 影片|網絡 網路|互聯網 網際網路|鼠標 滑鼠
屏幕 螢幕|短信 簡訊|信息 資訊|服務器 伺服器|數據庫 資料庫|激光 雷射|默認 預設|內存 記憶體|博客 部落格
點贊 按讚|郵箱 信箱|酒店 飯店|賓館 旅館|便利店 便利商店|幼兒園 幼稚園|藥店 藥局|寫字樓 辦公大樓
乒乓球 桌球|瑜伽 瑜珈|羽絨服 羽絨外套|塑料 塑膠|新西蘭 紐西蘭|澳大利亞 澳洲|悉尼 雪梨|麪 麵
片面包 片麵包|烤面包 烤麵包|吃面包 吃麵包|面包店 麵包店|面包屑 麵包屑|面包機 麵包機|面包片 麵包片|全麥面包 全麥麵包
"""

# Simplified characters that are also written in Traditional text but, in
# Taiwan, almost only as Simplified (挂 for 掛). Others like 干 后 里 面 台 只
# 余 周 唇 are everyday Taiwanese characters and are never touched.
SIMPLIFIED_IN_TAIWAN = "万丰价党厂叶杰柜腊蜡挂帘淀据愿虫胜极确种适筑荐蚝蝎腌膻咸杠夸广苹"

_tw_tables: tuple[dict, dict, int] | None = None


def _tw() -> tuple[dict, dict, int]:
    """(character map, word table, longest word). The character map holds
    Simplified-only characters (a mixed sentence like 湯姆把日曆挂在墙上 isn't
    caught as Simplified as a whole) and OpenCC's Taiwan variants; the word
    table is TW_WORDS with every result protected."""
    global _tw_tables
    if _tw_tables is None:
        variants, words = {}, {}
        try:
            import os
            import opencc as oc
            folder = os.path.join(os.path.dirname(oc.__file__), "dictionary")
            path = os.path.join(folder, "STCharacters.txt")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        k, _, v = line.rstrip("\n").partition("\t")
                        options = v.split()
                        if k and options and (k not in options or k in SIMPLIFIED_IN_TAIWAN):
                            variants[k] = next(o for o in options if o != k)
            path = os.path.join(folder, "TWVariants.txt")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        k, _, v = line.rstrip("\n").partition("\t")
                        if k and v:
                            variants[k] = v.split(" ")[0]
            # Chains (a character mapped to one the variants rewrite again).
            for k, v in list(variants.items()):
                variants[k] = variants.get(v, v)
        except ImportError:
            pass
        variants.pop("幺", None)  # 么 alone reads as Simplified 麼
        for pair in TW_WORDS.replace("\n", "|").split("|"):
            k, _, v = pair.strip().partition(" ")
            if k and v:
                (variants if len(k) == 1 and len(v) == 1 else words)[k] = v
        for v in list(words.values()):
            words.setdefault(v, v)
        _tw_tables = (variants, words, max(map(len, words), default=1))
    return _tw_tables


def to_taiwan(text: str) -> str:
    """Chinese text in Taiwan usage: Simplified converted (OpenCC s2twp),
    Taiwan character variants, then Taiwan words for Mainland ones
    (意大利麵 → 義大利麵, 芝士 → 起司, 視頻 → 影片). Converting twice
    changes nothing."""
    if not text or not CJK.search(text):
        return text
    if looks_simplified(text):
        text = opencc("s2twp", text) or text
    variants, words, longest = _tw()
    text = "".join(variants.get(ch, ch) for ch in text)
    out, i = [], 0
    while i < len(text):
        for n in range(min(longest, len(text) - i), 1, -1):
            hit = words.get(text[i:i + n])
            if hit is not None:
                out.append(hit)
                i += n
                break
        else:
            out.append(text[i])
            i += 1
    text = "".join(out)
    # A list of words may now name one twice (匙子、調羹、湯匙 → …湯匙、湯匙).
    parts = text.split("、")
    if len(parts) > 1 and all(len(p) <= 8 and not re.search(r"[。！？，；]", p) for p in parts):
        text = "、".join(dict.fromkeys(parts))
    # Taiwan quotation marks: “滾石不生苔” → 「滾石不生苔」, ‘…’ → 『…』, and
    # straight quotes around Chinese.
    text = re.sub(r"“([^“”]*)”", r"「\1」", text)
    text = re.sub(r"‘([^‘’]*)’", r"『\1』", text)
    text = re.sub(r'"([^"]*[一-鿿][^"]*)"', r"「\1」", text)
    return text


def taiwanize(value):
    """to_taiwan over every string in a JSON-like value. Simplified strings
    are left as they are, so validation can still reject them."""
    if isinstance(value, str):
        return value if looks_simplified(value) else to_taiwan(value)
    if isinstance(value, list):
        return [taiwanize(v) for v in value]
    if isinstance(value, dict):
        return {k: taiwanize(v) for k, v in value.items()}
    return value


# Words never shown to learners as relation words (Datamuse lists 「shit」
# as related to grass).
OFFENSIVE = {"shit", "shitty", "bullshit", "fuck", "fucking", "fucked", "crap", "crappy", "bitch",
             "bastard", "dick", "cock", "cunt", "piss", "pissed", "asshole", "arse", "arsehole",
             "whore", "slut", "nigger", "nigga", "fag", "faggot", "retard", "retarded", "twat",
             "wank", "wanker", "bollocks", "tits", "boobs", "porn", "dildo", "jerk off", "blowjob",
             "prostitute", "prostitutes", "whores"}

# Explicit Chinese profanity that dictionaries and AI sometimes give as a
# translation (underdog 屌絲, catfight 撕逼). Single characters with clean
# uses (逼真, 鳥) are not listed.
ZH_OFFENSIVE = ("屌", "雞巴", "鸡巴", "傻逼", "傻屄", "屄", "撕逼", "裝逼", "牛逼", "肏",
                "他媽的", "他妈的", "操你", "王八蛋", "婊子")


# Common English abbreviations kept as-is in Taiwan Chinese usage (問題回報
# #187's acceptance criteria asks for a documented whitelist, not a blanket
# allowance): everyday tech/media acronyms a learner already reads in Latin
# script. Anything else in Latin script is either a leaked English word
# (table「背gammon遊戲」) or a stray fragment (ship「…CP」) — not a translation.
LATIN_OK_ABBR = {"DNA", "RNA", "HTTP", "HTTPS", "USB", "GPS", "DVD", "CD", "WIFI",
                 "VIP", "KTV", "ATM", "APP", "PDF", "LED", "TV", "AI", "ID"}
_LATIN_RUN = re.compile(r"[A-Za-z]+")
_PAREN_NOTE = re.compile(r"[（(][^）)]*[）)]")

# Card 29: explicit technical acronyms, not arbitrary uppercase fragments (CP).
_LATIN_TECH = {"CPU", "IRC", "IT", "QSL", "LGBT", "LGBTQ", "ASCII", "Unicode", "SI"}
_LATIN_CONTEXT = re.compile(
    r"(?<![A-Za-z])(?:T\s*恤|[UVXT]\s*[型形]|R&B)(?![A-Za-z])"
    r"|(?<=\d)\s*(?:mm|cm|km|kg|mg)(?![A-Za-z])")


def normalize_native_gloss(text: str) -> str:
    """Keep both sides of an explicit bilingual gloss, Chinese first.

    No translation or deletion: discredit（失譽） -> 失譽（discredit）.
    Only a single Latin word followed by a two/three-character CJK gloss;
    scientific names, formulas and unglossed fragments remain untouched.
    """
    def replace(match):
        # Do not split a multiword name or translate an already allowed acronym.
        if re.search(r"[A-Za-z]\s+$", text[:match.start()]) or not native_latin_issue(match[1]):
            return match[0]
        return f"{match[2]}（{match[1]}）"
    return re.sub(r"(?<![A-Za-z])([A-Za-z]{2,})\s*[（(]([㐀-鿿]{2,3})[）)]",
                  replace, text)


# A binomial (Felis catus) or a family/subfamily name may stay in Chinese only
# inside parentheses, so it is visibly a 學名 and not a leaked English word.
_SCI_NAME = re.compile(
    r"(?<![A-Za-z（(])("
    r"[A-Z][a-z]{2,}(?:\s+[a-z]{3,})+"
    r"|[A-Z][a-z]{2,}(?:idae|inae|aceae|oideae|ales|formes|oidea)"
    r")(?![A-Za-z）)])"
)
_GENUS_BEFORE = re.compile(r"(?<![A-Za-z（(])([A-Z][a-z]{3,})(?=\s*屬)")
_LOW_NATIVE_LABELS = {
    "obsolete", "archaic", "dated", "rare", "slang", "humorous", "nonstandard",
    "historical", "vulgar", "derogatory", "offensive", "euphemistic", "poetic",
    "informal", "colloquial", "dialectal", "low_priority",
}
_OBSCURE_GLOSS = re.compile(
    r"\b(?:simple past|past participle|present participle|gerund of|"
    r"third-person singular|alternative (?:spelling|form|letter-case form)|"
    r"pronunciation spelling|obsolete spelling|clipping of|initialism of|"
    r"synonym of|misspelling of|genus|species|subfamily|phylum)\b|"
    r"\b[A-Z][a-z]{2,}(?:idae|inae|aceae)\b|"
    r"\b(?:formally|hom-sets?)\b",
    re.I,
)


def mark_scientific_names(text: str) -> str:
    """Wrap a binomial or a family name in （） so the Latin is a marked 學名."""
    if not text:
        return text
    text = _SCI_NAME.sub(lambda m: f"（{m.group(1)}）", text)
    return _GENUS_BEFORE.sub(lambda m: f"（{m.group(1)}）", text)


def _low_native_label(item: dict) -> bool:
    labels = {str(x).lower() for x in item.get("labels") or []}
    return bool(labels & _LOW_NATIVE_LABELS or any(x.startswith("etymology-") for x in labels))


_POINTER_PAREN = re.compile(r"\(([^)]*)\)")
_POINTER_WORD = r"[A-Za-z][A-Za-z'-]*"
_POINTER_SYN = re.compile(
    rf"^(?:synonym|another (?:name|word|term)) of\s+({_POINTER_WORD})$", re.I)
_POINTER_LIST = re.compile(
    rf"^(?:(?:a|an)\s+)?{_POINTER_WORD}"
    rf"(?:\s*(?:,|;|or)\s+(?:(?:a|an)\s+)?{_POINTER_WORD})*$", re.I)
_POINTER_SKIP = {"a", "an", "or", "also", "to", "of", "from"}
_POINTER_SCI = re.compile(r"[A-Z][a-z]{2,}\s+[a-z]{3,}")


def synonym_pointer_lemmas(gloss: str | None) -> list[str] | None:
    """English words a gloss merely names, as in 「A nappy (UK), a diaper (American).」.

    A definition with a long parenthetical, or a scientific name, is not a pointer.
    None when the gloss is a real definition rather than a list of other words.
    """
    if not gloss or _POINTER_SCI.search(gloss):
        return None
    if any(len(p.strip()) > 16 for p in _POINTER_PAREN.findall(gloss)):
        return None
    bare = _POINTER_PAREN.sub(" ", gloss)
    bare = re.sub(r"[.“”\"']", " ", bare)
    bare = re.sub(r"\s+", " ", bare).strip(" .")
    named = _POINTER_SYN.match(bare)
    if named:
        return [named.group(1).lower()]
    if not _POINTER_LIST.match(bare):
        return None
    words = [w.lower() for w in re.findall(_POINTER_WORD, bare)
             if w.lower() not in _POINTER_SKIP]
    return words or None


def main_native_sense_key(items: list[dict]) -> str | None:
    """The sense learners see first: the first sense that is not low-priority."""
    for item in items:
        if item.get("sense_key") and not _low_native_label(item):
            return item["sense_key"]
    for item in items:
        if item.get("sense_key"):
            return item["sense_key"]
    return None


def sense_skipped_for_native(item: dict, main_key: str | None) -> bool:
    """Obscure senses (low priority, biological taxonomy, terminology, mere
    forms) are not given a forced Chinese gloss. The main sense always is."""
    if main_key and item.get("sense_key") == main_key:
        return False
    if _low_native_label(item):
        return True
    return bool(_OBSCURE_GLOSS.search(item.get("gloss") or ""))


def native_sense_keys(items: list[dict]) -> set[str]:
    main = main_native_sense_key(items)
    return {i["sense_key"] for i in items
            if i.get("sense_key") and not sense_skipped_for_native(i, main)}


_OUTLAW_WORD = re.compile(r"\boutlaw", re.I)
_ADULTERY_WORD = re.compile(r"adulter|fornicat|extramarital|cuckold", re.I)
_ICELANDIC_WORD = re.compile(r"\bIcelandic\b", re.I)
_IRISH_WORD = re.compile(r"\bIrish\b", re.I)


def repair_outlaw_gloss(english: str | None, chinese: str | None) -> str | None:
    """Qwen rendered the English word outlaw as 通姦者 (問題回報 #254).

    A gloss whose English is actually adultery (adulterer, fornicate) is
    left alone. Replacing 通姦者 before the bare 通姦 keeps 通姦者 from
    becoming 被放逐者. Idempotent.
    """
    if not chinese or not english or not _OUTLAW_WORD.search(english):
        return chinese
    if _ADULTERY_WORD.search(english):
        return chinese
    needs = ("通姦" in chinese or "通奸" in chinese
             or ("Icelandic" in english and "愛爾蘭語" in chinese and "冰島" not in chinese))
    if not needs:
        return chinese
    text = chinese.replace("通姦者", "逃犯").replace("通奸者", "逃犯")
    text = text.replace("通姦", "被放逐").replace("通奸", "被放逐")
    text = text.replace("útlagi（「逃犯、逃亡者」）", "útlagi（「逃犯、被放逐者」）")
    text = text.replace("útlagi（「被放逐、逃亡者」）", "útlagi（「逃犯、被放逐者」）")
    if "Icelandic" in english and "冰島" not in text:
        text = text.replace("愛爾蘭語", "冰島語")
    return text


def repair_icelandic_gloss(english: str | None, chinese: str | None) -> str | None:
    """Repair Icelandic language-name mistranslations (#264, #273).

    Preserve real Irish/Estonian mentions independently. Idempotent.
    """
    if not chinese or not english:
        return chinese
    if not _ICELANDIC_WORD.search(english):
        return chinese
    if not _IRISH_WORD.search(english):
        chinese = chinese.replace("愛爾蘭語", "冰島語")
    if not re.search(r"\bEstonian\b", english, re.I):
        chinese = chinese.replace("愛沙尼亞語", "冰島語")
    return chinese.replace("愛斯蘭尼亞語", "冰島語")


_LANGUAGE_NAME_FIXES = (
    ("舊法國語", "古法語"),
    ("低地德國語", "低地德語"),
    ("德國語", "德語"),
    ("法國語", "法語"),
)


def repair_language_names(chinese: str | None) -> str | None:
    """German/French rendered as 德國語/法國語 (問題回報 #274); the right terms are 德語/法語.

    Neither 德國語 nor 法國語 is ever correct Taiwan usage, so no English check is needed.
    Idempotent.
    """
    if not chinese:
        return chinese
    for wrong, right in _LANGUAGE_NAME_FIXES:
        chinese = chinese.replace(wrong, right)
    return chinese


def repair_learner_gloss(english: str | None, chinese: str | None) -> str | None:
    """Stored-gloss repairs applied on the way into the learner pack."""
    return repair_language_names(
        repair_icelandic_gloss(english, repair_outlaw_gloss(english, chinese)))


def accept_native_gloss(text: str | None, *, short: bool = True) -> str | None:
    """A Taiwan Chinese gloss that is not blank and does not leak Latin.

    Scientific names survive only after mark_scientific_names has wrapped
    them. A short gloss is a word or a short list, not a translated sentence.
    """
    if not text:
        return None
    text = mark_scientific_names(normalize_native_gloss(text))
    text = (clean_native(text) or "").strip(" ，、；; ")
    if not text or not re.search(r"[㐀-鿿]", text):
        return None
    if native_latin_issue(text):
        return None
    if short:
        parts = [p.strip() for p in re.split(r"[、，,；;]", text) if p.strip()]
        if not parts or any(len(p) > 18 for p in parts) or len(text) > 36:
            return None
    return text


def native_latin_issue(text: str | None) -> str | None:
    """None when a zh-TW native meaning has no stray Latin letters outside
    a parenthetical note (a 學名 or similar gloss note travels inside the
    parens already, e.g. 家貓（Felis catus）) and outside the abbreviation
    whitelist above. Otherwise the offending run(s), for qc samples."""
    if not text:
        return None
    bare = _PAREN_NOTE.sub("", text)
    bare = _LATIN_CONTEXT.sub("", bare)
    bad = [r for r in _LATIN_RUN.findall(bare)
           if r.upper() not in LATIN_OK_ABBR and r not in _LATIN_TECH]
    return "、".join(dict.fromkeys(bad)) if bad else None


def clean_native(text: str | None) -> str | None:
    """A native meaning without profane items (問題回報 #116): 「弱者、處於劣勢
    的人、屌絲」 → 「弱者、處於劣勢的人」; None when nothing is left. A meaning
    is a word, not a sentence: the AI's trailing 。 goes (討價還價。, #171)."""
    if text and text.rstrip().endswith("。") and text.rstrip(" 。"):
        text = text.rstrip(" 。")
    if not text or not offensive_native(text):
        return text
    groups = []
    for group in re.split(r"[；;]", text):
        kept = [w for w in group.split("、") if w.strip() and not offensive_native(w)]
        if kept:
            groups.append("、".join(kept))
    return "；".join(groups) or None


# Sense labels that mark the English meaning itself as coarse. A sense with
# one of these may keep a coarse Chinese equivalent (bastard 王八蛋, prick
# 傻屌): the word is kept and shown with a 粗俗 tag instead of being dropped
# or left without Chinese (user decision 2026-10-15, LEXICON_QUALITY_RULES).
COARSE_SENSE_LABELS = {"vulgar", "offensive", "derogatory", "slang"}
VULGAR_SENSE_LABELS = {"vulgar", "offensive"}


def sense_native(text: str | None, labels) -> tuple[str | None, bool]:
    """(native meaning to show, is_vulgar) for a sense with these labels.
    A neutral sense still loses profane items (underdog ??); a sense the
    dictionary labels coarse keeps them and is flagged vulgar."""
    labels = set(labels or [])
    vulgar = bool(labels & VULGAR_SENSE_LABELS)
    if text and offensive_native(text) and labels & COARSE_SENSE_LABELS:
        return text.rstrip(" ?") or None, True
    return clean_native(text), vulgar


def offensive_native(text: str | None) -> bool:
    return bool(text) and any(b in text for b in ZH_OFFENSIVE)

