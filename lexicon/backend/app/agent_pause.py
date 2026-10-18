"""Board start/pause state shared by the API, workers, and quality tools.

The owner toggles bots on the schedule board; state lives in
lexicon/state/paused_agents.json. Reads are cached a few seconds so the
tag queue and tools can poll cheaply. Writes go through set_paused.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from . import config

PAUSED_FILE = config.HOME / "state" / "paused_agents.json"
_CACHE: dict = {"at": 0.0, "data": {}}


def paused_agents(*, max_age: float = 3.0, force: bool = False) -> dict:
    """Map of paused agent name -> ISO timestamp. Cached max_age seconds."""
    now = time.monotonic()
    if not force and now - _CACHE["at"] < max_age:
        return _CACHE["data"]
    try:
        data = json.loads(PAUSED_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    _CACHE["at"] = now
    _CACHE["data"] = data
    return data


def is_paused(name: str, *, max_age: float = 3.0) -> bool:
    return name in paused_agents(max_age=max_age)


def set_paused(name: str, paused: bool) -> dict:
    d = dict(paused_agents(force=True))
    if paused:
        d[name] = datetime.now(timezone.utc).isoformat()
    else:
        d.pop(name, None)
    PAUSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PAUSED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(PAUSED_FILE)
    _CACHE["at"] = time.monotonic()
    _CACHE["data"] = d
    return d
