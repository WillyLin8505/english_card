"""Normalization shared by adapters, the resolver and the exporter."""

from __future__ import annotations

import hashlib
import re
import unicodedata

CJK = re.compile(r"[㐀-鿿豈-﫿]")


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


def looks_simplified(text: str) -> bool:
    """More Simplified-only characters than Traditional-only ones. Uses the
    Taiwan-standard table (plain s2t also rewrites 吃 as 喫)."""
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


def clean_native(text: str | None) -> str | None:
    """A native meaning without profane items (問題回報 #116): 「弱者、處於劣勢
    的人、屌絲」 → 「弱者、處於劣勢的人」; None when nothing is left."""
    if not text or not offensive_native(text):
        return text
    groups = []
    for group in re.split(r"[；;]", text):
        kept = [w for w in group.split("、") if w.strip() and not offensive_native(w)]
        if kept:
            groups.append("、".join(kept))
    return "；".join(groups) or None


def offensive_native(text: str | None) -> bool:
    return bool(text) and any(b in text for b in ZH_OFFENSIVE)

