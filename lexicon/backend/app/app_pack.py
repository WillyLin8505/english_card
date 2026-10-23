"""The app pack: the exported SQLite projected to one JSON file that the
Flutter app can load on every platform (web builds can't open SQLite
without extra plumbing). Same rows, same stable lexeme ids.

    python lexicon/tools/install_app_pack.py   # media into app/assets/lexicon/, then the slim bundle
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
import math
import shutil
import sqlite3
from pathlib import Path

from . import catalog, config
from .text import entry_type_of

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
                           "zipf": r["zipf"], "entry_type": entry_type_of(r["normalized"]),
                           "senses": [], "forms": [], "pronunciations": [],
                           "examples": [], "relations": [], "morphemes": [], "missing": {}}
    for r in q("SELECT s.*, t.text AS native, t.is_ai FROM senses s LEFT JOIN sense_translations t"
               " ON t.sense_id = s.id ORDER BY s.lexeme_id, s.ordinal"):
        by_lex[r["lexeme_id"]]["senses"].append({
            "id": r["id"], "ordinal": r["ordinal"], "definition": r["definition"],
            "language": r["definition_language"],
            "labels": json.loads(r["labels"] or "[]"), "native": r["native"],
            "register": r["register"], "native_ai": bool(r["is_ai"])})
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
            "license": a["license"] if a else None, "attribution": a["attribution"] if a else None,
            # 問題回報 #688: the App shows who recorded it and where from (#657).
            "speaker": a.get("speaker") if a else None,
            "source_page": a.get("source_page") if a else None})
    for r in q("SELECT e.*, t.text AS translation, t.is_ai FROM examples e LEFT JOIN"
               " example_translations t ON t.example_id = e.id ORDER BY e.lexeme_id, e.ordinal"):
        by_lex[r["lexeme_id"]]["examples"].append({
            "id": r["id"], "text": r["text"], "translation": r["translation"],
            "translation_ai": bool(r["is_ai"]), "level": r["difficulty"], "sense_id": r["sense_id"],
            "source": r["source"], "license": r["license"]})
    for r in q("SELECT * FROM relations ORDER BY lexeme_id, relation, ordinal"):
        by_lex[r["lexeme_id"]]["relations"].append({
            "relation": r["relation"], "word": r["target_word"], "lexeme_id": r["target_lexeme_id"],
            "pos": r["target_pos"], "sense_id": r["source_sense_id"], "native": r["native_meaning"], "native_ai": bool(r["native_is_ai"]),
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
        "card_template": json.loads(meta.get("card_template", "null")),
        "schema_version": int(meta.get("schema_version", 0)),
        "target_language": meta.get("target_language"),
        "native_language": meta.get("native_language"),
        "created_at": meta.get("created_at"),
        "labels": {r["key"]: r["text"] for r in q("SELECT * FROM labels")},
        "redirects": {str(r["old_id"]): r["new_id"] for r in q("SELECT * FROM lexeme_redirects")},
        "lexemes": [lx if lx["status"] == "full" else
                    {k: lx[k] for k in ("id", "lemma", "normalized", "pos", "status", "entry_type")}
                    for lx in by_lex.values()],
    }
    con.close()
    rank_usages(pack["lexemes"], language=pack["target_language"] or "en")
    assign_cards(pack["lexemes"], pack["target_language"] or "en")
    # Each spelling's main part of speech first: the app takes a word's first
    # entry when it doesn't know the part of speech (sky 天空, not the verb
    # 「飲用不碰容器」). Stable, so the id order stays within a rank.
    pack["lexemes"].sort(key=lambda lx: lx.get("usage_rank", 0))
    # Quality rules (#182-#186): main senses first, checked examples first,
    # lint flags and reviewed overrides from lexicon/quality/.
    from . import quality
    quality.apply_pack(pack)
    quality.apply_decisions(pack)  # owner decision #191
    move_compound_synonyms(pack)  # #400 / card 413
    hide_minor_sense_synonyms(pack)  # #466 / card 481
    fix_confusable_glosses(pack)  # #581 / card 541
    drop_unlisted_confusables(pack)  # #457 / card 462
    from .picture_need import assign_picture_ids
    assign_picture_ids(pack["lexemes"])
    return pack


_CONFUSABLE_RELATIONS = ("near_homophones", "similar_spelling")
_GLOSS_SPLIT = re.compile(r"[、，,；;/]")
_GLOSS_NOISE = re.compile(r"[\s。．.「」『』\"'“”()（）]")


def _gloss_keys(text: str | None) -> list[str]:
    return [k for k in (_GLOSS_NOISE.sub("", p) for p in _GLOSS_SPLIT.split(text or "")) if k]


def fix_confusable_glosses(pack: dict) -> int:
    """「容易混淆的字」 Chinese is the other word's main meaning (問題回報 #581, card 541).
    A chip whose Chinese is not among the first three senses of the other spelling's main
    part of speech (usage_rank 0) shows a rare sense there: page→pale 「柵欄」 (pale is mainly
    「蒼白」), sea→set 「日落」. Such a chip takes that entry's first sense instead. A chip
    that would then equal the headword's own meaning is hidden (#420), and a chip whose
    target has no Chinese yet keeps its text. The database rows are not touched."""
    main_by_spelling: dict[str, dict] = {}
    for lx in pack.get("lexemes", []):
        if lx.get("status") == "full" and lx.get("usage_rank") == 0:
            main_by_spelling.setdefault(lx.get("normalized"), lx)
    lexeme_by_id = {lx["id"]: lx for lx in pack.get("lexemes", [])}
    changed = 0
    for lx in pack.get("lexemes", []):
        if lx.get("status") != "full" or not lx.get("relations"):
            continue
        head_keys = {k for sn in lx.get("senses") or [] for k in _gloss_keys(sn.get("native"))}
        for r in lx["relations"]:
            if r["relation"] not in _CONFUSABLE_RELATIONS or r.get("hide_by_default"):
                continue
            target = lexeme_by_id.get(r.get("lexeme_id"))
            main = main_by_spelling.get(target.get("normalized")) if target else None
            if main is None:
                continue
            top = [sn for sn in (main.get("senses") or [])[:3] if sn.get("native")]
            first = next((sn for sn in main.get("senses") or [] if sn.get("native")), None)
            if first is None:
                continue
            top_keys = {k for sn in top for k in _gloss_keys(sn["native"])}
            chip = _gloss_keys(r.get("native"))
            if chip and all(any(c == t or c in t or t in c for t in top_keys) for c in chip):
                continue  # already a main meaning of the other word
            if set(_gloss_keys(first["native"])) & head_keys:
                r["hide_by_default"] = True  # the same meaning as the headword (#420)
                r["detail"] = {**(r.get("detail") or {}), "hidden_reason": "same_meaning"}
            r["native"], r["native_ai"] = first["native"], bool(first.get("native_ai"))
            changed += 1
    return changed




def drop_unlisted_confusables(pack: dict) -> int:
    """「容易混淆的字」 shows only words that are entries in the lexicon (問題回報 #457, option A):
    a candidate with no lexeme_id is a word the learner cannot open (apple→ipl/apl, bread→brad,
    quick→buick). The exporter already skips these (exporter.export: tgt is None); the app pack
    kept them. Hidden rows stay as they are; the database rows are not touched."""
    dropped = 0
    for lx in pack.get("lexemes", []):
        if lx.get("status") != "full" or not lx.get("relations"):
            continue
        kept = []
        for r in lx["relations"]:
            if (r["relation"] in _CONFUSABLE_RELATIONS and r.get("lexeme_id") is None
                    and not r.get("hide_by_default")):
                dropped += 1
                continue
            kept.append(r)
        lx["relations"] = kept
    return dropped


MAIN_SENSES = 3


def hide_minor_sense_synonyms(pack: dict) -> int:
    """A synonym belongs to one meaning of the headword (問題回報 #466, option A): shown only
    when that meaning is among the first MAIN_SENSES, or when the meaning is not known yet.
    possession→enthusiasm (the 著魔 sense) and inert→soggy are hidden, not deleted."""
    hidden = 0
    for lx in pack.get("lexemes", []):
        if lx.get("status") != "full":
            continue
        rank = {sn["id"]: n for n, sn in enumerate(lx.get("senses") or [])}
        for r in lx.get("relations") or []:
            if r["relation"] != "synonyms" or r.get("hide_by_default"):
                continue
            sense_id = r.get("sense_id")
            if (r.get("detail") or {}).get("sense_match") == "none":
                reason = "no_sense"
            elif sense_id is not None and rank.get(sense_id, 0) >= MAIN_SENSES:
                reason = "minor_sense"
            else:
                continue
            r["hide_by_default"] = True
            r["detail"] = {**(r.get("detail") or {}), "hidden_reason": reason}
            hidden += 1
    return hidden


def move_compound_synonyms(pack: dict) -> int:
    """A synonym/antonym that is a multi-word phrase containing the headword
    (apple -> orchard apple tree, force -> force play) is a compound or a
    narrower term, not a substitute: file it under "related" (問題回報 #400)."""
    moved = 0
    for lx in pack.get("lexemes", []):
        if lx.get("status") != "full":
            continue
        head = re.compile(r"\b" + re.escape((lx.get("lemma") or "").lower()) + r"\b")
        for r in lx.get("relations") or []:
            word = (r.get("word") or "").lower()
            if (r["relation"] in ("synonyms", "antonyms") and not r.get("hide_by_default")
                    and " " in word.strip() and head.search(word)):
                r["detail"] = {**(r.get("detail") or {}), "moved_from": r["relation"]}
                r["relation"] = "related"
                moved += 1
    return moved


def assign_cards(lexemes: list[dict], language: str) -> None:
    """A form shares its word's card (問題回報 #51, owner 2026-10-14:
    詞形變化跟原形共用同一張卡片): tethered, dried and lying get "card":
    tether, dry, lie when that word is a full entry here, and the app files
    the form's photos and saved word under that card. Words spelt like a
    form but meaning something else (left, building) have none."""
    from .adapters.base import card_base
    full = {lx["normalized"] for lx in lexemes if lx.get("status") == "full"}
    for lx in lexemes:
        lx.pop("card", None)
        lx.pop("card_form", None)
        word = lx["normalized"]
        if lx.get("status") != "full" or " " in word:
            continue
        base = card_base(word, language)
        if base and base != word and base in full:
            lx["card"] = base
            if lx.get("pos") in _form_only_pos(word, language):
                # dried the verb is only dry's form: no meaning of its own
                # on dry's card (dried the adjective, 乾燥的, has one).
                lx["card_form"] = True


@lru_cache(maxsize=50_000)
def _form_only_pos(word: str, language: str) -> frozenset[str]:
    from . import kaikki_index
    from .adapters.base import inflection_bases
    from .adapters.kaikki import _pos, inflection_only_pos
    entries = [e for e in kaikki_index.lookup(language, word) or []
               if str(e.get("word", "")).lower() == word]
    if inflection_bases(word, language):  # runs: every part of speech
        return frozenset(p for e in entries if (p := _pos(e)))
    return frozenset(inflection_only_pos(entries))


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
            if of is not None and f["field"].startswith("fr_") and pos not in ("noun", "verb", "adj"):
                return False  # merci the interjection is not 「le merci」
            if of is None:
                return True
            if pos not in ("noun", "verb", "adj", "adv"):
                # good / sage the interjection, ample the determiner: a form that
                # belongs to a noun / verb / adjective sibling of the spelling is
                # that sibling's (better/best on the 感嘆詞 card, 問題回報 #479);
                # a determiner with no such sibling (many → more) keeps it.
                owners = (of,) if isinstance(of, str) else tuple(of)
                return not any(o.get("pos") in owners for o in group if o is not lex)
            # French gender / number forms belong to nouns and adjectives
            # alike (card #429: chat lost chats, chatte).
            either = catalog.FORM_POS.get(f["field"])
            if isinstance(either, tuple) and pos in either:
                return True
            return of == pos or (pos == "adj" and participle and of == "verb")

        for lex in group:
            lex["forms"] = [dict(f) for f in shared if own(lex, f)]


_CORE_POS = ("noun", "verb", "adj", "adv")
# How much one example sentence weighs against one sense when the list and
# the dictionaries tie. Card #164 simulated 0 / 0.25 / 0.5 / 1.0 and a cap of
# 2–3 examples per sense on 1,787 spellings: anything below full weight
# flipped buoy / burrow / hose / stain / tamper to the verb, so examples keep
# full weight; the known misses are cast / lift (one noun sense carrying 16
# examples), charter, nudge (this ECDICT has no verb line), outcast, reek.
_EXAMPLE_WEIGHT = 1.0


@lru_cache(maxsize=50_000)
def dictionary_pos(word: str) -> tuple[int, dict[str, int], dict[str, int]]:
    """How many general dictionaries know ``word``, which parts of speech
    each lists, and how much they say under each: (known, {pos: votes},
    {pos: weight}). Sources: Open English WordNet (weight = synsets) and
    ECDICT (weight = meanings) — both compact dictionaries that leave out
    the archaic / dialect senses Wiktionary documents at length (card
    #164). A source that does not have the word at all is not counted, and
    a failure (package or index missing) is neutral: (0, {}, {})."""
    known = 0
    votes: dict[str, int] = {}
    weight: dict[str, int] = {}
    try:
        from .adapters import oewn
        poses = oewn._thread.submit(
            lambda: [oewn.POS.get(ss.pos, ss.pos) for ss in oewn._wordnet().synsets(word)]
        ).result(timeout=30)
        if poses:
            known += 1
            for p in set(poses):
                votes[p] = votes.get(p, 0) + 1
            for p in poses:
                weight[p] = weight.get(p, 0) + 1
    except Exception:  # noqa: BLE001 — wn not installed / no data
        pass
    try:
        from .adapters import ecdict
        translation = ecdict.ECDict().translation(word)
        meanings = ecdict.meanings(translation) if translation else []
        if meanings:
            known += 1
            for p in {p for p, _ in meanings}:
                votes[p] = votes.get(p, 0) + 1
            for p, words in meanings:
                weight[p] = weight.get(p, 0) + len(words)
    except Exception:  # noqa: BLE001 — no ecdict.csv
        pass
    return known, votes, weight


def rank_usages(lexemes: list[dict], cefr_by_pos: dict | None = None,
                pos_votes=None, language: str = "en") -> None:
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
    usage's share of the senses + examples scales it down (log10 share).

    Evidence counts senses/examples at full weight only when the sense is
    not itself low-priority (問題回報 #216: frail's archaic/dated noun sense
    is documented with more senses and examples in Kaikki than the common
    adjective, so a raw count picked the noun as "main").

    Before the evidence, the general dictionaries vote (card #164): when at
    least two of them know the word, a core part of speech that fewer of
    them list ranks after one they all list (archaic / vulgar are only
    adjectives there, preen / snuggle only verbs — however many Wiktionary
    senses the noun has); among parts of speech they all list, the one
    they say more about comes first (cast / lift / reek: more WordNet
    synsets and ECDICT meanings for the verb than for the noun). The
    dictionaries also outrank the -ing / -ed rule (underlying is an
    adjective to both; the noun is Wiktionary's only). ``pos_votes(word) ->
    (known, {pos: votes}[, {pos: weight}])`` is injectable for tests;
    default :func:`dictionary_pos`."""
    from . import quality
    from .adapters.local import _family_cap, capped_frequency_level, fr_cefr_source

    if cefr_by_pos is None and language != "en":
        # The CEFR-J list is English: a French "chat" / "grand" must not take
        # the English word's level (card #325). Levels stay the stored ones.
        cefr_by_pos = {}
    if cefr_by_pos is None:
        try:
            from .adapters.local import cefr_list
            cefr_by_pos = {w: v[1] for w, v in cefr_list().items()}
        except Exception:  # noqa: BLE001 — no list: senses and examples only
            cefr_by_pos = {}
    if pos_votes is None:
        pos_votes = dictionary_pos
    listed_pos = {"adj.": "adj", "adv.": "adv"}
    groups: dict[str, list[dict]] = {}
    for lx in lexemes:
        if lx.get("status") == "full":
            groups.setdefault(lx["normalized"], []).append(lx)

    def weighted_evidence(lx: dict, example_weight: float) -> float:
        senses = lx.get("senses") or []
        stale = {id(s) for s in senses if quality.sense_is_low(s, False)}
        stale_db_ids = {s.get("id") for s in senses if id(s) in stale and s.get("id") is not None}
        sense_weight = sum(0.2 if id(s) in stale else 1.0 for s in senses)
        examples = sum(0.2 if ex.get("sense_id") in stale_db_ids else 1.0
                       for ex in lx.get("examples") or [])
        return 1 + sense_weight + example_weight * examples

    for word, group in groups.items():
        listed = {listed_pos.get(p, p): lv for p, lv in (cefr_by_pos.get(word) or {}).items()}
        evidence = {id(lx): weighted_evidence(lx, _EXAMPLE_WEIGHT) for lx in group}
        # The rare usages' level comes from their share of everything the
        # dictionary records, examples included (問題回報 #16).
        share_of = {id(lx): weighted_evidence(lx, 1.0) for lx in group}
        participle = not listed and word.endswith(("ing", "ed"))
        known, votes = 0, {}
        if len(group) > 1:
            try:
                known, votes, *_ = pos_votes(word)
            except Exception:  # noqa: BLE001 — neutral when a source breaks
                known, votes = 0, {}

        def dictionary_tier(pos: str) -> int:
            # 0 = every dictionary that knows the word lists this part of
            # speech … known = none does. Only with two or more sources, so
            # one dictionary's gap (ECDICT has backlight only as a verb)
            # cannot flip a word by itself; other parts of speech (phrase,
            # intj) are neutral.
            if known < 2 or pos not in _CORE_POS:
                return 0
            return known - votes.get(pos, 0)

        def key(lx):
            lv = listed.get(lx["pos"])
            return (0 if lv else 1,
                    _LEVELS.index(lv) if lv in _LEVELS else 9,
                    # -ing / -ed words not in the list: the verb form comes
                    # after the noun and the adjective (potted 盆栽的) …
                    1 if participle and lx["pos"] == "verb" else 0,
                    dictionary_tier(lx["pos"]),
                    # … and, when the dictionaries do not separate them,
                    # the noun before the adjective (railing).
                    {"noun": 0, "adj": 1}.get(lx["pos"], 2) if participle else 0,
                    -evidence[id(lx)], _POS_ORDER.get(lx["pos"], 9), lx["id"])

        group.sort(key=key)
        total = sum(share_of.values())
        main = group[0]
        for rank, lx in enumerate(group):
            lx["usage_rank"] = rank
            lv = listed.get(lx["pos"])
            if rank == 0 or lv:
                lx["rare_usage"] = False
                if lv and lv != lx.get("cefr"):
                    lx["headword_cefr"], lx["cefr"], lx["cefr_source"] = lx.get("cefr"), lv, "cefr-j"
                elif lv:
                    lx["cefr_source"] = "cefr-j"
                elif lx.get("cefr"):
                    # Outside the list the level is a frequency estimate,
                    # capped by the word-family rule above so it is never
                    # far above the base's listed level (#214/#218); the
                    # app says it is an estimate either way (#139 decision:
                    # 標「估算」; #132 noodle).
                    cap = _family_cap(word, language)
                    if cap is not None:
                        lx["cefr"] = _LEVELS[min(_LEVELS.index(lx["cefr"]), cap)]
                    lx["cefr_source"] = (fr_cefr_source(word) if language == "fr"
                                         else "frequency_estimate")
                continue
            lx["rare_usage"] = True
            lx["headword_cefr"] = lx.get("cefr")
            if lx.get("zipf") is None:
                continue
            share = share_of[id(lx)] / total
            # Dictionary evidence overstates a minor part of speech's real use
            # (out 感嘆詞「滾」 has ~4% of the entries but far less of the
            # text), so the share counts twice (card #397).
            estimate = capped_frequency_level(word, lx["zipf"] + 2 * math.log10(share), language)
            floor = main.get("cefr") or lx.get("cefr")
            if floor in _LEVELS and _LEVELS.index(estimate) < _LEVELS.index(floor):
                # A rarer usage is never shown easier than the word's main
                # one -- unless a word-family cap says the word itself
                # should never show as hard as that main usage (standing
                # adj <= stand A2 + 1, even though standing noun 「social
                # standing」 is listed C2, 問題回報 #218).
                cap = _family_cap(word, language)
                estimate = floor if cap is None or _LEVELS.index(floor) <= cap else _LEVELS[cap]
            lx["cefr"], lx["cefr_source"] = estimate, "frequency_estimate"


def install(release_dir: Path, target: str, native: str, app_assets: Path = APP_ASSETS) -> dict:
    """Copy a release's audio and pictures into the Flutter app's assets
    (app/assets/lexicon/media/ …). The pack JSON itself is the slim bundle
    that lexicon/tools/card268_bundle_pack.py writes: a raw export (~250 MB,
    every stub, no catalog pictures) is not shippable and once replaced the
    bundle (問題回報 #405), so it is never copied over it."""
    base = release_dir.name
    pack = release_dir / f"{base}.json"
    if not pack.exists():
        raise FileNotFoundError(f"{pack.name} 不存在（請重新匯出）")
    app_assets.mkdir(parents=True, exist_ok=True)
    name = f"{target}-{native}"
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
    return {"pack": str(app_assets / f"{name}.json"), "release": base, "media_copied": copied,
            "bundle": BUNDLE_COMMAND}


# How the shipped pack is rebuilt (card #268 settings: 480 px WebP, quality 60).
BUNDLE_COMMAND = "python lexicon/tools/card268_bundle_pack.py --max-side 480 --quality 60"
