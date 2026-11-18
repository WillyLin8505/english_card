"""French verb conjugation data from Wiktionary / Kaikki only (card #1219, 問題回報 #1671).

Everything here is read from the open dump (CC BY-SA) or computed by a rule from forms the dump
has; what the source does not carry stays empty. Field names: fr_<tense>_<person> (tense =
present / imperfect / future / conditional / subjunctive / passe_simple, person = 1s 2s 3s 1p 2p 3p),
fr_imperative_{2s,1p,2p}, fr_past_participle{,_f,_mpl,_fpl}, and the grammar fields fr_verb_group
(1 / 2 / 3), fr_conj_model (model verb: aimer, finir, partir, prendre …), fr_pronominal (yes),
fr_h_aspire (yes).
"""
from __future__ import annotations

import re
from typing import Callable

PERSONS = ("1s", "2s", "3s", "1p", "2p", "3p")
TENSES = ("present", "imperfect", "future", "conditional", "subjunctive", "passe_simple")
TENSE_FIELDS = [f"fr_{t}_{p}" for t in TENSES for p in PERSONS]
IMPERATIVE_FIELDS = ["fr_imperative_2s", "fr_imperative_1p", "fr_imperative_2p"]
PARTICIPLE_FIELDS = ["fr_past_participle_f", "fr_past_participle_mpl", "fr_past_participle_fpl"]
# What the App already had (present, past/present participle, imperfect and future je, auxiliary).
CONJ_FIELDS = (TENSE_FIELDS + IMPERATIVE_FIELDS + PARTICIPLE_FIELDS
               + ["fr_past_participle", "fr_present_participle"])
META_FIELDS = ["fr_verb_group", "fr_conj_model", "fr_pronominal", "fr_h_aspire"]
H_CATEGORY = "aspirated h"

# Bescherelle's model verbs of the 3rd group (and the 1st-group irregular aller): a verb takes
# one as its model when it ends in it and the forms agree after the prefix (comprendre → prendre).
MODELS_3 = (
    "aller", "partir", "sentir", "vêtir", "couvrir", "cueillir", "assaillir", "faillir", "bouillir",
    "dormir", "courir", "mourir", "servir", "fuir", "venir", "acquérir", "pleuvoir", "pouvoir",
    "mouvoir", "savoir", "devoir", "recevoir", "valoir", "voir", "vouloir", "asseoir", "rendre",
    "prendre", "battre", "mettre", "rire", "suivre", "vivre", "écrire", "boire", "conclure",
    "absoudre", "résoudre", "coudre", "moudre", "croire", "craindre", "peindre", "joindre", "naître",
    "paraître", "plaire", "taire", "faire", "dire", "lire", "conduire", "croître", "vaincre",
    "être", "avoir", "falloir", "tenir", "ouvrir", "offrir", "souffrir", "mentir", "sortir",
    "rompre", "connaître", "cuire", "nuire", "luire", "traire", "foutre", "bruire",
)


def _entries(lookup: Callable, lemma: str, pos: str = "verb") -> list[dict]:
    from .adapters import kaikki
    return [e for e in (lookup(lemma) or []) if e.get("lang_code", "fr") == "fr"
            and (e.get("word") or lemma).lower() == lemma.lower() and kaikki._pos(e) == pos]


def verb_values(entries: list[dict], lemma: str) -> dict[str, list[str]]:
    """field → forms for one lemma's verb entries (no Wiktionary table → {})."""
    from .adapters import kaikki
    out: dict[str, list[str]] = {}
    for e in entries:
        for fo in e.get("forms", []):
            form = (fo.get("form") or "").strip()
            tags = set(fo.get("tags", []))
            if not form or form == lemma or " " in form or "-" in form or kaikki.FR_ELIDED.match(form):
                continue
            if not kaikki.fr_spelling_ok(form) or tags & (kaikki.LOW_TAGS | {"reflexive"}):
                continue
            f = kaikki.form_field("verb", tags, "fr")
            if f and form not in out.setdefault(f, []):
                out[f].append(form)
    return out


def participle_agreement(participle: str, lookup: Callable) -> dict[str, list[str]]:
    """fini → finie / finis / finies, from the dump's own entries «feminine singular of fini»."""
    kinds = (("fr_past_participle_f", "feminine singular of "),
             ("fr_past_participle_mpl", "masculine plural of "),
             ("fr_past_participle_fpl", "feminine plural of "))
    cand = {"fr_past_participle_f": (participle + "e",),
            "fr_past_participle_mpl": (participle + "s",),
            "fr_past_participle_fpl": (participle + "es",)}
    out: dict[str, list[str]] = {}
    for field, gloss in kinds:
        for w in cand[field]:
            if w == participle:
                continue  # pris is also its own masculine plural: no second spelling to show
            for e in lookup(w) or []:
                if e.get("lang_code", "fr") != "fr" or (e.get("word") or w) != w:
                    continue
                if any((s.get("form_of") or [{}])[0].get("word") == participle
                       and any(g.startswith(gloss) for g in s.get("glosses", []))
                       for s in e.get("senses", [])):
                    if w not in out.setdefault(field, []):
                        out[field].append(w)
    return out


def verb_group(lemma: str, values: dict[str, list[str]]) -> str | None:
    base = re.sub(r"^(?:se |s['’])", "", lemma)
    if base == "aller":
        return "3"
    if base.endswith("er"):
        return "1"
    if base.endswith("ir") and any(f.endswith("issant") for f in values.get("fr_present_participle", [])):
        return "2"
    return "3" if base.endswith(("ir", "oir", "re")) else None


def h_aspire(entries: list[dict]) -> bool:
    for e in entries:
        cats = list(e.get("categories") or [])
        for s in e.get("senses", []):
            cats += s.get("categories") or []
        if any(H_CATEGORY in (c.get("name") if isinstance(c, dict) else str(c)) for c in cats):
            return True
    return False


def is_pronominal(verb_entries: list[dict], lemma: str) -> bool:
    """se lever, or a verb with a sense Wiktionary tags reflexive / pronominal."""
    return _strip(lemma) != lemma or any(
        {"reflexive", "pronominal"} & set(s.get("tags") or [])
        for e in verb_entries for s in e.get("senses", []))


def _first(values: dict[str, list[str]], field: str) -> str:
    return (values.get(field) or [""])[0]


def _strip(lemma: str) -> str:
    return re.sub(r"^(?:se |s['’])", "", lemma)


def first_group_model(lemma: str, values: dict[str, list[str]]) -> str | None:
    """The Bescherelle model of an -er verb, decided from its own present forms."""
    base = _strip(lemma)
    stem = base[:-2]
    forms = values.get("fr_present_1s") or []
    p1s = forms[0] if forms else ""
    if base == "aller":
        return "aller"
    if base.endswith(("envoyer",)):
        return "envoyer"
    if not p1s:
        return None
    if stem + "e" in forms and not base.endswith("yer"):
        if base.endswith("cer"):
            return "placer"
        if base.endswith("ger"):
            return "manger"
        return "aimer"
    if base.endswith("yer") and any(f == stem[:-1] + "ie" for f in forms):
        return "payer" if base.endswith("ayer") else "employer"
    if base.endswith(("eler", "eter")) and p1s == stem + stem[-1] + "e":
        return "appeler" if base.endswith("eler") else "jeter"
    # e → è in the last syllable (lever, acheter, geler) / é → è (céder)
    m = re.match(r"^(.*)([eé])([^aeiouyéèêàâîïôûù]+)er$", base)
    if m and p1s == f"{m[1]}è{m[3]}e":
        return "lever" if m[2] == "e" else "céder"
    return None


def second_group_model(lemma: str, values: dict[str, list[str]]) -> str | None:
    base = _strip(lemma)
    p1s = _first(values, "fr_present_1s")
    if p1s == base[:-2] + "is":
        return "finir"
    return "haïr" if base.endswith("haïr") else None


def third_group_model(lemma: str, values: dict[str, list[str]], lookup: Callable) -> str | None:
    base = _strip(lemma)
    if base in MODELS_3:
        return base
    probe = ("fr_present_1s", "fr_present_3p", "fr_future_1s", "fr_past_participle")
    mine = {f: _first(values, f) for f in probe}
    for model in sorted(MODELS_3, key=len, reverse=True):
        if not base.endswith(model) or base == model:
            continue
        prefix = base[:-len(model)]
        mv = verb_values(_entries(lookup, model), model)
        ok = 0
        for f in probe:
            a, b = mine[f], _first(mv, f)
            if a and b:
                if a != prefix + b and not (a.startswith(prefix) and a[len(prefix):] == b):
                    ok = -99
                    break
                ok += 1
        if ok >= 2:
            return model
    return None


def conj_model(lemma: str, values: dict[str, list[str]], group: str | None,
               lookup: Callable) -> str | None:
    if group == "1":
        return first_group_model(lemma, values)
    if group == "2":
        return second_group_model(lemma, values)
    if group == "3":
        return third_group_model(lemma, values, lookup)
    return None
