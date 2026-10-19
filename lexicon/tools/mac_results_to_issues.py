"""Every problem the Mac reports becomes a 問題回報 at once (owner, 2026-10-19).

The Mac Claude session writes its iPhone / flutter results to docs/mac_verify_results.md on
GitHub (it may have no API key). dispatch_tick runs this each tick, before the issue swarm, so a
failed row is on the 問題回報 page — and handed to a new Claude CLI — within minutes:

  git fetch → read origin/main:docs/mac_verify_results.md → table rows that report a failure
  (不通過／失敗／錯誤／error／crash／溢出／✕／❌ …, not "0 失敗") → one issue per new row
  ("[Mac] …", reporter "Mac Claude（git）"), remembered by a hash of the row.

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

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "lexicon" / "state" / "mac_results_issues.json"
API = "http://127.0.0.1:5173/api"
RESULTS = "docs/mac_verify_results.md"
FAIL_RE = re.compile(r"不通過|未通過|失敗|錯誤|error|crash|當機|閃退|溢出|overflow|✕|❌|壞掉|打不開|無法", re.I)
NOT_FAIL_RE = re.compile(r"\b0 失敗|0 個失敗|0 error|無 error|No issues found|全部通過|0 failed", re.I)
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
    for section, row in failure_rows(text):
        key = hashlib.sha1(row.encode("utf-8")).hexdigest()[:16]
        if key in state["filed"]:
            continue
        if a.seed:
            state["filed"][key] = "seed"
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        what = next((c for c in cells if c and not re.fullmatch(r"#?\d+", c)), cells[0])
        sev = next((v for k, v in SEVERITY if any(c == k or c.startswith(k + "（") for c in cells)), "medium")
        title = f"[Mac] {section[:40]}：{what[:60]}"
        detail = (f"Mac 端驗證回報（{RESULTS}，自動轉成問題回報）。\n段落：{section}\n列：{row}\n\n"
                  "請在 Windows 重現；若是 iOS／Mac 才有的問題，寫清楚原因與修法。修好後 mac_sync 會再請 Mac 驗證。")
        print(("DRY " if a.dry_run else "") + title)
        if a.dry_run:
            continue
        try:
            i = http("POST", "/issues", {"kind": "bug", "severity": sev, "area": "app", "title": title[:300],
                                         "detail": detail, "reporter": "Mac Claude（git）"})
        except Exception as e:  # noqa: BLE001
            print(f"issue POST failed: {e}")
            return 1
        state["filed"][key] = i.get("id")
        new += 1
    if not a.dry_run or a.seed:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    if new:
        print(f"filed {new} issue(s) from Mac results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
