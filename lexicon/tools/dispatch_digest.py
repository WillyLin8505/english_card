"""Unread dispatcher events in <= ~15 short lines (for Grokbot; zero work otherwise).

    python lexicon/tools/dispatch_digest.py            # print unread events, advance the pointer
    python lexicon/tools/dispatch_digest.py --peek     # print, don't advance
    python lexicon/tools/dispatch_digest.py --all      # no 14-line cap

Reads lexicon/state/dispatch_events.jsonl from the offset saved in
lexicon/state/dispatch_digest.json; last line = what is running / resting now.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "lexicon" / "state"
EVENTS = STATE_DIR / "dispatch_events.jsonl"
POINTER = STATE_DIR / "dispatch_digest.json"
STATE = STATE_DIR / "dispatch_state.json"
TAIPEI = timezone(timedelta(hours=8))
ICON = {"finished": "✔", "dispatched": "▶", "limit": "⛔", "recovered": "↺", "error": "✖",
        "decision": "❓", "blocker": "⚠", "unblocked": "↗"}
CAP = 14


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _hm(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(iso).astimezone(TAIPEI)
    except (TypeError, ValueError):
        return "?"
    return d.strftime("%m/%d %H:%M") if d.date() != datetime.now(TAIPEI).date() else d.strftime("%H:%M")


def fmt(e: dict, width: int = 150) -> str:
    who = e.get("agent", "")
    card = f"#{e['card']}" if e.get("card") else ""
    title = (e.get("title") or "")[:24]
    head = " ".join(x for x in (_hm(e.get("t")), ICON.get(e.get("type"), "·"), card, who) if x)
    body = e.get("outcome") or ""
    if e.get("action") and e.get("type") == "finished":
        body = f"[{e['action']}] {body}"
    line = f"{head} {title}：{body}" if title else f"{head}：{body}"
    return line[:width]


def read_new(offset: int) -> tuple[list[dict], int]:
    if not EVENTS.exists():
        return [], 0
    size = EVENTS.stat().st_size
    if offset > size:
        offset = 0
    out = []
    with EVENTS.open("rb") as f:
        f.seek(offset)
        data = f.read()
    for raw in data.decode("utf-8", "replace").splitlines():
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out, offset + len(data)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--peek", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    ptr = _load(POINTER, {})
    events, end = read_new(int(ptr.get("offset", 0)))
    # keep what matters: drop 'dispatched' if the same card also finished in this batch
    finished = {e.get("card") for e in events if e.get("type") in ("finished", "decision", "blocker")}
    events = [e for e in events if not (e.get("type") == "dispatched" and e.get("card") in finished)]
    if not events:
        print(f"沒有新事件（上次讀到 {_hm(ptr.get('at'))}）")
    else:
        shown = events if a.all or len(events) <= CAP else events[-CAP:]
        if len(shown) < len(events):
            print(f"…較早 {len(events) - len(shown)} 則略過（--all 看全部）")
        for e in shown:
            print(fmt(e))
    st = _load(STATE, {})
    run = "、".join(f"{r['agent']} #{c}" for c, r in (st.get("runs") or {}).items()) or "沒人在跑"
    lim = "、".join(f"{a} 到 {_hm(u)}" for a, u in (st.get("limits") or {}).items())
    print(f"現在：{run}" + (f"｜休息：{lim}" if lim else "") + f"｜最後巡檢 {_hm(st.get('last_tick'))}")
    if not a.peek:
        tmp = POINTER.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"offset": end, "at": datetime.now(TAIPEI).isoformat(timespec="seconds")}),
                       encoding="utf-8")
        os.replace(tmp, POINTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
