"""Hand finished app cards to the Mac for iPhone verification (owner, 2026-10-18).

Every card that changed the Flutter app must be verified on the owner's Mac (iPhone
simulator, and a real iPhone) before it counts. The Mac only sees what is on GitHub, so:

 1. Collect cards finished since the last sync (dispatch_events.jsonl `finished`) whose
    result.md touches the app (app/…, flutter, iOS).
 2. `flutter analyze` (errors only) and `flutter test` on Windows. Failing → nothing is pushed;
    a 問題回報 "[Windows] flutter test 失敗" is opened/updated so the issue swarm fixes it.
 3. Commit the working tree (.gitignore applies), merge origin/main, push.
 4. Add an item M<n> to docs/mac_inbox.md (commit, cards, what to check on the iPhone) and
    push it; mark those issues "待 Mac 驗證" in their resolution.

    python lexicon/tools/mac_sync.py            # one sync (run by dispatch_tick, own lock)
    python lexicon/tools/mac_sync.py --dry-run  # list what would be handed over
State: lexicon/state/mac_sync.json · log: lexicon/logs/mac_sync.log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flutter_check_workspace import check_workspace

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
STATE = ROOT / "lexicon" / "state" / "mac_sync.json"
LOCK = ROOT / "lexicon" / "state" / "mac_sync.lock"
EVENTS = ROOT / "lexicon" / "state" / "dispatch_events.jsonl"
LOG = ROOT / "lexicon" / "logs" / "mac_sync.log"
INBOX = ROOT / "docs" / "mac_inbox.md"
AG_LOGS = ROOT / "lexicon" / "logs" / "agents"
API = "http://127.0.0.1:5173/api"
TAIPEI = timezone(timedelta(hours=8))
APP_RE = re.compile(r"app/|flutter|\.dart\b|iOS|iPhone|畫面|Widget", re.I)
FAIL_TITLE = "[Windows] flutter test 失敗：修好才會推給 Mac 驗證"
FLUTTER = "flutter.bat" if os.name == "nt" else "flutter"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def log(msg: str):
    line = f"{datetime.now(TAIPEI):%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def http(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def sh(*args, cwd=ROOT, timeout=1800) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=NO_WINDOW)


def app_cards(since: str | None) -> list[dict]:
    """Finished one-off cards since `since` whose result touches the app."""
    out, seen = [], set()
    if not EVENTS.exists():
        return out
    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "finished" or e.get("action") not in ("done", "scheduled"):
            continue
        if since and e["t"] <= since:
            continue
        res = ROOT / (e.get("result") or "")
        text = res.read_text(encoding="utf-8", errors="replace") if res.is_file() else e.get("summary", "")
        if not APP_RE.search(text) or e["card"] in seen:
            continue
        seen.add(e["card"])
        out.append(e)
    return out


def checks() -> tuple[bool, str]:
    # Each agent (including simulations) may run Flutter in APP. A retry in that
    # same directory still races its asset cleanup / loaded sqlite3.dll on Windows.
    # A private source copy gives analyze AND the whole test suite their own caches.
    with check_workspace(ROOT) as app:
        a = sh(FLUTTER, "analyze", "--no-fatal-infos", "--no-fatal-warnings", cwd=app, timeout=540)
        if a.returncode != 0:
            return False, "flutter analyze ????\n" + (a.stdout + a.stderr)[-3000:]
        t = sh(FLUTTER, "test", "--reporter=expanded", cwd=app, timeout=540)
        output = (t.stdout + t.stderr).strip()
        if t.returncode != 0:
            # Include pre-test filesystem errors, which have no test [E] line.
            failed = [line for line in output.splitlines() if "[E]" in line]
            return False, "flutter test ???\n" + "\n".join(failed[:15]) + "\n" + output[-3000:]
        return True, output.splitlines()[-1] if output else "flutter test passed"


def report_failure(text: str, cards: list[dict]):
    items = http("GET", "/issues").get("items", [])
    # owner 10/23 (token savings): one issue for every test failure — reopen the latest one,
    # even after it was fixed, instead of opening a new issue (and a new CLI) each time
    open_ = sorted((i for i in items if i.get("title") == FAIL_TITLE), key=lambda i: i["id"], reverse=True)
    detail = (f"mac_sync {datetime.now(TAIPEI):%m/%d %H:%M}：等著推給 Mac 的卡 "
              f"{'、'.join('#' + str(c['card']) for c in cards)}，但 Windows 上檢查沒過，所以沒有 push。\n{text}\n"
              "修到 flutter analyze 無 error、flutter test 全過；不要為了過而刪測試。")
    if open_:
        # reopen so the issue swarm dispatches it again (an in_progress issue whose card is
        # already done would otherwise never be picked up)
        http("PUT", f"/issues/{open_[0]['id']}", {"detail": detail, "status": "open", "by": "mac_sync"})
    else:
        http("POST", "/issues", {"kind": "bug", "severity": "high", "area": "app", "title": FAIL_TITLE,
                                 "detail": detail, "reporter": "mac_sync"})


def next_item_no() -> int:
    text = INBOX.read_text(encoding="utf-8") if INBOX.exists() else ""
    return max([int(n) for n in re.findall(r"^## M(\d+)", text, re.M)] or [0]) + 1


def clean_outcome(text: str) -> str:
    """A result written through a non-UTF-8 shell is all '?' (10/24 #676, Codex): say so
    instead of passing the noise to the Mac."""
    body = (text or "").split("（dispatch_tick")[0]  # the tick's own note is real Chinese
    if body.count("?") >= 12 and not re.search(r"[一-鿿]", body):
        return "（結果檔編碼損壞，看不出內容；請看該卡的 log）"
    return text


def clean_title(c: dict) -> str:
    """Titles that reached the board through a non-UTF-8 shell arrive as '????' (card #376):
    show the result's first sentence instead of unreadable text."""
    t = (c.get("title") or "").strip()
    if len(re.findall(r"[?�]", t)) < 3:
        return t
    out = (c.get("outcome") or "").replace("全部完成：", "").strip()
    return f"問題回報（標題亂碼）：{out[:50]}"


def inbox_item(no: int, commit: str, cards: list[dict], test_line: str) -> str:
    rows = []
    for c in cards:
        rows.append(f"- 卡 #{c['card']}：{clean_title(c)[:70]}\n  結果：{clean_outcome(c.get('outcome') or '')[:160]}")
    return (f"\n## M{no}（{datetime.now(TAIPEI):%Y-%m-%d %H:%M}）狀態：待做\n"
            f"commit `{commit}`（Windows：flutter analyze 無 error、{test_line}）。`git pull` 後在 iPhone 模擬器"
            "逐張驗證下面的卡（owner 10/28：用 owner 的 iPad 驗證，模擬器只做快速檢查；不用 owner 的 iPhone）：照卡上的結果實際操作一次、截圖，"
            "結果寫進 docs/mac_verify_results.md（每張卡一列：通過／不通過＋原因）。"
            "不通過的開 `[Mac]` 問題回報，標題寫卡號。\n" + "\n".join(rows) + "\n")


def mark_issues(cards: list[dict], no: int, commit: str):
    for c in cards:
        try:
            t = http("GET", f"/tasks/{c['card']}")
        except Exception:  # noqa: BLE001
            continue
        for iid in t.get("issue_ids") or []:
            i = http("GET", f"/issues/{iid}")
            note = f"（待 Mac 驗證：docs/mac_inbox.md M{no}，commit {commit}）"
            if note not in (i.get("resolution") or ""):
                http("PUT", f"/issues/{iid}", {"resolution": ((i.get("resolution") or "") + note)[:1500],
                                               "by": "mac_sync"})


def push_non_app() -> int:
    """owner 10/23 「修改完就push」: changes outside app/ (lexicon, server, tools, docs) need no
    flutter checks — commit and push them as they come. app/ still waits for its checks above."""
    changed = [line[3:].strip().strip('"') for line in sh("git", "status", "--porcelain").stdout.splitlines()]
    paths = [p for p in changed if p and not p.startswith(("app/", "lexicon/tmp/"))
             and not ((ROOT / p).is_file() and (ROOT / p).stat().st_size > 50 * 1024 * 1024)]
    if not paths:
        log("no finished app cards since last sync; nothing else to push")
        return 0
    LOCK.write_text(str(os.getpid()))
    try:
        sh("git", "add", "-A", "--", *paths)
        if sh("git", "diff", "--cached", "--quiet").returncode == 0:
            return 0
        r = sh("git", "commit", "-q", "-m", "Windows: lexicon / server / tools changes (mac_sync, no app/ code)")
        if r.returncode != 0:
            log(f"commit failed: {r.stderr[-300:]}")
            return 1
        sh("git", "fetch", "-q", "origin")
        if sh("git", "merge", "-q", "--no-edit", "origin/main").returncode != 0:
            log("merge with origin/main failed (non-app push)")
            sh("git", "merge", "--abort")
            return 1
        p = sh("git", "push", "origin", "main")
        log(f"pushed {len(paths)} non-app path(s)" if p.returncode == 0 else f"push failed: {p.stderr[-300:]}")
        return 0 if p.returncode == 0 else 1
    finally:
        LOCK.unlink(missing_ok=True)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--also", default="", help="extra card ids (e.g. cards launched by hand), comma-separated")
    a = ap.parse_args(argv)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 60 * 60:
        log("another mac_sync is running → skip")
        return 0
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    cards = app_cards(state.get("since"))
    for cid in [int(x) for x in a.also.split(",") if x.strip()]:
        if all(c["card"] != cid for c in cards):
            t = http("GET", f"/tasks/{cid}")
            cards.append({"card": cid, "t": "", "title": t.get("title"), "outcome": (t.get("progress") or "")[:200]})
    if not cards:
        return 0 if a.dry_run else push_non_app()
    log(f"{len(cards)} app card(s) to hand over: {', '.join('#' + str(c['card']) for c in cards)}")
    if a.dry_run:
        return 0
    LOCK.write_text(str(os.getpid()))
    try:
        upto = max([c["t"] for c in cards if c["t"]] or [state.get("since") or ""])
        ok, line = checks()
        if not ok:
            log("checks failed → not pushing app/; reported as an issue")
            report_failure(line, cards)
            # the Mac's inbox and screenshots don't wait for app tests (10/26: #726–#729 shots stuck)
            LOCK.unlink(missing_ok=True)
            push_non_app()
            return 1
        sh("git", "add", "-A")
        # GitHub refuses files over 100 MB and then every later push fails too (10/22: a 327 MB
        # agent scratch pack blocked the Mac for hours) — never commit anything that big
        for p in sh("git", "diff", "--cached", "--name-only").stdout.splitlines():
            f = ROOT / p.strip()
            if f.is_file() and f.stat().st_size > 50 * 1024 * 1024:
                log(f"not committing {p} ({f.stat().st_size // 2**20} MB)")
                sh("git", "reset", "-q", "--", p.strip())
        if sh("git", "diff", "--cached", "--quiet").returncode != 0:
            msg = ("Sync for Mac verification: cards " + ", ".join(f"#{c['card']}" for c in cards)
                   + "\n\nCommitted by lexicon/tools/mac_sync.py after flutter analyze + flutter test passed.")
            r = sh("git", "commit", "-q", "-m", msg)
            if r.returncode != 0:
                log(f"commit failed: {r.stderr[-300:]}")
                return 1
        sh("git", "fetch", "-q", "origin")
        r = sh("git", "merge", "-q", "--no-edit", "origin/main")
        if r.returncode != 0:
            log(f"merge with origin/main failed: {r.stdout[-300:]} {r.stderr[-300:]}")
            sh("git", "merge", "--abort")
            return 1
        commit = sh("git", "rev-parse", "--short", "HEAD").stdout.strip()
        no = next_item_no()
        with INBOX.open("a", encoding="utf-8", newline="\n") as f:
            f.write(inbox_item(no, commit, cards, line))
        sh("git", "commit", "-q", "-m", f"Mac inbox M{no}: verify cards on iPhone", "--", "docs/mac_inbox.md")
        p = sh("git", "push", "origin", "main")
        if p.returncode != 0:
            log(f"push failed: {p.stderr[-300:]}")
            return 1
        mark_issues(cards, no, commit)
        # the web app served by serve_app.py (127.0.0.1:8123 / api.willylinai.com) is a build:
        # rebuild it so the owner sees the same code the Mac verifies (owner 10/19)
        defines = ["--dart-define-from-file=posthog.local.json"] if (APP / "posthog.local.json").exists() else []
        b = sh(FLUTTER, "build", "web", "--release", *defines, cwd=APP, timeout=1500)
        log("web build " + ("OK" if b.returncode == 0 else f"failed: {(b.stdout + b.stderr)[-300:]}"))
        state["since"] = upto
        state["last"] = {"at": datetime.now(TAIPEI).isoformat(timespec="seconds"), "item": f"M{no}",
                         "commit": commit, "cards": [c["card"] for c in cards]}
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"pushed {commit}; inbox M{no} with {len(cards)} card(s)")
        return 0
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
