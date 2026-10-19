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
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from contextlib import contextmanager
from pathlib import Path

from . import config

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


@contextmanager
def _locked():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(STATE.with_suffix(".lock")), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.01)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            try:
                st = json.loads(STATE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                st = {}
            yield st
            tmp = STATE.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(st), encoding="utf-8")
            os.replace(tmp, STATE)
        finally:
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


def _interval(st: dict) -> float:
    return min(MAX_INTERVAL, MIN_INTERVAL * (1 + int(st.get("strikes", 0))))


def wait_turn() -> float:
    """Reserve the next machine-wide slot and sleep until it. Returns seconds waited."""
    now = time.time()
    with _locked() as st:
        slot = max(now, float(st.get("next_at", 0)), float(st.get("pause_until", 0)))
        st["next_at"] = slot + _interval(st)
    wait = slot - now
    if wait > 0:
        time.sleep(wait)
    return wait


def penalize(retry_after: str | float | None = None) -> float:
    """A 429/503 from Wikimedia: pause every process. Returns the pause in seconds."""
    now = time.time()
    try:
        asked = float(retry_after) if retry_after not in (None, "") else 0.0
    except (TypeError, ValueError):
        asked = 0.0
    with _locked() as st:
        paused = float(st.get("pause_until", 0)) > now
        if not paused:  # replies to requests sent before the pause don't escalate it
            st["strikes"] = int(st.get("strikes", 0)) + 1
        pause = min(BACKOFF_MAX, max(asked, BACKOFF_BASE * 2 ** (int(st.get("strikes", 1)) - 1)))
        st["pause_until"] = max(float(st.get("pause_until", 0)), now + pause)
        st["last_limited"] = now
        st["limited_total"] = int(st.get("limited_total", 0)) + 1
        return float(st["pause_until"]) - now


def succeeded() -> None:
    """A good reply: after a calm minute, take one strike back."""
    now = time.time()
    try:  # the common case (no strikes) needs no lock and no write
        if not json.loads(STATE.read_text(encoding="utf-8")).get("strikes"):
            return
    except (OSError, ValueError):
        return
    with _locked() as st:
        if st.get("strikes") and now - float(st.get("last_limited", 0)) > CALM_S:
            st["strikes"] = int(st["strikes"]) - 1
            st["last_limited"] = now  # one strike per calm minute


def status() -> dict:
    with _locked() as st:
        return dict(st, interval=_interval(st))
