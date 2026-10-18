"""Grade every open board card's difficulty (card #156): 1 簡單 · 2 中等 · 3 困難 · 4 極難.

    python lexicon/tools/grade_cards.py --dry-run          # show the grades, change nothing
    python lexicon/tools/grade_cards.py                    # fill cards that have no grade yet
    python lexicon/tools/grade_cards.py --regrade          # re-run the heuristic on every card
    python lexicon/tools/grade_cards.py --set t89=3:"跨模組根因" i231=2:"只加唯讀診斷"

Cards: tasks that aren't done/cancelled (one-off, standing, blocked) and open
問題回報 (bug/todo). A grade set on the board (or with --set) is kept unless
--regrade. Saved through the API (PUT /api/schedule/difficulty via 5173); an
API that doesn't know difficulty yet (not restarted) → straight to the DB with
the backend's own settings (no secret is printed). Also mirrored to
lexicon/state/card_difficulty.json, which pick_card.py reads as a fallback.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_difficulty import LABELS, grade  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:5173/api"
STATE = ROOT / "lexicon" / "state" / "card_difficulty.json"
OPEN_TASK = ("queued", "in_progress", "waiting", "blocked", "scheduled")


def call(method: str, path: str, body: dict | None = None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


def cards() -> list[dict]:
    out = []
    for t in call("GET", "/tasks")["items"]:
        if t["status"] in OPEN_TASK:
            out.append({"key": f"t{t['id']}", "card": "task", **t})
    for r in call("GET", "/issues?status=open")["items"]:
        if r.get("kind") in ("bug", "todo"):
            out.append({"key": f"i{r['id']}", "card": "issue", **r})
    return out


def parse_sets(items: list[str]) -> dict[str, tuple[int, str]]:
    out = {}
    for it in items or []:
        key, _, rest = it.partition("=")
        lvl, _, why = rest.partition(":")
        if not key[:1] in ("t", "i") or not lvl.isdigit() or not 1 <= int(lvl) <= 4:
            sys.exit(f"--set 格式：t89=3:理由 或 i231=2:理由（收到 {it}）")
        out[key] = (int(lvl), f"{LABELS[int(lvl)]}：{why.strip() or '派工者手動設定'}")
    return out


class DB:
    """Direct write for an API that doesn't know difficulty yet."""
    def __init__(self):
        sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
        from app import config  # loads lexicon/.env itself; nothing is printed
        from sqlalchemy import create_engine, text
        self.text = text
        self.engine = create_engine(config.database_url())

    def existing(self) -> dict[str, tuple[int, str]]:
        out = {}
        with self.engine.connect() as c:
            for table, p in (("agent_tasks", "t"), ("issue_reports", "i")):
                for i, d, why in c.execute(self.text(
                        f"SELECT id, difficulty, difficulty_reason FROM {table} WHERE difficulty IS NOT NULL")):
                    out[f"{p}{i}"] = (d, why)
        return out

    def save(self, key: str, lvl: int, why: str):
        table = "agent_tasks" if key[0] == "t" else "issue_reports"
        with self.engine.begin() as c:
            c.execute(self.text(f"UPDATE {table} SET difficulty = :d, difficulty_reason = :w WHERE id = :i"),
                      {"d": lvl, "w": why, "i": int(key[1:])})


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--regrade", action="store_true")
    ap.add_argument("--set", nargs="*", default=[])
    a = ap.parse_args(argv)
    sets = parse_sets(a.set)
    deck = cards()
    api_knows = any("difficulty" in c for c in deck)
    db = None if api_knows else DB()
    have = {c["key"]: (c["difficulty"], c.get("difficulty_reason")) for c in deck if c.get("difficulty")} \
        if api_knows else db.existing()
    state = {}
    dist = {1: 0, 2: 0, 3: 0, 4: 0}
    for c in deck:
        k = c["key"]
        if k in sets:
            lvl, why, src = *sets[k], "set"
        elif k in have and not a.regrade:
            lvl, why, src = *have[k], "kept"
        else:
            lvl, why = grade(c)
            src = "heuristic"
        dist[lvl] += 1
        state[k] = {"difficulty": lvl, "reason": why, "title": (c.get("title") or "")[:80]}
        print(f"{k:>5} {lvl} {src:9} {(c.get('title') or '')[:46]:46} | {why}")
        if a.dry_run or (src == "kept"):
            continue
        if api_knows:
            body = {"difficulty": lvl, "reason": why, "by": "Grokbot",
                    ("task_id" if k[0] == "t" else "issue_id"): int(k[1:])}
            call("PUT", "/schedule/difficulty", body)
        else:
            db.save(k, lvl, why)
    print("分布：" + " · ".join(f"{LABELS[k]} {v}" for k, v in dist.items()), f"（共 {len(deck)} 張）")
    if not a.dry_run:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已存：{'API' if api_knows else '資料庫（API 尚未重啟）'} + {STATE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
