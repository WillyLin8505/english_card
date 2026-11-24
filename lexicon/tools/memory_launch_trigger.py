"""Opens card launches once memory is low (owner 11/24 「監控記憶體，當掉到五十的時候就開卡」).

Checks memory every minute; when it is at or below --threshold (50 %) it writes
lexicon/state/launch_override.json {"until": now + --hours, "reason": ...} and exits.
dispatch_tick then starts new CLIs even outside launch_schedule until "until"; resource_guard
(memory / CPU / GPU over 80 %) still holds new CLIs as before.

Run detached: pythonw lexicon/tools/memory_launch_trigger.py
Log: lexicon/logs/memory_launch_trigger.log
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
OVERRIDE = ROOT / "lexicon" / "state" / "launch_override.json"
LOG = ROOT / "lexicon" / "logs" / "memory_launch_trigger.log"
TAIPEI = timezone(timedelta(hours=8))


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(TAIPEI):%Y-%m-%d %H:%M:%S} {msg}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=50.0)
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--every", type=float, default=60.0)
    a = ap.parse_args(argv)
    log(f"start: waiting for memory <= {a.threshold:.0f}%")
    last_logged = 0.0
    while True:
        pct = psutil.virtual_memory().percent
        if pct <= a.threshold:
            now = datetime.now(TAIPEI)
            OVERRIDE.write_text(json.dumps({
                "until": (now + timedelta(hours=a.hours)).isoformat(timespec="seconds"),
                "reason": f"memory {pct:.0f}% <= {a.threshold:.0f}% (owner 11/24)",
                "set_at": now.isoformat(timespec="seconds"),
            }, ensure_ascii=False), encoding="utf-8")
            log(f"memory {pct:.0f}% → launches open for {a.hours:g} h ({OVERRIDE.name})")
            return 0
        if time.time() - last_logged >= 1800:
            log(f"memory {pct:.0f}%, still waiting")
            last_logged = time.time()
        time.sleep(a.every)


if __name__ == "__main__":
    raise SystemExit(main())
