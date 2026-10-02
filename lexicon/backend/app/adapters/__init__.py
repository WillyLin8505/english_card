"""Adapter registry: one SourceAdapter per catalog source."""

from __future__ import annotations

from .. import catalog
from .ai import AITranslate
from .base import Candidate, Context, SourceAdapter
from .cmudict import CMUdict
from .commons import WikimediaCommons
from .datamuse import Datamuse
from .http import SourceError
from .kaikki import Kaikki
from .morph import MorphLocal
from .local import (CefrJ, KaikkiWordlist, LexiconLookup, LocalCalc, NotImplementedSource,
                    SystemTTS, WordFreq)
from .oewn import OEWN
from .tatoeba import Tatoeba

ADAPTERS: dict[str, SourceAdapter] = {a.key: a for a in [
    Kaikki(), OEWN(), CMUdict(), Tatoeba(), Datamuse(), WordFreq(), CefrJ(), KaikkiWordlist(),
    LocalCalc(), LexiconLookup(), AITranslate(), SystemTTS(), MorphLocal(), WikimediaCommons()]}
for _key, _src in catalog.SOURCES.items():
    if not _src.implemented:
        ADAPTERS[_key] = NotImplementedSource(_key)
assert set(ADAPTERS) == set(catalog.SOURCES), set(catalog.SOURCES) ^ set(ADAPTERS)


def configure(session) -> None:
    """Point adapters at their active snapshots."""
    from sqlalchemy import select

    from .. import models as m
    rows = session.execute(select(m.SourceSnapshot).where(m.SourceSnapshot.active.is_(True),
                                                          m.SourceSnapshot.status == "ready")
                           ).scalars().all()
    for a in ADAPTERS.values():
        a.snapshot = None
        a.snapshots = {}
    for r in rows:
        a = ADAPTERS.get(r.source)
        if a is None:
            continue
        info = {"id": r.id, "path": r.path, "version": r.version, "language": r.language}
        a.snapshots[r.language] = info
        a.snapshot = info


__all__ = ["ADAPTERS", "Candidate", "Context", "SourceAdapter", "SourceError", "configure"]
