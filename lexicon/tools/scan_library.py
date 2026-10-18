"""Read-only whole-library root-cause scan (card #161).

Standing cards #168–#171 call this. It builds the same live pack as
``qc.py`` (``serve_app.live_pack``) and writes counts plus up to 30
samples per check. It does not write the database or call a model.

    python lexicon/tools/scan_library.py
    python lexicon/tools/scan_library.py --only A,D
    python lexicon/tools/scan_library.py --pack fixture.json --out some/dir
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
sys.path.insert(0, str(ROOT))

from app import qc as pack_qc  # noqa: E402
from app.text import native_latin_issue  # noqa: E402

OUT = ROOT / "lexicon" / "exports" / "quality" / "scan"
SAMPLE_MAX = 30
TAIPEI = ZoneInfo("Asia/Taipei")
LEVEL = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
LISTED_SOURCES = ("cefr-j", "cefrj", "octanove")
# Same exclusion the #160 scope scan used (includes quality_rule).
ESTIMATE_EXCLUDED = ("cefr-j", "cefrj", "octanove", "list")
LEVELED_INFLECTION_SOURCES = ("frequency_estimate", "quality_rule", "cefr-j")
RARE_MAIN = {"archaic", "obsolete", "rare", "dated", "historical", "dialectal", "uncommon"}
RARE_FIRST = {"archaic", "obsolete", "rare", "dated", "historical"}
RARE_PRIORITY = RARE_MAIN | {"slang", "vulgar", "derogatory", "offensive"}
GENERIC = (
    "surface", "edge", "handle", "pattern", "structure", "vertical", "center",
    "object", "area", "part", "side", "background", "photograph", "image",
    "portrait", "depict", "display", "close-up", "picture", "scene", "view",
    "item", "thing", "shape", "texture", "color", "colour", "foreground",
)
SYNONYM_PAIRS = (
    ("stone", "rock"), ("bowl", "container"), ("light", "illuminated"),
    ("cup", "mug"), ("road", "street"), ("picture", "image"), ("photo", "photograph"),
)
ODD_NAMES = re.compile(r"\b(Ziri|Mennad|Baya|Skura|Yanni|Rima|Taninna|Layla|Sami)\b")
SENTENCE_END = re.compile(r"[.!?\"\u201d]\s*$")
LATIN_RUN = re.compile(r"[A-Za-z]{2,}")
VULGAR = re.compile(
    r"\b(fuck\w*|shit\w*|bitch\w*|cunt|dick|asshole|bastard|crap|whore|slut|nigger|faggot|retard\w*)\b",
    re.I,
)
# Card #160 scope scan: broad "form of" (identity) vs narrow (still leveled).
_INF_HEAD = (
    r"^(?:\(.*?\)\s*)?(simple past|past participle|present participle|plural|"
    r"third-person|comparative|superlative|gerund|inflection"
)
INF_NARROW = re.compile(_INF_HEAD + r")\b.*\bof\b", re.I)
INF_BROAD = re.compile(
    _INF_HEAD + r"|alternative form|alternative spelling|obsolete form|archaic form|"
    r"misspelling|nonstandard form|eye dialect|abbreviation|initialism)\b.*\bof\b",
    re.I,
)
GROUPS = {
    "A": "屈折形／衍生詞身分與等級",
    "B": "CEFR 估算離群",
    "C": "主用法／主義項與照片義項",
    "D": "中文意思",
    "E": "例句",
    "F": "照片標籤品質",
    "G": "代表圖相關性",
    "H": "發音",
}


def _check(n: int, samples: list | None = None) -> dict:
    picked: list[str] = []
    seen: set[str] = set()
    for item in samples or []:
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        picked.append(text)
        if len(picked) >= SAMPLE_MAX:
            break
    return {"n": int(n), "samples": picked}


def _labels(sense: dict) -> set[str]:
    return {str(x).lower() for x in (sense.get("labels") or [])}


def _example_text(example: dict) -> str:
    return example.get("text") or example.get("sentence") or example.get("en") or ""


def _tag_words(tags) -> set[str]:
    words = set()
    for tag in tags or []:
        if isinstance(tag, str):
            words.add(tag.lower())
        elif isinstance(tag, dict) and tag.get("word"):
            words.add(str(tag["word"]).lower())
    return words


def _bases(word: str) -> set[str]:
    found = set()
    for suf, rep in (
        ("ed", ""), ("ed", "e"), ("d", ""), ("ing", ""), ("ing", "e"),
        ("s", ""), ("es", ""), ("ies", "y"), ("y", ""), ("er", ""),
        ("ly", ""), ("ness", ""), ("ful", ""), ("less", ""),
    ):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            base = word[:-len(suf)] + rep
            found.add(base)
            if len(base) > 3 and base[-1] == base[-2]:
                found.add(base[:-1])
    return found


def _all_form_of(lexeme: dict, pattern: re.Pattern) -> bool:
    senses = lexeme.get("senses") or []
    return bool(senses) and all(pattern.match(s.get("definition") or "") for s in senses)


def _any_form_of(lexeme: dict, pattern: re.Pattern) -> bool:
    return any(pattern.match(s.get("definition") or "") for s in (lexeme.get("senses") or []))


def scan_pack(pack: dict) -> dict:
    """Group a pack. Pure function: no database and no files."""
    lexemes = pack.get("lexemes") or []
    full = [lx for lx in lexemes if lx.get("status") == "full"]
    images = pack.get("catalog_images") or []
    by_id = {lx.get("id"): lx for lx in lexemes}
    tagged: Counter = Counter()
    for image in images:
        for tag in image.get("tags") or []:
            if tag.get("lexeme_id") is not None:
                tagged[tag["lexeme_id"]] += 1

    narrow_only = [lx for lx in full if _all_form_of(lx, INF_NARROW)]
    broad_only = [lx for lx in full if _all_form_of(lx, INF_BROAD)]
    broad_ids = {id(lx) for lx in broad_only}
    leveled = [
        lx for lx in narrow_only
        if lx.get("cefr") and lx.get("cefr_source") in LEVELED_INFLECTION_SOURCES
    ]
    mixed = [lx for lx in full if _any_form_of(lx, INF_BROAD) and id(lx) not in broad_ids]

    estimated = [
        lx for lx in full
        if lx.get("cefr") and lx.get("cefr_source") not in ESTIMATE_EXCLUDED
    ]
    listed: dict[str, list[int]] = {}
    for lx in full:
        if lx.get("cefr") in LEVEL and lx.get("cefr_source") in LISTED_SOURCES:
            listed.setdefault(lx.get("normalized") or "", []).append(LEVEL[lx["cefr"]])
    family = []
    for lx in estimated:
        if lx.get("cefr") not in LEVEL:
            continue
        for base in _bases(lx.get("normalized") or ""):
            if base in listed and LEVEL[lx["cefr"]] - min(listed[base]) >= 2:
                family.append(f"{lx.get('lemma')}({lx.get('cefr')}) base {base}")
                break
    est_photo = [lx for lx in estimated if lx.get("cefr") in ("C1", "C2") and tagged[lx.get("id")]]
    est_photo_noun = [lx for lx in est_photo if lx.get("pos") == "noun"]

    by_norm: dict[str, list] = defaultdict(list)
    for lx in full:
        by_norm[lx.get("normalized") or ""].append(lx)
    odd_main = []
    for word, group in by_norm.items():
        if len(group) < 2:
            continue
        mains = [lx for lx in group if lx.get("usage_rank") == 0]
        if not mains:
            continue
        main = mains[0]
        labs = [_labels(s) for s in (main.get("senses") or [])]
        if labs and all(lb & RARE_MAIN for lb in labs):
            odd_main.append(f"{word}:{main.get('pos')}")
    first_rare = [
        lx for lx in full
        if (lx.get("senses") or []) and _labels(lx["senses"][0]) & RARE_FIRST
    ]
    main_priority_rare = [
        lx for lx in full for sense in (lx.get("senses") or [])
        if sense.get("priority") == "main" and _labels(sense) & RARE_PRIORITY
    ]
    nonmain_photo_senses = [
        (lx, sense) for lx in full for sense in (lx.get("senses") or [])
        if sense.get("images") and sense.get("priority") != "main"
    ]
    nonmain_photo_images = sum(len(sense.get("images") or []) for _, sense in nonmain_photo_senses)
    low_photo_images = sum(
        len(sense.get("images") or []) for _, sense in nonmain_photo_senses
        if sense.get("priority") == "low"
    )
    fallback = sum(
        1 for image in images for tag in (image.get("tags") or []) if tag.get("sense_fallback")
    )
    violations = pack_qc.validate(pack)

    empty_senses = [
        f"{lx.get('lemma')}:{index}"
        for lx in full for index, sense in enumerate(lx.get("senses") or [])
        if not (sense.get("native") or "").strip()
    ]
    main_empty = [
        lx.get("lemma") for lx in full
        if (lx.get("senses") or []) and not (lx["senses"][0].get("native") or "").strip()
    ]
    latin_raw = [
        f"{lx.get('lemma')}:{sense.get('native')}"
        for lx in full for sense in (lx.get("senses") or [])
        if sense.get("native") and LATIN_RUN.search(sense.get("native") or "")
    ]
    latin_qc = [
        f"{lx.get('lemma')}:{issue}"
        for lx in full for sense in (lx.get("senses") or [])
        if (issue := native_latin_issue(sense.get("native")))
    ]
    main_ai = [
        lx.get("lemma") for lx in full
        if (lx.get("senses") or []) and lx["senses"][0].get("native_ai")
    ]
    photo_no_zh = []
    photo_low = []
    for image in images:
        for tag in image.get("tags") or []:
            lid = tag.get("lexeme_id")
            lx = by_id.get(lid)
            if not lx or lx.get("status") != "full":
                continue
            sense = next(
                (s for s in (lx.get("senses") or []) if s.get("id") == tag.get("sense_id")),
                None,
            )
            if sense is None:
                continue
            if not (sense.get("native") or "").strip():
                photo_no_zh.append(f"{image.get('id')}:{lx.get('lemma')}")
            elif sense.get("priority") == "low":
                photo_low.append(f"{image.get('id')}:{lx.get('lemma')}")

    examples = [(lx, ex) for lx in full for ex in (lx.get("examples") or [])]
    not_sentence = [lx.get("lemma") for lx, ex in examples
                    if _example_text(ex) and not SENTENCE_END.search(_example_text(ex).strip())]
    odd_name = [lx.get("lemma") for lx, ex in examples if ODD_NAMES.search(_example_text(ex))]
    missing_lemma = []
    for lx, ex in examples:
        text = _example_text(ex).lower()
        forms = {lx.get("normalized") or ""} | {
            f.get("normalized") for f in (lx.get("forms") or []) if f.get("normalized")
        }
        forms.discard("")
        if text and not any(re.search(r"\b" + re.escape(form) + r"\b", text) for form in forms):
            missing_lemma.append(lx.get("lemma"))
    no_examples = [lx.get("lemma") for lx in full if not lx.get("examples")]
    vulgar_examples = [
        f"{lx.get('lemma')}:{_example_text(ex)[:50]}"
        for lx, ex in examples if VULGAR.search(_example_text(ex))
    ]
    vulgar_relations = []
    for lx in full:
        rel = lx.get("relations") or []
        rows = rel if isinstance(rel, list) else []
        if isinstance(rel, dict):
            rows = [item for values in rel.values() for item in (values or [])]
        for row in rows:
            word = row.get("word") if isinstance(row, dict) else str(row)
            if word and VULGAR.fullmatch(word.strip()):
                vulgar_relations.append(f"{lx.get('lemma')}->{word.strip()}")

    per_image = []
    level_counts = []
    tag_uses: Counter = Counter()
    for image in images:
        labels = image.get("labels") or []
        per_image.append(len(labels))
        level_counts.append(len({x.get("cefr") for x in labels if x.get("cefr")}))
        for label in labels:
            if label.get("word"):
                tag_uses[str(label["word"]).lower()] += 1
    synonym_hits = 0
    for image in images:
        words = {str(x.get("word") or "").lower() for x in (image.get("labels") or [])}
        synonym_hits += sum(1 for a, b in SYNONYM_PAIRS if a in words and b in words)
    generic_hits = [(word, tag_uses[word]) for word in GENERIC if tag_uses[word]]

    heavy = []
    for lx in full:
        count = sum(len(sense.get("images") or []) for sense in (lx.get("senses") or []))
        if count >= 15:
            heavy.append((count, lx.get("lemma"), lx.get("pos")))
    heavy.sort(reverse=True)
    rep_missing = []
    for lx in full:
        for sense in lx.get("senses") or []:
            for image in sense.get("images") or []:
                if image.get("role") == "representative" and image.get("tags"):
                    words = _tag_words(image.get("tags"))
                    lemma = (lx.get("lemma") or "").lower()
                    normalized = (lx.get("normalized") or "").lower()
                    if normalized not in words and lemma not in words:
                        rep_missing.append(lx.get("lemma"))

    without_ipa = []
    without_audio_kind = []
    without_audio_path = []
    arpabet = []
    for lx in full:
        prons = lx.get("pronunciations") or []
        ipa_values = [p.get("value") for p in prons if p.get("kind") == "ipa" and p.get("value")]
        if not ipa_values:
            without_ipa.append(lx.get("lemma"))
        elif any(pack_qc._is_arpabet(val) for val in ipa_values):
            arpabet.append(lx.get("lemma"))
        if not any(p.get("kind") == "audio" for p in prons):
            without_audio_kind.append(lx.get("lemma"))
        if not any((p.get("audio") or p.get("audio_url") or p.get("path")) for p in prons):
            without_audio_path.append(lx.get("lemma"))

    def show(rows, fmt):
        return [fmt(row) for row in rows]

    groups = {
        "A": {"title": GROUPS["A"], "checks": {
            "inflection_only_leveled": _check(len(leveled), show(
                leveled, lambda lx: f"{lx.get('lemma')}({lx.get('pos')},{lx.get('cefr')},{lx.get('cefr_source')})")),
            "inflection_only_leveled_on_photos": _check(
                sum(1 for lx in leveled if tagged[lx.get("id")]),
                [lx.get("lemma") for lx in leveled if tagged[lx.get("id")]]),
            "mixed_formof_plus_real_senses": _check(len(mixed), [lx.get("lemma") for lx in mixed]),
            "inflection_only_full": _check(len(broad_only), [
                f"{lx.get('lemma')}({lx.get('pos')},{lx.get('cefr')},{lx.get('cefr_source')})"
                for lx in broad_only]),
            "inflection_only_full_on_photos": _check(
                sum(1 for lx in broad_only if tagged[lx.get("id")]),
                [lx.get("lemma") for lx in broad_only if tagged[lx.get("id")]]),
        }},
        "B": {"title": GROUPS["B"], "checks": {
            "full_cefr_estimated": _check(len(estimated)),
            "est_C1C2_on_photos": _check(len(est_photo), show(
                est_photo, lambda lx: f"{lx.get('lemma')}({lx.get('pos')},{lx.get('cefr')})")),
            "est_C1C2_nouns_on_photos": _check(len(est_photo_noun), [lx.get("lemma") for lx in est_photo_noun]),
            "estimate_2plus_above_listed_base": _check(len(family), family),
        }},
        "C": {"title": GROUPS["C"], "checks": {
            "main_usage_all_senses_archaic_rare": _check(len(odd_main), odd_main),
            "first_sense_archaic_rare": _check(len(first_rare), [lx.get("lemma") for lx in first_rare]),
            "main_priority_sense_rare_label": _check(len(main_priority_rare), [
                lx.get("lemma") for lx in main_priority_rare]),
            "photo_senses_nonmain_with_images": _check(len(nonmain_photo_senses), [
                f"{lx.get('lemma')}:{sense.get('priority')}" for lx, sense in nonmain_photo_senses]),
            "photo_image_rows_on_nonmain": _check(nonmain_photo_images),
            "photo_image_rows_on_low": _check(low_photo_images),
            "tags_sense_fallback": _check(fallback),
            "photo_tag_sense_low_priority": _check(
                len(photo_low), photo_low,
            ),
            "qc_photo_tag_sense_low_priority": _check(len(violations.get("photo_tag.sense_low_priority") or [])),
        }},
        "D": {"title": GROUPS["D"], "checks": {
            "main_sense_empty": _check(len(main_empty), main_empty),
            "senses_native_empty": _check(len(empty_senses), empty_senses),
            "native_has_latin_letters": _check(len(latin_raw), latin_raw),
            "native_latin_issue": _check(len(latin_qc), latin_qc),
            "main_sense_ai": _check(len(main_ai)),
            "photo_tag_sense_without_chinese": _check(len(photo_no_zh), photo_no_zh),
            "qc_main_without_chinese": _check(len(violations.get("sense.main_without_chinese") or [])),
            "qc_main_is_ai": _check(len(violations.get("sense.main_is_ai") or [])),
            "qc_native_empty": _check(len(violations.get("sense.native_empty") or [])),
            "qc_native_has_latin": _check(len(violations.get("sense.native_has_latin") or [])),
            "qc_photo_tag_sense_without_chinese": _check(
                len(violations.get("photo_tag.sense_without_chinese") or [])),
        }},
        "E": {"title": GROUPS["E"], "checks": {
            "examples_not_sentence": _check(len(not_sentence), not_sentence),
            "examples_odd_tatoeba_names": _check(len(odd_name), sorted(set(odd_name))),
            "examples_missing_lemma": _check(len(missing_lemma), sorted(set(missing_lemma))),
            "full_without_examples": _check(len(no_examples), no_examples),
            "examples_profanity": _check(len(vulgar_examples), vulgar_examples),
            "relations_profanity": _check(len(vulgar_relations), vulgar_relations),
        }},
        "F": {"title": GROUPS["F"], "checks": {
            "catalog_images": _check(len(images)),
            "images_lt3_labels": _check(sum(1 for n in per_image if n < 3)),
            "images_le2_levels": _check(sum(1 for n in level_counts if n <= 2)),
            "generic_tag_uses": _check(sum(tag_uses[word] for word in GENERIC), [
                f"{word}:{count}" for word, count in generic_hits]),
            "images_synonym_pairs": _check(synonym_hits),
        }},
        "G": {"title": GROUPS["G"], "checks": {
            "lexemes_ge15_images": _check(len(heavy), [f"{lemma}({pos}):{count}" for count, lemma, pos in heavy]),
            "adj_ge15_images": _check(
                sum(1 for _, _, pos in heavy if pos in ("adj", "adjective")),
                [f"{lemma}:{count}" for count, lemma, pos in heavy if pos in ("adj", "adjective")]),
            "representative_missing_word": _check(len(rep_missing), sorted(set(rep_missing))),
        }},
        "H": {"title": GROUPS["H"], "checks": {
            "full_without_ipa": _check(len(without_ipa), without_ipa),
            "ipa_is_arpabet": _check(len(arpabet), arpabet),
            "full_without_audio_kind": _check(len(without_audio_kind)),
            "full_without_audio_path": _check(len(without_audio_path)),
            "qc_full_without_ipa": _check(len(violations.get("entry.full_without_ipa") or [])),
            "qc_full_without_audio": _check(len(violations.get("entry.full_without_audio") or [])),
            "qc_ipa_is_arpabet": _check(len(violations.get("pronunciation.ipa_is_arpabet") or [])),
        }},
    }
    return {
        "groups": groups,
        "pack": {
            "lexemes": len(lexemes),
            "full": len(full),
            "catalog_images": len(images),
            "cefr_source": dict(Counter(lx.get("cefr_source") for lx in full)),
        },
    }


def select_groups(report: dict, only: list[str] | None) -> dict:
    if not only:
        return report
    wanted = [name.strip().upper() for name in only if name.strip()]
    unknown = [name for name in wanted if name not in GROUPS]
    if unknown:
        raise SystemExit(f"unknown group(s): {', '.join(unknown)}; choose from {', '.join(GROUPS)}")
    return {
        **report,
        "groups": {name: report["groups"][name] for name in wanted},
    }


def delta_against(report: dict, previous: dict | None) -> dict:
    out = {}
    prev_groups = (previous or {}).get("groups") or {}
    for name, body in report.get("groups", {}).items():
        prev_checks = (prev_groups.get(name) or {}).get("checks") or {}
        for check, row in body.get("checks", {}).items():
            prev_n = (prev_checks.get(check) or {}).get("n")
            out[f"{name}.{check}"] = {
                "n": row["n"],
                "prev": prev_n,
                "diff": None if prev_n is None else row["n"] - prev_n,
            }
    return out


def build_pack() -> dict:
    """Same in-process pack as ``qc.py`` ``build_pack``. Read-only transaction."""
    import serve_app
    serve_app._cache.clear()
    body, _etag = serve_app.live_pack("en", "zh-TW")
    return json.loads(body)


def _load_previous(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_report(report: dict, out_dir: Path, update_latest: bool) -> tuple[Path, Path | None]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TAIPEI).strftime("%Y%m%d-%H%M%S")
    stamped = out_dir / f"scan-{stamp}.json"
    text = json.dumps(report, ensure_ascii=False, indent=1)
    stamped.write_text(text, encoding="utf-8")
    latest = None
    if update_latest:
        latest = out_dir / "latest.json"
        latest.write_text(text, encoding="utf-8")
    return stamped, latest


def _summary(report: dict) -> str:
    lines = [
        f"full={report.get('pack', {}).get('full')} images={report.get('pack', {}).get('catalog_images')} "
        f"seconds={report.get('seconds')}",
    ]
    for name, body in report.get("groups", {}).items():
        parts = [f"{check}={row['n']}" for check, row in body.get("checks", {}).items()]
        lines.append(f"{name} " + " ".join(parts))
    changed = [
        f"{key} {row['prev']}->{row['n']} ({row['diff']:+d})"
        for key, row in (report.get("delta") or {}).items()
        if row.get("diff") not in (None, 0)
    ]
    if changed:
        lines.append("delta " + "; ".join(changed[:40]))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan_library",
        description="Read-only whole-library root-cause scan for standing cards #168–#171.",
    )
    parser.add_argument("--only", help="comma-separated groups to keep in the report (A–H)")
    parser.add_argument("--pack", help="read this pack JSON instead of building the live pack")
    parser.add_argument("--out", help="output directory (default: lexicon/exports/quality/scan)")
    parser.add_argument("--no-write", action="store_true", help="print the summary only")
    args = parser.parse_args(argv)
    only = args.only.split(",") if args.only else None
    started = time.time()
    if args.pack:
        pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    else:
        pack = build_pack()
    report = select_groups(scan_pack(pack), only)
    out_dir = Path(args.out) if args.out else OUT
    previous = _load_previous(out_dir / "latest.json") if not args.no_write else None
    report["delta"] = delta_against(report, previous)
    report["generated_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    report["seconds"] = round(time.time() - started, 1)
    report["read_only"] = True
    if not args.no_write:
        stamped, latest = write_report(report, out_dir, update_latest=only is None)
        report["paths"] = {"stamped": str(stamped), "latest": str(latest) if latest else None}
    print(_summary(report))
    if report.get("paths"):
        print(f"wrote {report['paths']['stamped']}")
        if report["paths"]["latest"]:
            print(f"wrote {report['paths']['latest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
