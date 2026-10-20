"""Machine-wide request budgets for rate-limited picture sources (問題回報 #360).

問題回報 #339 gave Wikimedia one token schedule shared by every process on the
machine (`wikimedia_gate`).  Smithsonian (api.si.edu, behind api.data.gov) and
Openverse (api.openverse.org) had nothing like it: two image workers plus any
foreground tool each hit the API on their own, every 429 was retried three
times inside the process with sleeps of up to 60 s (Retry-After from
api.data.gov is ~11 h, not seconds), and the next task started over.  With the
public DEMO_KEY (10 requests a day) that made nearly every French task spend
~45–180 s on a source that has delivered 9 pictures in total.

A `Gate` keeps the same token schedule as the Wikimedia one in a small state
file under a file lock, with two differences for sources that are only a
fallback in the picture chain:

- `skip_when_paused`: while the source is in a 429 pause, `wait_turn()` raises
  `Paused` at once instead of sleeping; `images.auto_fetch` logs it and moves
  on to the next source.  Nobody waits 11 hours for the third-choice source.
- long pauses: Retry-After is honoured up to `backoff_max` (a day), so one 429
  pauses the source for every process until the provider's window reopens.

`wikimedia_gate` keeps its own module (and its module-level constants, which
tests monkeypatch); `gate_for(url)` returns whichever gate a URL belongs to.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from contextlib import contextmanager
from pathlib import Path

from . import config

STATE_DIR = Path(os.environ.get("LEXICON_GATE_STATE_DIR", config.HOME / "state"))


class Paused(OSError):
    """The source's shared gate is paused (a 429 someone got); the caller
    should skip this source now instead of waiting.  An OSError so that
    images.auto_fetch's per-source `except` moves on to the next source."""

    def __init__(self, gate: "Gate", seconds: float, http_code: int | None = None):
        self.gate_name = gate.name
        self.seconds = seconds
        self.http_code = http_code
        left = f"{seconds / 60:.0f} 分鐘" if seconds < 5400 else f"{seconds / 3600:.1f} 小時"
        head = f"HTTP Error {http_code}: Too Many Requests；" if http_code else ""
        super().__init__(f"{head}{gate.name} 共用限速閘門暫停中（還有 {left}），略過此來源")


class Gate:
    def __init__(self, name: str, hosts: tuple[str, ...], *, min_interval: float,
                 max_interval: float, backoff_base: float, backoff_max: float,
                 calm_s: float, skip_when_paused: bool = False, state: Path | None = None,
                 timeout_limit: int = 3, timeout_pause: float = 600.0):
        self.name = name
        self.hosts = tuple(h.lower() for h in hosts)
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.calm_s = calm_s
        self.skip_when_paused = skip_when_paused
        self.timeout_limit = timeout_limit
        self.timeout_pause = timeout_pause
        self.state = state or STATE_DIR / f"{name}_gate.json"

    # -- hosts -----------------------------------------------------------
    def matches(self, url: str) -> bool:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in self.hosts)

    # -- state file ------------------------------------------------------
    @contextmanager
    def _locked(self):
        state = Path(self.state)
        state.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(state.with_suffix(".lock")), os.O_RDWR | os.O_CREAT, 0o644)
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
                    st = json.loads(state.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    st = {}
                yield st
                tmp = state.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(json.dumps(st), encoding="utf-8")
                os.replace(tmp, state)
            finally:
                if os.name == "nt":
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)

    def _read(self) -> dict:
        try:
            return json.loads(Path(self.state).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _interval(self, st: dict) -> float:
        return min(self.max_interval, self.min_interval * (1 + int(st.get("strikes", 0))))

    # -- budget ----------------------------------------------------------
    def paused_for(self) -> float:
        """Seconds until the shared pause ends (0 when not paused). No lock."""
        return max(0.0, float(self._read().get("pause_until", 0)) - time.time())

    def wait_turn(self) -> float:
        """Reserve the next machine-wide slot and sleep until it; returns the
        seconds waited.  A skip-when-paused gate raises `Paused` instead of
        waiting out a 429 pause."""
        now = time.time()
        with self._locked() as st:  # (raising inside the block would skip the state write)
            pause_until = float(st.get("pause_until", 0))
            skip = self.skip_when_paused and pause_until > now
            if skip:
                st["skipped_total"] = int(st.get("skipped_total", 0)) + 1
            else:
                slot = max(now, float(st.get("next_at", 0)), pause_until)
                st["next_at"] = slot + self._interval(st)
        if skip:
            raise Paused(self, pause_until - now)
        wait = slot - now
        if wait > 0:
            time.sleep(wait)
        return wait

    def penalize(self, retry_after: str | float | None = None) -> float:
        """A 429/503: pause every process.  Returns the pause in seconds."""
        now = time.time()
        try:
            asked = float(retry_after) if retry_after not in (None, "") else 0.0
        except (TypeError, ValueError):
            asked = 0.0
        with self._locked() as st:
            paused = float(st.get("pause_until", 0)) > now
            if not paused:  # replies to requests sent before the pause don't escalate it
                st["strikes"] = int(st.get("strikes", 0)) + 1
            backoff = self.backoff_base * 2 ** (int(st.get("strikes", 1)) - 1)
            pause = min(self.backoff_max, max(asked, backoff))
            st["pause_until"] = max(float(st.get("pause_until", 0)), now + pause)
            st["last_limited"] = now
            st["limited_total"] = int(st.get("limited_total", 0)) + 1
            return float(st["pause_until"]) - now

    def timed_out(self) -> float:
        """A request that timed out (問題回報 #395): after `timeout_limit`
        in a row (any process) a skip-when-paused source is paused for
        `timeout_pause` seconds, so tasks skip it instead of each waiting out
        its own 25 s timeouts.  Returns the pause started (0 for none)."""
        if not self.skip_when_paused or not self.timeout_limit:
            return 0.0
        now = time.time()
        with self._locked() as st:
            st["timeouts"] = int(st.get("timeouts", 0)) + 1
            st["timeouts_total"] = int(st.get("timeouts_total", 0)) + 1
            if st["timeouts"] < self.timeout_limit:
                return 0.0
            st["timeouts"] = 0
            st["pause_until"] = max(float(st.get("pause_until", 0)), now + self.timeout_pause)
            st["timeout_pauses"] = int(st.get("timeout_pauses", 0)) + 1
            return float(st["pause_until"]) - now

    def succeeded(self) -> None:
        """A good reply: clears the timeout run and, after a calm period,
        takes one strike back."""
        now = time.time()
        st0 = self._read()
        if not st0.get("strikes") and not st0.get("timeouts"):  # the common case: no lock, no write
            return
        with self._locked() as st:
            st["timeouts"] = 0
            if st.get("strikes") and now - float(st.get("last_limited", 0)) > self.calm_s:
                st["strikes"] = int(st["strikes"]) - 1
                st["last_limited"] = now

    def status(self) -> dict:
        with self._locked() as st:
            return dict(st, name=self.name, interval=self._interval(st),
                        paused_for=max(0.0, float(st.get("pause_until", 0)) - time.time()))


# Smithsonian Open Access sits behind api.data.gov: the public DEMO_KEY allows
# 10 requests, a real key 1,000/h; a 429 carries Retry-After in hours.  Only
# the search API counts — ids.si.edu downloads are not metered by the key.
SMITHSONIAN = Gate("smithsonian", ("api.si.edu",), min_interval=4.0, max_interval=60.0,
                   backoff_base=600.0, backoff_max=86400.0, calm_s=600.0, skip_when_paused=True)
# Openverse anonymous: 20/min burst, 200/day sustained (headers measured 2026-10-19).
# With LEXICON_OPENVERSE_CLIENT_ID/SECRET (問題回報 #380, app.openverse_auth)
# a registered client gets 10,000/day: one request a second, shorter first pause.
OPENVERSE_KEYED = bool(config.OPENVERSE_CLIENT_ID and config.OPENVERSE_CLIENT_SECRET)
OPENVERSE = Gate("openverse", ("api.openverse.org",),
                 min_interval=1.0 if OPENVERSE_KEYED else 3.5, max_interval=60.0,
                 backoff_base=60.0 if OPENVERSE_KEYED else 300.0, backoff_max=86400.0,
                 calm_s=600.0, skip_when_paused=True)

GATES: tuple[Gate, ...] = (SMITHSONIAN, OPENVERSE)


def gate_for(url: str):
    """The gate a URL takes its slot from: the Wikimedia one (module
    `wikimedia_gate`, shared with audio downloads), one of `GATES`, or None."""
    from . import wikimedia_gate
    if wikimedia_gate.is_wikimedia(url):
        return wikimedia_gate.GATE
    for gate in GATES:
        if gate.matches(url):
            return gate
    return None


def status_all() -> list[dict]:
    from . import wikimedia_gate
    return [dict(wikimedia_gate.status(), name="wikimedia")] + [g.status() for g in GATES]
