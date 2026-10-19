"""One request budget for every process that talks to Wikimedia (問題回報 #339).

Text workers (audio), image workers (pictures) and foreground tools each used
to rate-limit only themselves, so together they went over what Commons
tolerates and got "429 … please contact noc@wikimedia.org".  Every request to
a Wikimedia host now takes a slot from a token schedule kept in a small state
file under a file lock, shared by all processes on the machine:

- slots are MIN_INTERVAL apart in total (all hosts, all processes);
- a 429/503 pauses everyone (Retry-After or exponential backoff, capped) and
  widens the interval while strikes last, instead of each process retrying on
  its own and all of them resuming together;
- successes after a quiet minute take the strikes back down.

The mechanics live in `rate_gate.Gate` (shared with the Smithsonian and
Openverse gates of 問題回報 #360); this module keeps the Wikimedia constants
and the function API every caller and test uses.  Wikimedia is the primary
picture and audio source, so its gate waits a pause out (no skip).
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from . import config
from .rate_gate import Gate

STATE = Path(os.environ.get("LEXICON_WIKIMEDIA_GATE", config.HOME / "state" / "wikimedia_gate.json"))
MIN_INTERVAL = float(os.environ.get("LEXICON_WIKIMEDIA_INTERVAL", "1.0"))  # seconds, machine-wide
MAX_INTERVAL = 8.0
BACKOFF_BASE = 10.0
BACKOFF_MAX = 300.0
CALM_S = 60.0  # no 429 for this long → successes lower the strikes again

DOMAINS = ("wikimedia.org", "wikidata.org", "wikipedia.org", "wiktionary.org", "lingualibre.org")


def is_wikimedia(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in DOMAINS)


class _WikimediaGate(Gate):
    """A Gate that reads this module's constants on every call, so tests (and
    operators) can change STATE / MIN_INTERVAL / BACKOFF_BASE on the module."""

    def __init__(self):  # no super().__init__: the settings below are live properties
        self.name = "wikimedia"
        self.hosts = DOMAINS
        self.skip_when_paused = False  # the primary source: wait the pause out

    state = property(lambda self: STATE)
    min_interval = property(lambda self: MIN_INTERVAL)
    max_interval = property(lambda self: MAX_INTERVAL)
    backoff_base = property(lambda self: BACKOFF_BASE)
    backoff_max = property(lambda self: BACKOFF_MAX)
    calm_s = property(lambda self: CALM_S)

    def matches(self, url: str) -> bool:
        return is_wikimedia(url)


GATE = _WikimediaGate()


def wait_turn() -> float:
    """Reserve the next machine-wide slot and sleep until it. Returns seconds waited."""
    return GATE.wait_turn()


def penalize(retry_after: str | float | None = None) -> float:
    """A 429/503 from Wikimedia: pause every process. Returns the pause in seconds."""
    return GATE.penalize(retry_after)


def succeeded() -> None:
    """A good reply: after a calm minute, take one strike back."""
    GATE.succeeded()


def status() -> dict:
    return GATE.status()
