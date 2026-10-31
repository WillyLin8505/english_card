"""Every problem the Mac reports becomes a 問題回報 at once (owner, 2026-10-19; 注意 rows too, card #918).

The Mac Claude session writes its iPhone / flutter results to docs/mac_verify_results.md on
GitHub (it may have no API key). dispatch_tick runs this each tick, before the issue swarm, so a
failed row is on the 問題回報 page — and handed to a new Claude CLI — within minutes:

  git fetch → read origin/main:docs/mac_verify_results.md → table rows that report a failure
  (不通過／失敗／錯誤／error／crash／溢出／✕／❌ …, not "0 失敗") → one issue per new row
  ("[Mac] …", reporter "Mac Claude（git）"), remembered by a hash of the row. A 注意 row (結果 column)
  becomes a low-severity "[Mac 注意] …" todo unless it only says nothing was verifiable (NOTE_SKIP_RE);
  a row about the same item (cards + first cell) is not filed again while its issue is still active.
  通過 rows need no issue: flow_tick derives the stage from them. Report format: docs/mac_verify.md §報告格式.

    python lexicon/tools/mac_results_to_issues.py            # once
    python lexicon/tools/mac_results_to_issues.py --dry-run  # list rows it would file
State: lexicon/state/mac_results_issues.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flow_rules as fr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "lexicon" / "state" / "mac_results_issues.json"
API = "http://127.0.0.1:5173/api"
RESULTS = "docs/mac_verify_results.md"
FAIL_RE = re.compile(r"不通過|未通過|失敗|錯誤|error|crash|當機|閃退|溢出|overflow|✕|❌|壞掉|打不開|無法", re.I)
NOT_FAIL_RE = re.compile(r"\b0 失敗|0 個失敗|0 error|無 error|No issues found|全部通過|0 failed", re.I)
# 注意 rows that carry nothing to fix: waiting for a later round, owner already chose "leave it"
NOTE_SKIP_RE = re.compile(r"等下一輪|還沒在|尚未在|沒有畫面可驗|不用再量|不用再|owner.{0,12}選 ?[ABC]|已決定|預期值")
SEVERITY = (("高", "high"), ("中", "medium"), ("低", "low"))


def sh(*args) -> str:
    r = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=0x08000000 if sys.platform == "win32" else 0)
    return r.stdout or ""


def http(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def failure_rows(text: str) -> list[tuple[str, str]]:
    """(section heading, row) for each table row that reports a problem. The columns to read
    come from the table's header: 實際 / 結果 / 原因 / 嚴重度 (not 預期 or the step name)."""
    out, section, cols = [], "", None
    for line in text.splitlines():
        if line.startswith("## "):
            section, cols = line[3:].strip(), None
            continue
        if not line.startswith("|"):
            cols = None
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cols is None:  # header row
            cols = [i for i, c in enumerate(cells) if c in ("實際", "結果", "原因", "嚴重度", "狀態")]
            continue
        result = " ".join(cells[i] for i in cols if i < len(cells))
        if re.search(r"不通過|未通過", result) or (FAIL_RE.search(result) and not NOT_FAIL_RE.search(result)):
            out.append((section, line.strip()))
    return out


def note_rows(text: str) -> list[tuple[str, str]]:
    """(section, row) for each 注意 row of a table with a 結果 column that is worth a card.
    Card numbers are not required (a new Mac finding has none yet)."""
    out, section, at = [], "", None
    for line in text.splitlines():
        if line.startswith("## "):
            section, at = line[3:].strip(), None
        elif not line.startswith("|"):
            at = None
        elif set(line.replace("|", "").strip()) <= set("-: "):
            continue
        else:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if at is None:
                at = cells.index("結果") if "結果" in cells else -1
            elif 0 <= at < len(cells) and fr._verdict(cells[at]) == "note" and not NOTE_SKIP_RE.search(line):
                out.append((section, line.strip()))
    return out


def item_key(row: str) -> str:
    """Same item = same first cell (card numbers / step name), whatever the verdict text says."""
    first = row.strip().strip("|").split("|")[0].strip()
    return "item:" + hashlib.sha1(first.encode("utf-8")).hexdigest()[:12]


def still_active(issue_id) -> bool:
    if not isinstance(issue_id, int):
        return False
    try:
        return http("GET", f"/issues/{issue_id}").get("status") in ("open", "in_progress", "needs_decision")
    except Exception:  # noqa: BLE001
        return True


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", action="store_true", help="mark every current failure row as already handled")
    a = ap.parse_args(argv)
    sh("git", "fetch", "-q", "origin")
    text = sh("git", "show", f"origin/main:{RESULTS}")
    if not text:
        return 0
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"filed": {}}
    new = 0
    todo = [("fail", sec, row) for sec, row in failure_rows(text)]
    todo += [("note", sec, row) for sec, row in note_rows(text)]
    for kind, section, row in todo:
        key = hashlib.sha1(row.encode("utf-8")).hexdigest()[:16]
        if key in state["filed"]:
            continue
        if a.seed:
            state["filed"][key] = "seed"
            continue
        ikey = item_key(row)
        if still_active(state["filed"].get(ikey)):  # same item already has an open issue
            state["filed"][key] = state["filed"][ikey]
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        what = next((c for c in cells if c and not re.fullmatch(r"#?\d+", c)), cells[0])
        sev = next((v for k, v in SEVERITY if any(c == k or c.startswith(k + "（") for c in cells)), "medium")
        note = kind == "note"
        if note:
            sev = "low"
        title = f"[Mac{' 注意' if note else ''}] {section[:40]}：{what[:60]}"
        detail = (f"Mac 端驗證回報（{RESULTS}，自動轉成問題回報）。\n段落：{section}\n列：{row}\n\n"
                  + ("Mac 標了「注意」：結果不是壞掉，但有值得處理的發現。請在 Windows 判斷要不要修；"
                     "不需要就在問題回報寫理由後標不處理。" if note else
                     "請在 Windows 重現；若是 iOS／Mac 才有的問題，寫清楚原因與修法。修好後 mac_sync 會再請 Mac 驗證。"))
        print(("DRY " if a.dry_run else "") + title)
        if a.dry_run:
            continue
        try:
            i = http("POST", "/issues", {"kind": "todo" if note else "bug", "severity": sev, "area": "app",
                                         "title": title[:300], "detail": detail, "reporter": "Mac Claude（git）"})
        except Exception as e:  # noqa: BLE001
            print(f"issue POST failed: {e}")
            return 1
        state["filed"][key] = i.get("id")
        state["filed"][ikey] = i.get("id")
        new += 1
    if not a.dry_run or a.seed:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    if new:
        print(f"filed {new} issue(s) from Mac results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
