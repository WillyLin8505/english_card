"""Move cards and 問題回報 through the pipeline (card #916, lexicon/docs/PIPELINE.md).

Run by dispatch_tick every tick, no LLM. Reads what the Mac sees (origin/main: docs/mac_inbox.md,
docs/mac_verify_results.md, docs/releases.md) plus the cards, stores each stage, closes 問題回報
whose App cards passed the iPad, and once a day saves a digest of what needs the owner
(nothing needed → nothing saved).

    python lexicon/tools/flow_tick.py            # once
    python lexicon/tools/flow_tick.py --dry-run  # print the changes
State: lexicon/state/flow_facts.json, daily_digest.json · log: lexicon/logs/flow_tick.log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import flow_rules as fr

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "lexicon" / "state"
FACTS = STATE_DIR / "flow_facts.json"
DIGEST = STATE_DIR / "daily_digest.json"
DIGEST_DIR = ROOT / "lexicon" / "logs" / "daily_digest"
MAC_ISSUES = STATE_DIR / "mac_results_issues.json"
LOG = ROOT / "lexicon" / "logs" / "flow_tick.log"
API = "http://127.0.0.1:5173/api"
TAIPEI = timezone(timedelta(hours=8))
FAIL_QUERY = "flutter test 失敗"
RELEASE_RE = re.compile(r"(?m)^\|\s*(\d+\.\d+\.\d+\S*)\s*\|[^|]*\|\s*`?([0-9a-f]{6,40})`?\s*\|")
DIGEST_HOUR = 9


def log(msg: str):
    line = f"{datetime.now(TAIPEI):%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def http(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=0x08000000 if sys.platform == "win32" else 0)


def on_main(path: str) -> str:
    """The file as the Mac sees it; dispatch_tick's mac_results step fetched origin just before."""
    return git("show", f"origin/main:{path}").stdout or ""


def released_cards(inbox: dict[int, tuple[str, str]], releases: str) -> set[int]:
    """Cards whose verified commit is inside a release listed in docs/releases.md."""
    commits = [c for _, c in RELEASE_RE.findall(releases)]
    if not commits:
        return set()
    out = set()
    for card, (_, commit) in inbox.items():
        if any(git("merge-base", "--is-ancestor", commit, r).returncode == 0 for r in commits):
            out.add(card)
    return out


def cleared_rows(rows: list[fr.Row], filed: dict, by_issue: dict[int, dict]) -> set[str]:
    """Failed rows whose follow-up 問題 (mac_results_to_issues) is finished."""
    out = set()
    for r in rows:
        iid = filed.get(r.key)
        i = by_issue.get(iid) if isinstance(iid, int) else None
        if i and (i.get("status") == "wont_fix" or i.get("stage") in fr.DONE_STAGES):
            out.add(r.key)
    return out


def plan(items: dict, rows: list[fr.Row], pushed: dict, released: set[int], filed: dict, check_failing: bool,
         text_of=fr.result_text) -> tuple[list[dict], list[tuple[dict, str]]]:
    """(stage changes, 問題回報 to close with the reason)."""
    issues = {i["id"]: i for i in items["issues"]}
    cleared = cleared_rows(rows, filed, issues)
    changes, cards_of, closes = [], {}, []
    for t in items["tasks"]:
        linked = [issues[i].get("area") for i in t.get("issue_ids") or [] if i in issues]
        app = t.get("stage") in (*fr.ORDER[1:6],) or (t["status"] == "done" and fr.is_app(text_of(t["id"]), linked))
        mine = [r for r in rows if t["id"] in r.cards]
        stage, state, note = fr.derive_card(t["status"], app, mine, t["id"] in pushed, t["id"] in released,
                                            cleared, check_failing)
        if (stage, state, note) != (t.get("stage"), t.get("stage_state"), t.get("stage_note")):
            changes.append({"type": "task", "id": t["id"], "stage": stage, "state": state, "note": note})
        for iid in t.get("issue_ids") or []:
            cards_of.setdefault(iid, []).append({"id": t["id"], "stage": stage, "state": state, "note": note})
    for i in items["issues"]:
        stage, state, note = fr.derive_issue(i["status"], cards_of.get(i["id"], []))
        if (stage, state, note) != (i.get("stage"), i.get("stage_state"), i.get("stage_note")):
            changes.append({"type": "issue", "id": i["id"], "stage": stage, "state": state, "note": note})
        if i["status"] == "in_progress" and stage in fr.DONE_STAGES and i["id"] in cards_of:
            closes.append((i, f"iPad 驗證通過（{'、'.join('卡 #' + str(c['id']) for c in cards_of[i['id']])}）"
                           if stage != "done" else "卡片完成，不需 Mac 驗證"))
    return changes, closes


def write_digest(now: datetime, lines: list[str], state: dict | None) -> bool:
    """Once a day after DIGEST_HOUR; a day with nothing for the owner leaves no trace."""
    today = now.date().isoformat()
    if now.hour < DIGEST_HOUR or (state or {}).get("checked") == today:
        return False
    out = {"checked": today, "date": (state or {}).get("date"), "lines": (state or {}).get("lines") or []}
    if lines:
        out.update(date=today, lines=lines)
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        (DIGEST_DIR / f"{today}.md").write_text(f"# 每日摘要 {today}：需要你\n\n" + "\n".join(f"- {x}" for x in lines) + "\n",
                                                encoding="utf-8")
    else:
        out.update(date=None, lines=[])
    DIGEST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return bool(lines)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        items = http("GET", "/flow/items")
    except (urllib.error.URLError, OSError, ValueError) as e:  # API down or still on older code
        log(f"skip: /flow/items not available ({e})")
        return 0
    if not items["start"]["task"]:
        return 0
    inbox_text = on_main("docs/mac_inbox.md")
    pushed = fr.parse_inbox(inbox_text)
    rows = fr.parse_results(on_main("docs/mac_verify_results.md"), fr.item_cards(inbox_text))
    released = released_cards(pushed, on_main("docs/releases.md"))
    filed = (json.loads(MAC_ISSUES.read_text(encoding="utf-8")) if MAC_ISSUES.exists() else {}).get("filed", {})
    failing = http("GET", f"/issues?status=active&q={urllib.parse.quote(FAIL_QUERY)}").get("items", [])
    changes, closes = plan(items, rows, pushed, released, filed, bool(failing))
    if a.dry_run:
        for c in changes:
            print("DRY", c["type"], c["id"], c["stage"], c["state"] or "")
        print("DRY close", [i["id"] for i, _ in closes])
        return 0
    if changes:
        http("POST", "/flow/stages", {"items": changes, "by": "flow_tick"})
        log("; ".join(f"{c['type'][0]}{c['id']}→{c['stage']}" + (f"({c['state']})" if c["state"] else "")
                      for c in changes)[:600])
    for i, why in closes:
        http("PUT", f"/issues/{i['id']}", {"status": "fixed", "by": "flow_tick", "resolution": why})
    last = git("log", "-1", "--format=%ct", "origin/main", "--", "docs/mac_verify_results.md").stdout.strip()
    now = datetime.now(TAIPEI)
    tmp = FACTS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"at": now.isoformat(timespec="seconds"), "inbox_todo": fr.inbox_todo(inbox_text),
                               "mac_last_at": int(last) if last.isdigit() else None}, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, FACTS)
    state = json.loads(DIGEST.read_text(encoding="utf-8")) if DIGEST.exists() else None
    if now.hour >= DIGEST_HOUR and (state or {}).get("checked") != now.date().isoformat():
        lines = http("GET", "/flow/overview").get("needs_you") or []
        if write_digest(now, lines, state):
            log(f"daily digest: {len(lines)} item(s) for the owner")
    return 0


if __name__ == "__main__":
    sys.exit(main())
