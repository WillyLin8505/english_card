"""Best card for an AI right now (card #156): difficulty within its ability, highest priority first.

    python lexicon/tools/pick_card.py --agent "Cursor CLI"            # prints: <key> <level> <title>
    python lexicon/tools/pick_card.py --agent Codex --all             # every eligible card, ranked
    python lexicon/tools/pick_card.py --agent "Cursor CLI" --json
    python lexicon/tools/pick_card.py --agent "Cursor CLI" --claim    # also claim it on the board

Rules (lexicon/tools/agent_capabilities.json):
* only cards whose difficulty <= the agent's max_difficulty; Qwen / Grokbot take none;
* night-only cards (`night_only_tasks`, Qwen-heavy) only inside `night_window`
  (default 01:00–07:00 Asia/Taipei); `--check-task N` exits 6 outside it;
* never a card another AI holds (the deck only lists free cards), never a
  blocked card, never the skip lists (#27; 問題回報 #192, #202–206);
* order: a card the owner handed to this agent → owner's one-off requests →
  問題回報 by severity → due standing cards; inside the same rank, cards in the
  agent's preferred band (>= prefer_min_difficulty, e.g. Claude takes hard
  cards first) come first, then harder before easier.
Difficulty: the board's value, else lexicon/state/card_difficulty.json
(grade_cards.py), else the heuristic in card_difficulty.py.
Exit codes: 0 found · 3 nothing eligible · 4 agent paused · 5 unknown agent · 6 night-only card outside the night window.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_difficulty import LABELS, agent_profile, eligible, grade, load_capabilities  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:5173/api"
STATE = ROOT / "lexicon" / "state" / "card_difficulty.json"
SEV = {"high": 0, "medium": 1, "low": 2}
TAIPEI = timezone(timedelta(hours=8))


def is_night(caps: dict, now: datetime | None = None) -> bool:
    """Inside the night window (Asia/Taipei)? Window may wrap midnight (e.g. 23:00–06:00)."""
    w = caps.get("night_window") or {}
    start, end = w.get("start", "01:00"), w.get("end", "07:00")
    hm = (now or datetime.now(TAIPEI)).astimezone(TAIPEI).strftime("%H:%M")
    return start <= hm < end if start <= end else (hm >= start or hm < end)


def night_blocked(caps: dict, task_id, now: datetime | None = None) -> bool:
    """A night-only (Qwen-heavy) card asked for outside the night window."""
    return task_id in set(caps.get("night_only_tasks", [])) and not is_night(caps, now)


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path: str, body: dict):
    req = urllib.request.Request(API + path, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def candidates(board: dict, agent: str, caps: dict, state: dict | None = None,
               now: datetime | None = None) -> list[dict]:
    """Eligible cards for `agent`, best first. Pure: testable without the API."""
    state = _state() if state is None else state
    _, prof = agent_profile(caps, agent)
    skip_t = set(caps.get("skip_tasks", []))
    skip_i = set(caps.get("skip_issues", []))
    mine = []
    for b in board.get("bots", []):
        if b.get("agent") == agent:
            mine = [{"card": "task", **t, "_assigned": True} for t in b.get("assigned", [])]
    out = []
    for order, c in enumerate(mine + list(board.get("deck", []))):
        is_task = c.get("card") == "task"
        key = f"t{c['id']}" if is_task else f"i{c['issue_id']}"
        if (is_task and c["id"] in skip_t) or (not is_task and c["issue_id"] in skip_i):
            continue
        if is_task and night_blocked(caps, c["id"], now):
            continue
        if is_task and (c.get("status") == "blocked" or (c.get("agent") and c.get("agent") != agent)):
            continue
        if not is_task and c.get("kind") not in ("bug", "todo"):
            continue
        if c.get("difficulty"):
            lvl, why, src = c["difficulty"], c.get("difficulty_reason") or "", "board"
        elif key in state:
            lvl, why, src = state[key]["difficulty"], state[key].get("reason", ""), "graded"
        else:
            (lvl, why), src = grade(c), "heuristic"
        if not eligible(lvl, prof):
            continue
        if c.get("_assigned"):
            pile = 0
        elif is_task and c.get("kind") != "recurring":
            pile = 1
        elif not is_task:
            pile = 2 + SEV.get(c.get("severity"), 1) / 10
        else:
            pile = 3
        band = 0 if lvl >= int(prof.get("prefer_min_difficulty", 1)) else 1
        out.append({"key": key, "task_id": c.get("id") if is_task else None,
                    "issue_id": None if is_task else c["issue_id"], "difficulty": lvl,
                    "label": LABELS[lvl], "reason": why, "source": src,
                    "title": c.get("title"), "kind": c.get("kind"), "severity": c.get("severity"),
                    "_rank": (pile, band, -lvl, order)})
    out.sort(key=lambda x: x["_rank"])
    for x in out:
        x.pop("_rank")
    return out


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent", required=True)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--claim", action="store_true", help="claim the best card for the agent (POST /schedule/claim)")
    ap.add_argument("--check-task", type=int, help="exit 6 if this card is night-only and it is not night now")
    a = ap.parse_args(argv)
    caps = load_capabilities()
    if a.check_task is not None and night_blocked(caps, a.check_task):
        w = caps.get("night_window") or {}
        print(f"#{a.check_task} 只在夜間 {w.get('start', '01:00')}–{w.get('end', '07:00')}（台北）派工，現在不派")
        return 6
    name, prof = agent_profile(caps, a.agent)
    if not prof:
        print(f"不認得的 AI：{a.agent}（agent_capabilities.json 沒有對應的 match）")
        return 5
    if prof.get("dispatchable") is False:
        print(f"{a.agent} 不接看板卡（{'、'.join(prof.get('strengths', []))}）")
        return 3
    board = get("/schedule/board")
    if any(b.get("agent") == a.agent and b.get("paused") for b in board.get("bots", [])):
        print(f"{a.agent} 在看板上是暫停中，不派卡")
        return 4
    got = candidates(board, a.agent, caps)
    if not got:
        print(f"沒有 {a.agent} 能接的卡（上限 {LABELS.get(prof.get('max_difficulty'), prof.get('max_difficulty'))}）")
        return 3
    shown = got if a.all else got[:1]
    if a.json:
        print(json.dumps(shown, ensure_ascii=False, indent=1))
    else:
        for x in shown:
            print(f"{x['key']} {x['difficulty']}({x['label']}) {x['title'][:70]} | {x['reason']} [{x['source']}]")
    if a.claim:
        best = got[0]
        body = {"agent": a.agent, **({"task_id": best["task_id"]} if best["task_id"] else {"issue_id": best["issue_id"]})}
        t = post("/schedule/claim", body)
        print(f"CLAIMED #{t['id']} → {a.agent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
