"""Report your work on the admin's 排程 board (lexicon/backend/app/tasks.py).

    python lexicon/tools/task.py hello --agent "Claude · 英文卡片 UI 設計"   # I'm here (shows on the board)
    python lexicon/tools/task.py next --agent "..." [--pile once|recurring]
        # pull a card: one handed to me, else the top (due standing cards first)
    python lexicon/tools/task.py start "使用者的需求（一行）" --agent "Claude · 英文卡片 UI 設計" [--detail "..."]
    python lexicon/tools/task.py progress 12 "做到哪裡（一行）" --agent "..."
    python lexicon/tools/task.py waiting 12 "要使用者決定什麼" --agent "..."
    python lexicon/tools/task.py done 12 "結果（一行）" --agent "..." [--issues 169,171]
        (a standing card goes back to waiting for its next run)
    python lexicon/tools/task.py take 12 --agent "..."      # a request the owner added on the page
    python lexicon/tools/task.py list                       # unfinished tasks

The API (127.0.0.1:8770) and its key (LEXICON_API_KEY in lexicon/.env) are
read from the environment or lexicon/.env. Prints the task number.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"


def key() -> str:
    if os.environ.get("LEXICON_API_KEY"):
        return os.environ["LEXICON_API_KEY"]
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("LEXICON_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("no LEXICON_API_KEY in the environment or lexicon/.env")


def call(method: str, path: str, body: dict | None = None) -> dict:
    url = os.environ.get("LEXICON_API", "http://127.0.0.1:8770") + path
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "X-API-Key": key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code == 404 and path == "/schedule/claim":
            sys.exit("牌堆是空的，沒有可以接的卡")
        sys.exit(f"{method} {path}: HTTP {e.code} {detail}")
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"排程 API 沒有回應（{url}）：{e}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("hello", "next", "start", "progress", "waiting", "blocked",
                                       "done", "take", "list"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--agent", default=os.environ.get("TASK_AGENT"))
    ap.add_argument("--detail")
    ap.add_argument("--issues", help="related 問題回報 numbers: 169,171")
    ap.add_argument("--pile", choices=("once", "recurring"),
                    help="next: only one-off cards (requests, 問題回報) or only standing cards")
    a = ap.parse_args()
    if a.action == "list":
        for t in call("GET", "/tasks?status=active")["items"]:
            print(f"#{t['id']} [{t['status']}] {t['agent'] or '—'}: {t['title']}"
                  + (f" — {t['progress']}" if t["progress"] else ""))
        return
    if not a.agent:
        sys.exit("--agent is required (e.g. \"Claude · 英文卡片 UI 設計\", \"Codex 桌面版\")")
    issues = [int(n) for n in (a.issues or "").replace("#", "").split(",") if n.strip()]
    if a.action == "hello":
        call("POST", "/agents/hello", {"agent": a.agent, "note": a.args[0] if a.args else None})
        print(f"{a.agent}: 已在排程看板上報到")
        return
    if a.action == "next":
        t = call("POST", "/schedule/claim", {"agent": a.agent, **({"pile": a.pile} if a.pile else {})})
        kind = "常態卡" if t["kind"] == "recurring" else "一次性卡"
        print(f"#{t['id']} {kind}: {t['title']}")
        if t.get("detail"):
            print(t["detail"])
        if t.get("issue_ids"):
            print("問題回報：" + "、".join(f"#{n}" for n in t["issue_ids"]))
        if t.get("last_result"):
            print("上次結果：" + t["last_result"])
        return
    if a.action == "start":
        if not a.args:
            sys.exit("start needs the request as one line")
        t = call("POST", "/tasks", {"title": a.args[0], "detail": a.detail, "requested_by": "owner",
                                    "agent": a.agent, "status": "in_progress", "by": a.agent,
                                    **({"issue_ids": issues} if issues else {})})
    else:
        if not a.args:
            sys.exit(f"{a.action} needs the task number")
        body = {"by": a.agent, "agent": a.agent}
        status = {"progress": "in_progress", "take": "in_progress", "waiting": "waiting",
                  "blocked": "blocked", "done": "done"}[a.action]
        body["status"] = status
        if len(a.args) > 1:
            body["progress"] = a.args[1]
        if issues:
            body["issue_ids"] = issues
        t = call("PUT", f"/tasks/{int(a.args[0].lstrip('#'))}", body)
    print(f"#{t['id']} {t['status']}: {t['title']}")


if __name__ == "__main__":
    main()
