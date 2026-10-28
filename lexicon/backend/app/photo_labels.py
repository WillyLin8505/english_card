"""Default photo labels picked from the candidate grid (card #741, 問題回報 #889 C).

``photo_grid.build_grid`` gives every candidate word of a photo (the table of card
#863/#645, already checked by Qwen's fit pass of card #722). This layer, which only
reads that grid, chooses what the App shows by default for a learner level:
mostly nouns, plus verbs / adjectives / phrases that fit the photo, more of them
the higher the level (A1 almost all nouns). Adverbs only when the photo shows
them (or Qwen rated them as a clear fit). Each label carries ``pos`` so the App
can switch parts of speech on and off.

label = {"word", "pos", "cefr", "concept_id", "anchor", "source", "fit"?}
"""
from __future__ import annotations

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
# Labels shown per photo, and the share of them that are nouns, by learner level.
LABEL_BUDGET = {"A1": 6, "A2": 7, "B1": 8, "B2": 9, "C1": 10, "C2": 10}
NOUN_SHARE = {"A1": 0.95, "A2": 0.85, "B1": 0.7, "B2": 0.65, "C1": 0.6, "C2": 0.6}
# How the non-noun share is split (adverbs are handled separately).
OTHER_WEIGHTS = {"adjective": 0.4, "verb": 0.4, "phrase": 0.2}
ADVERB_MAX = 1
ADVERB_MIN_FIT = 0.8      # a related (not photo-seen) adverb needs this Qwen score
OTHER_MIN_FIT = 0.6       # a related verb/adjective/phrase needs this Qwen score
LEVEL_REACH = 1           # words more than this many levels above the learner are left out
DEFAULT_LEVEL = "B1"


def _level_index(level) -> int:
    level = str(level or "").upper()
    return LEVELS.index(level) if level in LEVELS else LEVELS.index(DEFAULT_LEVEL)


def _candidates(grid: dict, user_idx: int) -> dict[str, list[dict]]:
    by_pos: dict[str, list[dict]] = {}
    for cell in grid.get("cells") or []:
        pos, cefr = cell.get("pos"), str(cell.get("cefr") or "").upper()
        if cefr not in LEVELS:
            continue
        distance = LEVELS.index(cefr) - user_idx
        if distance > LEVEL_REACH:
            continue
        for w in cell.get("words") or []:
            photo = w.get("source") == "photo"
            fit = w.get("fit")
            if not photo and pos != "noun":
                floor = ADVERB_MIN_FIT if pos == "adverb" else OTHER_MIN_FIT
                if fit is None or fit < floor:
                    continue
            by_pos.setdefault(pos, []).append({
                "word": w["word"], "pos": pos, "cefr": cefr, "concept_id": w.get("concept_id"),
                "anchor": w.get("anchor"), "source": w.get("source"),
                **({"fit": fit} if fit is not None else {}),
                "_rank": (0 if photo else 1, abs(distance), -(fit or 0)),
            })
    for words in by_pos.values():
        words.sort(key=lambda x: x["_rank"])
    return by_pos


def pick_labels(grid: dict, level: str | None) -> list[dict]:
    """The default labels of one photo for a learner at ``level`` (photo-seen words first)."""
    idx = _level_index(level)
    key = LEVELS[idx]
    pool = _candidates(grid, idx)
    budget = LABEL_BUDGET[key]
    noun_n = round(budget * NOUN_SHARE[key])
    other_n = budget - noun_n
    picked: list[dict] = []
    # Photo-seen adverbs only; at most ADVERB_MAX, and they take a slot from the others.
    adverbs = pool.get("adverb", [])[:ADVERB_MAX] if other_n >= 2 else []
    adverbs = [a for a in adverbs if a["source"] == "photo" or a.get("fit", 0) >= ADVERB_MIN_FIT]
    other_n -= len(adverbs)
    quotas = {p: int(other_n * wt) for p, wt in OTHER_WEIGHTS.items()}
    for p in sorted(OTHER_WEIGHTS, key=lambda p: -OTHER_WEIGHTS[p]):  # spread the rounding rest
        if sum(quotas.values()) >= other_n:
            break
        quotas[p] += 1
    for p, n in quotas.items():
        picked += pool.get(p, [])[:n]
    picked += adverbs
    # Nouns take their share, then any unused slots (A1 has few other parts of speech).
    nouns = pool.get("noun", [])
    picked += nouns[:noun_n + max(0, budget - noun_n - len(picked))]
    picked = picked[:budget]
    picked.sort(key=lambda x: (x["pos"] != "noun", x["_rank"]))
    for x in picked:
        x.pop("_rank")
    return picked


def pos_counts(labels: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in labels:
        out[x["pos"]] = out.get(x["pos"], 0) + 1
    return out
