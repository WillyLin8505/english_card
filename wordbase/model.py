"""The WordEntry view: spec-01 section 5's fields, filled from section 6's
sources in their priority order.

Section 6: ① 首選優先使用 ② 次選替代或補足 ③ 補充延伸資料 — so a list field
takes the first-choice source's items first, then tops up from the second,
then extends from the third, removing duplicates. Every item keeps the
source it came from (section 5: 來源以欄位為單位保存), and a learner's edit
replaces the field while the fetched value stays as its original.
"""

from __future__ import annotations

from dataclasses import dataclass

from sources import SOURCES


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    group: str
    sources: tuple[tuple[str, str], ...]  # (source, source field) in priority order
    limit: int = 20
    # How items are compared for duplicates.
    kind: str = "text"


GROUPS = ["識別", "釋義", "發音", "詞彙關係", "構詞", "例句"]

FIELDS = [
    Field("pos", "詞性", "識別", (("kaikki", "pos"), ("oewn", "pos")), 8),
    Field("senses", "英文定義與義項", "釋義", (("kaikki", "senses"), ("oewn", "senses")), 12, "sense"),
    Field("meaning_zh", "中文釋義", "釋義", (("kaikki", "meaning_zh"),), 10, "zh"),
    Field("ipa", "IPA 與口音", "發音", (("kaikki", "ipa"), ("cmudict", "ipa")), 8, "ipa"),
    Field("phonemes", "音素（ARPABET）", "發音", (("cmudict", "phonemes"),), 2),
    Field("audio", "單字真人發音", "發音", (("kaikki", "audio"),), 6, "audio"),
    Field("synonyms", "近義字／意思相近", "詞彙關係",
          (("oewn", "synonyms"), ("kaikki", "synonyms"), ("datamuse", "synonyms"),
           ("datamuse", "means_like")), 20),
    Field("homophones", "同音字／發音相近", "詞彙關係",
          (("cmudict", "homophones"), ("datamuse", "homophones"), ("kaikki", "homophones")), 15,
          "word"),
    Field("similar_spelling", "拼字相近", "詞彙關係",
          (("wordlist", "similar_spelling"), ("datamuse", "similar_spelling")), 15),
    Field("forms", "詞形變化", "詞彙關係", (("kaikki", "forms"),), 12, "form"),
    Field("derivations", "詞性衍生", "詞彙關係", (("kaikki", "derivations"), ("oewn", "derivations")),
          20),
    Field("morphology", "字根、字首、字尾", "構詞", (("kaikki", "morphology"),), 4, "morph"),
    Field("etymology", "詞源", "構詞", (("kaikki", "etymology"),), 2),
    Field("examples", "例句與翻譯", "例句",
          (("tatoeba", "examples"), ("kaikki", "examples"), ("oewn", "examples")), 10, "example"),
]
FIELD_BY_KEY = {f.key: f for f in FIELDS}


def _key(field: Field, item) -> str:
    if isinstance(item, str):
        return item.strip().lower()
    return {
        "sense": lambda i: (i.get("pos", "") + "|" + i.get("gloss", "")).lower(),
        "zh": lambda i: i.get("trad", "") + i.get("pos", ""),
        "ipa": lambda i: i.get("ipa", "").replace("ɹ", "r"),
        "audio": lambda i: i.get("url", ""),
        "word": lambda i: i.get("word", "").lower(),
        "form": lambda i: i.get("form", "") + i.get("pos", ""),
        "morph": lambda i: "+".join(i.get("parts", [])),
        "example": lambda i: " ".join(i.get("text", "").lower().split()),
    }.get(field.kind, lambda i: str(i))(item)


def sense_key(value) -> str:
    return _key(FIELD_BY_KEY["senses"], value) if isinstance(value, dict) else str(value).lower()


def merge_field(field: Field, results: dict) -> dict:
    """Items from the field's sources in priority order, duplicates removed.
    results = {source: {"data": {...}}}."""
    items, seen, used = [], set(), []
    ranks = {s: i for i, s in enumerate(dict.fromkeys(s for s, _ in field.sources), 1)}
    for source, src_field in field.sources:
        rank = ranks[source]
        found = ((results.get(source) or {}).get("data") or {}).get(src_field) or []
        added = 0
        for it in found:
            k = _key(field, it)
            if not k or k in seen or len(items) >= field.limit:
                continue
            seen.add(k)
            items.append({"value": it, "source": source, "rank": rank})
            added += 1
        if found:
            used.append({"source": source, "rank": rank, "found": len(found), "used": added})
    return {"items": items, "sources": used}


def _prefer_accent(items: list, accent: str | None) -> list:
    if not accent:
        return items
    def score(i):
        tags = i["value"].get("accent", []) if isinstance(i["value"], dict) else []
        text = " ".join(tags).lower()
        return 0 if accent.lower() in text or (accent == "US" and "american" in text) \
            or (accent == "UK" and ("received" in text or "british" in text)) else 1
    return sorted(items, key=score)


def build_view(entry: dict, results: dict, overrides: dict, verified: dict) -> dict:
    """The merged WordEntry: every field with its items, the sources that
    supplied them, licences, fetch time, and whether the learner edited or
    checked it."""
    fields = {}
    for f in FIELDS:
        merged = merge_field(f, results)
        if f.key in ("ipa", "audio"):
            merged["items"] = _prefer_accent(merged["items"], entry.get("default_accent"))
        info = {
            "label": f.label,
            "group": f.group,
            "items": merged["items"],
            "sources": [{**u, "name": SOURCES[u["source"]]["name"],
                         "license": SOURCES[u["source"]]["license"],
                         "fetched_at": (results.get(u["source"]) or {}).get("fetched_at")}
                        for u in merged["sources"]],
            "priority": [{"source": s, "rank": i, "name": SOURCES[s]["name"]}
                         for i, s in enumerate(dict.fromkeys(s for s, _ in f.sources), 1)],
            "trust": "source" if merged["items"] else None,
            "verified_at": verified.get(f.key),
        }
        if f.key in overrides:
            o = overrides[f.key]
            info["original"] = info["items"]
            info["items"] = [{"value": v, "source": "user", "rank": 0} for v in o["value"]]
            info["trust"] = "user"
            info["edited_at"] = o["edited_at"]
        # 使用者可指定主要義項: the chosen sense (by its key) goes first.
        if f.key == "senses" and entry.get("primary_sense"):
            p = next((i for i, it in enumerate(info["items"])
                      if sense_key(it["value"]) == entry["primary_sense"]), None)
            if p is not None:
                info["items"].insert(0, info["items"].pop(p))
                info["items"][0]["primary"] = True
        fields[f.key] = info
    return {"fields": fields}


def summarize(entry: dict, view: dict) -> dict:
    """What the word list shows and filters on."""
    f = view["fields"]
    items = lambda k: [i["value"] for i in f[k]["items"]]  # noqa: E731
    examples = items("examples")
    zh_examples = [e for e in examples if isinstance(e, dict)
                   and (e.get("translation_tw") or e.get("script") == "Hant")]
    sense = next(iter(items("senses")), None)
    zh = next(iter(items("meaning_zh")), None)
    ipa = next(iter(items("ipa")), None)
    return {
        "pos": items("pos")[:3],
        "gloss": sense.get("gloss") if isinstance(sense, dict) else sense,
        "zh": (zh.get("trad") if isinstance(zh, dict) else zh) or "",
        "ipa": ipa.get("ipa") if isinstance(ipa, dict) else ipa,
        "has": {
            "senses": bool(items("senses")),
            "meaning_zh": bool(items("meaning_zh")),
            "ipa": bool(items("ipa")),
            "audio": bool(items("audio")),
            "examples5": len(examples) >= 5,
            "examples_zh": bool(zh_examples),
            "synonyms": bool(items("synonyms")),
            "forms": bool(items("forms")),
            "morphology": bool(items("morphology")),
        },
        "counts": {"examples": len(examples), "examples_zh": len(zh_examples),
                   "audio": len(items("audio"))},
        "edited": sorted(k for k, v in f.items() if v["trust"] == "user"),
    }


# Missing-field filters for the list (缺漏欄位).
MISSING = {
    "meaning_zh": "缺中文釋義",
    "ipa": "缺音標",
    "audio": "缺真人發音",
    "examples5": "例句不足 5 句",
    "examples_zh": "缺繁中翻譯例句",
    "synonyms": "缺近義字",
    "forms": "缺詞形變化",
    "morphology": "缺字根字尾",
}
