"""Card #731 / issue #872: one heavy job at a time on this PC (qc check --live, flutter test, full
exports, card*_measure scans). The OS lock dies with the process, so a crash never blocks the next.

    python lexicon/tools/heavy_lock.py run -- flutter test      # waits for its turn, then runs it
    from heavy_lock import slot; slot()                         # inside a script: wait, hold until exit
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "state" / "heavy.lock"
ENV = "HEAVY_LOCK_HELD"  # children of a holder skip the lock (else qc inside `run` would deadlock)
_FH = None


def _try(fh) -> bool:
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def slot(timeout_s: float = 3000.0) -> bool:
    """Wait for the heavy-job slot; keep it until this process exits. False = gave up waiting
    (the caller runs anyway rather than hang a card)."""
    global _FH
    if os.environ.get(ENV) or _FH is not None:
        return True
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    _FH = open(LOCK, "a+")
    end = time.time() + timeout_s
    while not _try(_FH):
        if time.time() > end:
            return False
        time.sleep(5)
    os.environ[ENV] = "1"
    return True


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "run":
        print(__doc__)
        return 2
    cmd = argv[1:]
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    slot()
    return subprocess.call(cmd, shell=(os.name == "nt"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
