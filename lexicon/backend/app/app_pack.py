"""The app pack: the exported SQLite projected to one JSON file that the
Flutter app can load on every platform (web builds can't open SQLite
without extra plumbing). Same rows, same stable lexeme ids.

    python lexicon/tools/install_app_pack.py   # copy the latest pack into app/assets/lexicon/
"""

from __future__ import annotations

import json
import math
import shutil
import sqlite3
from pathlib import Path

from . import catalog, config

APP_ASSETS = config.REPO / "app" / "assets" / "lexicon"


def build(db_path: Path) -> dict:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    q = lambda sql, *a: con.execute(sql, a).fetchall()  # noqa: E731
    meta = {r["key"]: r["value"] for r in q("SELECT key, value FROM meta")}
    by_lex: dict[int, dict] = {}
    for r in q("SELECT * FROM lexemes ORDER BY id"):
        by_lex[r["id"]] = {"id": r["id"], "lemma": r["lemma"], "normalized": r["normalized"],
                           "pos": r["pos"], "status": r["status"], "cefr": r["cefr"],
                           "zipf": r["zipf"], "senses": [], "forms": [], "pronunciations": [],
                           "examples": [], "relations": [], "morphemes": [], "missing": {}}
    for r in q("SELECT s.*, t.text AS native, t.is_ai FROM senses s LEFT JOIN sense_translations t"
               " ON t.sense_id = s.id ORDER BY s.lexeme_id, s.ordinal"):
        by_lex[r["lexeme_id"]]["senses"].append({
            "id": r["id"], "definition": r["definition"], "language": r["definition_language"],
            "labels": json.loads(r["labels"] or "[]"), "native": r["native"],
            "native_ai": bool(r["is_ai"])})
    for r in q("SELECT * FROM forms ORDER BY lexeme_id, field"):
        by_lex[r["lexeme_id"]]["forms"].append({"field": r["field"], "form": r["form"],
                                                "normalized": r["normalized"], "label": r["label"]})
    share_forms(by_lex)
    audio = {r["id"]: dict(r) for r in q("SELECT * FROM audio")}
    for r in q("SELECT * FROM pronunciations ORDER BY lexeme_id, ordinal"):
        a = audio.get(r["audio_id"]) if r["audio_id"] else None
        by_lex[r["lexeme_id"]]["pronunciations"].append({
            "kind": r["kind"], "value": r["value"], "accent": r["accent"],
            "default": bool(r["is_default"]), "audio": a["path"] if a else None,
            "license": a["license"] if a else None, "attribution": a["attribution"] if a else None})
    for r in q("SELECT e.*, t.text AS translation, t.is_ai FROM examples e LEFT JOIN"
               " example_translations t ON t.example_id = e.id ORDER BY e.lexeme_id, e.ordinal"):
        by_lex[r["lexeme_id"]]["examples"].append({
            "id": r["id"], "text": r["text"], "translation": r["translation"],
            "translation_ai": bool(r["is_ai"]), "level": r["difficulty"], "sense_id": r["sense_id"],
            "source": r["source"], "license": r["license"]})
    for r in q("SELECT * FROM relations ORDER BY lexeme_id, relation, ordinal"):
        by_lex[r["lexeme_id"]]["relations"].append({
            "relation": r["relation"], "word": r["target_word"], "lexeme_id": r["target_lexeme_id"],
            "pos": r["target_pos"], "native": r["native_meaning"], "native_ai": bool(r["native_is_ai"]),
            "cefr": r["target_cefr"], "zipf": r["target_zipf"], "rarity": r["rarity"],
            "hide_by_default": bool(r["hide_by_default"]),
            "detail": json.loads(r["detail"] or "{}")})
    # Approved sense pictures (schema 4), under the sense they show.
    senses = {sn["id"]: sn for lx in by_lex.values() for sn in lx["senses"]}
    has_images = q("SELECT name FROM sqlite_master WHERE name = 'sense_images'")
    for r in (q("SELECT * FROM sense_images ORDER BY sense_id, ordinal, id") if has_images else []):
        if r["sense_id"] in senses:
            senses[r["sense_id"]].setdefault("images", []).append({
                "path": r["path"], "role": r["role"], "width": r["width"], "height": r["height"],
                "license": r["license"], "author": r["author"], "attribution": r["attribution"],
                "page_url": r["page_url"], "tags": json.loads(r["tags"] or "[]")})
    for r in q("SELECT * FROM morphemes ORDER BY lexeme_id, ordinal"):
        by_lex[r["lexeme_id"]]["morphemes"].append({
            "part": r["part"], "kind": r["kind"], "meaning": r["meaning"], "free": bool(r["free"]),
            "native": r["native_meaning"], "native_ai": bool(r["native_is_ai"])})
    for r in q("SELECT * FROM etymology"):
        by_lex[r["lexeme_id"]]["etymology"] = {
            "root": json.loads(r["root"] or "[]"), "prefix": json.loads(r["prefix"] or "[]"),
            "suffix": json.loads(r["suffix"] or "[]"), "origin_language": r["origin_language"],
            "original_form": r["original_form"], "text": r["text"], "native": r["native_text"]}
    for r in q("SELECT * FROM field_status WHERE status NOT IN"
               " ('complete', 'user_override', 'none', 'not_applicable')"):
        by_lex[r["lexeme_id"]]["missing"][r["field"]] = r["status"]
    pack = {
        "schema_version": int(meta.get("schema_version", 0)),
        "target_language": meta.get("target_language"),
        "native_language": meta.get("native_language"),
        "created_at": meta.get("created_at"),
        "labels": {r["key"]: r["text"] for r in q("SELECT * FROM labels")},
        "redirects": {str(r["old_id"]): r["new_id"] for r in q("SELECT * FROM lexeme_redirects")},
        "lexemes": [lx if lx["status"] == "full" else
                    {k: lx[k] for k in ("id", "lemma", "normalized", "pos", "status")}
                    for lx in by_lex.values()],
    }
    con.close()
    rank_usages(pack["lexemes"])
    # Each spelling's main part of speech first: the app takes a word's first
    # entry when it doesn't know the part of speech (sky 天空, not the verb
    # 「飲用不碰容器」). Stable, so the id order stays within a rank.
    pack["lexemes"].sort(key=lambda lx: lx.get("usage_rank", 0))
    return pack


_POS_ORDER = {"noun": 0, "verb": 1, "adj": 2, "adv": 3}
_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


def share_forms(by_lex: dict[int, dict]) -> None:
    # Each part of speech shows its own forms (問題回報 #85: happy the
    # adjective is not happied/happying, coffee the noun not coffee'd, mug
    # not mugger) — except a participle adjective, which also lists its
    # verb's (grated: grate/grated/grating/grates).
    from .materialize import FORM_POS
    order = {k: i for i, k in enumerate(catalog.FORM_FIELDS)}
    groups: dict[str, list[dict]] = {}
    for lex in by_lex.values():
        groups.setdefault(lex["normalized"], []).append(lex)
    for group in groups.values():
        seen, shared = set(), []
        for lex in group:
            for f in lex["forms"]:
                if (f["field"], f["normalized"]) not in seen:
                    seen.add((f["field"], f["normalized"]))
                    shared.append(f)
        shared.sort(key=lambda f: order.get(f["field"], len(order)))
        word = group[0]["normalized"]
        participle = word.endswith(("ed", "ing")) and any(
            f["field"] == "verb_base" and f["normalized"] != word for f in shared)

        def own(lex, f):
            pos, of = lex["pos"], FORM_POS.get(f["field"])
            if of is None or pos not in ("noun", "verb", "adj", "adv"):
                return True
            return of == pos or (pos == "adj" and participle and of == "verb")

        for lex in group:
            lex["forms"] = [dict(f) for f in shared if own(lex, f)]


def rank_usages(lexemes: list[dict], cefr_by_pos: dict | None = None) -> None:
    """Owner decision 2026-09-30 (問題回報 #16): until the usage layer
    exists, each part of speech of a spelling is its own entry; the main
    ones keep their CEFR, the rare ones are marked ``rare_usage`` with a
    frequency-estimated CEFR (never easier than the main one).

    Which parts of speech are main comes from the CEFR-J / Octanove list
    (breeze: noun A2 only; bowl: noun A1, verb B1), each with the list's
    level for it. A word the list lacks falls back to its senses and
    examples, with the noun and then the adjective first for -ing / -ed
    words (railing is 欄杆, potted is 盆栽的 — not the verb forms).

    The headword's zipf is shared by all its parts of speech, so a rare
    usage's share of the senses + examples scales it down (log10 share)."""
    from .adapters.base import frequency_profile

    if cefr_by_pos is None:
        try:
            from .adapters.local import cefr_list
            cefr_by_pos = {w: v[1] for w, v in cefr_list().items()}
        except Exception:  # noqa: BLE001 — no list: senses and examples only
            cefr_by_pos = {}
    listed_pos = {"adj.": "adj", "adv.": "adv"}
    groups: dict[str, list[dict]] = {}
    for lx in lexemes:
        if lx.get("status") == "full":
            groups.setdefault(lx["normalized"], []).append(lx)
    for word, group in groups.items():
        listed = {listed_pos.get(p, p): lv for p, lv in (cefr_by_pos.get(word) or {}).items()}
        evidence = {id(lx): 1 + len(lx.get("senses") or []) + len(lx.get("examples") or [])
                    for lx in group}
        participle = not listed and word.endswith(("ing", "ed"))

        def key(lx):
            lv = listed.get(lx["pos"])
            return (0 if lv else 1,
                    _LEVELS.index(lv) if lv in _LEVELS else 9,
                    # -ing / -ed words not in the list: the noun, then the
                    # adjective (potted 盆栽的), before the verb form.
                    {"noun": 0, "adj": 1}.get(lx["pos"], 2) if participle else 0,
                    -evidence[id(lx)], _POS_ORDER.get(lx["pos"], 9), lx["id"])

        group.sort(key=key)
        total = sum(evidence.values())
        main = group[0]
        for rank, lx in enumerate(group):
            lx["usage_rank"] = rank
            lv = listed.get(lx["pos"])
            if rank == 0 or lv:
                lx["rare_usage"] = False
                if lv and lv != lx.get("cefr"):
                    lx["headword_cefr"], lx["cefr"], lx["cefr_source"] = lx.get("cefr"), lv, "cefr-j"
                continue
            lx["rare_usage"] = True
            lx["headword_cefr"] = lx.get("cefr")
            if lx.get("zipf") is None:
                continue
            share = evidence[id(lx)] / total
            estimate = frequency_profile(lx["zipf"] + math.log10(share))["cefr"]
            floor = main.get("cefr") or lx.get("cefr")
            if floor in _LEVELS and _LEVELS.index(estimate) < _LEVELS.index(floor):
                estimate = floor
            lx["cefr"], lx["cefr_source"] = estimate, "frequency_estimate"


def install(release_dir: Path, target: str, native: str, app_assets: Path = APP_ASSETS) -> dict:
    """Copy a release's app pack, manifest and audio into the Flutter app's
    assets (app/assets/lexicon/{target}-{native}.json …)."""
    base = release_dir.name
    pack = release_dir / f"{base}.json"
    if not pack.exists():
        raise FileNotFoundError(f"{pack.name} 不存在（請重新匯出）")
    app_assets.mkdir(parents=True, exist_ok=True)
    name = f"{target}-{native}"
    tmp = app_assets / f".{name}.json.part"
    shutil.copyfile(pack, tmp)
    tmp.replace(app_assets / f"{name}.json")
    shutil.copyfile(release_dir / "manifest.json", app_assets / f"{name}.manifest.json")
    copied = 0
    media = release_dir / "media" / "audio" / target
    if media.exists():
        dest = app_assets / "media" / "audio" / target
        dest.mkdir(parents=True, exist_ok=True)
        for f in media.iterdir():
            if f.is_file() and not (dest / f.name).exists():
                shutil.copyfile(f, dest / f.name)
                copied += 1
    pictures = release_dir / "media" / "images"
    if pictures.exists():
        for f in pictures.rglob("*"):
            dest = app_assets / "media" / f.relative_to(release_dir / "media")
            if f.is_file() and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dest)
                copied += 1
    return {"pack": str(app_assets / f"{name}.json"), "release": base, "media_copied": copied}
