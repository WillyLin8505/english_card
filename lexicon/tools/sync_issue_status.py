"""Keep the 問題回報 page honest (owner, 2026-10-21): an issue still 「處理中」 whose cards are all
finished becomes 已修正 with the last card's result; one whose cards were all cancelled goes back
to open so the issue swarm picks it up again. Issues with a live card are left alone.

    python lexicon/tools/sync_issue_status.py [--dry-run]
Run by dispatch_tick every few ticks.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import flow_rules

API = "http://127.0.0.1:5173/api"
LIVE = {"queued", "in_progress", "waiting", "blocked", "scheduled"}


def http(method, path, body=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def start_issue() -> int:
    cfg = Path(__file__).with_name("dispatch_config.json").read_text(encoding="utf-8")
    return int((json.loads(cfg).get("flow") or {}).get("start_issue") or 0)


def plan(issues: list[dict], tasks: list[dict], first_flow_issue: int = 0) -> list[tuple[int, str, str]]:
    """(issue id, new status, resolution) for stale in_progress issues. A new issue fixed by an
    App card stays 處理中 until the iPad passed (flow_tick closes it, card #916)."""
    by_issue: dict[int, list[dict]] = {}
    for t in tasks:
        for i in t.get("issue_ids") or []:
            by_issue.setdefault(i, []).append(t)
    out = []
    for i in issues:
        if i.get("status") != "in_progress":
            continue
        cards = by_issue.get(i["id"], [])
        if not cards or any(t.get("status") in LIVE for t in cards):
            continue
        done = [t for t in cards if t.get("status") == "done"]
        if done:
            last = max(done, key=lambda t: t.get("updated_at") or "")
            if any(flow_rules.holds_issue(i["id"], i.get("area"), t["id"], first_flow_issue) for t in done):
                continue
            out.append((i["id"], "fixed", f"卡 #{last['id']}：{(last.get('progress') or '已完成')[:400]}"))
        else:
            out.append((i["id"], "open", ""))
    return out


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    changes = plan(http("GET", "/issues").get("items", []), http("GET", "/tasks").get("items", []),
                   start_issue())
    for iid, status, res in changes:
        if a.dry_run:
            print(f"DRY #{iid} → {status}")
            continue
        body = {"status": status, "by": "Claude · Manager", "note": "同步：卡片已結束"}
        if res:
            body["resolution"] = res
        try:
            http("PUT", f"/issues/{iid}", body)
        except Exception as e:  # noqa: BLE001
            print(f"#{iid}: {e}")
    if changes:
        print(f"synced {len(changes)} issue(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
