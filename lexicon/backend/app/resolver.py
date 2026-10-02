"""The Resolver: combines one field's per-source candidates, in policy
order, with one of the five strategies (spec section 08):

  FIRST_VALID     the first source with a valid value wins; later sources
                  aren't asked.
  MERGE_UNIQUE    every source, merged in order, duplicates removed.
  FILL_MISSING    item by item (a sense, an example, a word …): each slot
                  takes the first source that has it; later sources are
                  asked only while slots are still missing.
  BEST_SCORE      every source; per slot the highest confidence wins
                  (ties go to the earlier source).
  APPEND_LIMITED  append source by source until the limit, then stop
                  asking.

Incremental: the pipeline asks `wants_more()` before calling each next
source, so short-circuiting strategies never touch later sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STRATEGIES = ("FIRST_VALID", "MERGE_UNIQUE", "FILL_MISSING", "BEST_SCORE", "APPEND_LIMITED")


@dataclass
class Adopted:
    candidate: object  # adapters.Candidate
    position: int  # the policy step's position
    source: str


@dataclass
class Resolver:
    strategy: str
    limit: int | None = None
    # Slots the field should fill (senses, examples, words …); None = unknown.
    expected: set[str] | None = None
    # (at least, at most) items per slot, for fields filled per level: a
    # slot is missing until it has the first number, and takes no more
    # than the second (MERGE_UNIQUE / APPEND_LIMITED).
    per_slot: tuple[int, int] | None = None
    # Ask later sources only while a slot is still missing (recordings: a
    # second source only for the accent the first lacks).
    only_missing: bool = False
    adopted: list[Adopted] = field(default_factory=list)
    _keys: set = field(default_factory=set)
    _filled: set = field(default_factory=set)
    _best: dict = field(default_factory=dict)  # BEST_SCORE: slot → (confidence, order, Adopted)
    _order: int = 0

    def __post_init__(self):
        if self.strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {self.strategy}")

    # ── asking ──
    def wants_more(self, kind: str = "") -> bool:
        s = self.strategy
        if self.only_missing and self.expected is not None:
            return bool(self.missing())
        if s == "FIRST_VALID":
            return not self.adopted
        if self.per_slot and self.expected is not None and s in ("MERGE_UNIQUE", "APPEND_LIMITED"):
            if kind == "ai":  # AI only for levels the other sources left short
                return bool(self.missing())
            return self.limit is None or len(self.adopted) < self.limit
        if s == "APPEND_LIMITED":
            return self.limit is None or len(self.adopted) < self.limit
        if s == "FILL_MISSING":
            if self.expected is not None:
                return bool(self.missing())
            # Unknown slots: keep asking cheap sources; an AI step only
            # when nothing at all was found.
            return not (kind == "ai" and self.adopted)
        return True  # MERGE_UNIQUE, BEST_SCORE

    def missing(self) -> set[str]:
        if self.expected is None:
            return set() if self.adopted else {""}
        if self.per_slot:
            n = self._per_slot_counts()
            return {slot for slot in self.expected if n.get(slot, 0) < self.per_slot[0]}
        have = self._filled if self.strategy != "BEST_SCORE" else set(self._best)
        if self.strategy in ("FIRST_VALID", "MERGE_UNIQUE", "APPEND_LIMITED"):
            have = {a.candidate.slot for a in self.adopted}
        return set(self.expected) - have

    # ── adding one source's valid candidates, in that source's order ──
    def add(self, position: int, source: str, candidates: list) -> int:
        """Returns how many of these candidates were adopted."""
        s = self.strategy
        before = len(self.adopted)
        if s == "FIRST_VALID":
            if not self.adopted and candidates:
                for c in candidates:
                    self._take(c, position, source)
        elif s in ("MERGE_UNIQUE", "APPEND_LIMITED"):
            for c in candidates:
                if s == "APPEND_LIMITED" and self.limit is not None \
                        and len(self.adopted) >= self.limit:
                    break
                if self.per_slot and self._per_slot_counts().get(c.slot, 0) >= self.per_slot[1]:
                    continue
                self._take(c, position, source)
        elif s == "FILL_MISSING":
            new_slots = set()
            for c in candidates:
                if c.slot in self._filled:
                    continue
                if self.expected is not None and c.slot not in self.expected:
                    continue
                if self._take(c, position, source):
                    new_slots.add(c.slot)
            self._filled |= new_slots
        elif s == "BEST_SCORE":
            for c in candidates:
                self._order += 1
                cur = self._best.get(c.slot or c.key)
                if cur is None or c.confidence > cur[0]:
                    self._best[c.slot or c.key] = (c.confidence, self._order,
                                                   Adopted(c, position, source))
            self.adopted = [v[2] for v in sorted(self._best.values(), key=lambda v: v[1])]
            return sum(1 for a in self.adopted if a.source == source)
        return len(self.adopted) - before

    def _per_slot_counts(self) -> dict[str, int]:
        n: dict[str, int] = {}
        for a in self.adopted:
            n[a.candidate.slot] = n.get(a.candidate.slot, 0) + 1
        return n

    def _take(self, c, position, source) -> bool:
        if c.key in self._keys:
            return False
        self._keys.add(c.key)
        self.adopted.append(Adopted(c, position, source))
        return True

    def result(self) -> list[Adopted]:
        items = self.adopted
        if self.strategy == "BEST_SCORE":
            items = sorted(items, key=lambda a: -a.candidate.confidence)
        if not self.limit or len(items) <= self.limit:
            return list(items)
        if self.strategy == "FILL_MISSING":
            # Every filled slot (e.g. each part of speech) keeps its first
            # item before any slot gets a second one.
            first, seen = [], set()
            for a in items:
                if a.candidate.slot not in seen:
                    seen.add(a.candidate.slot)
                    first.append(a)
            keep = {id(a) for a in first[: self.limit]}
            for a in items:
                if len(keep) >= self.limit:
                    break
                keep.add(id(a))
            return [a for a in items if id(a) in keep]
        return items[: self.limit]


def status_of(adopted: list, missing: set[str], expected: set[str] | None, errors: int,
              asked: int) -> str:
    """complete / partial / missing / failed."""
    if not adopted:
        return "failed" if asked and errors == asked else "missing"
    if expected is not None and missing:
        return "partial"
    return "complete"
