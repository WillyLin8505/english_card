"""`qc` command: fix -> guard -> keep or auto-rollback (QUALITY P3).

    python lexicon/tools/qc.py run [--trigger import|tagging|pack|manual] [--dry-run] [--no-issues]
    python lexicon/tools/qc.py rollback RUN_ID
    python lexicon/tools/qc.py runs            # recent runs with change counts
    python lexicon/tools/qc.py check --pack URL_OR_FILE --out snapshot.json [--before snapshot.json]
    python lexicon/tools/qc.py check --live --out snapshot.json [--before snapshot.json]
                                # --live includes catalog_images (photo golden/QC); needs DB access

`run` builds the live pack in-process (same code as 8123 /api/lexicon),
snapshots metrics + golden set, applies the deterministic fixers in one
transaction, rebuilds, compares; any regression rolls the run back.
Remaining violations are filed as one local issue per rule.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QC_RUNNING", "1")  # hooks must not re-trigger from inside a run

from app import qc  # noqa: E402

OUT = ROOT / "lexicon" / "exports" / "quality" / "qc"
ISSUES = os.environ.get("QC_ISSUES_URL", "http://127.0.0.1:5173/api/issues")


def build_pack() -> dict:
    import serve_app
    serve_app._cache.clear()
    body, _ = serve_app.live_pack("en", "zh-TW")
    return json.loads(body)


def _req(method, url, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


RULE_TITLES = {
    "sense.main_without_chinese": "主義項沒有中文",
    "sense.main_is_ai": "主義項中文只有 AI 翻譯",
    "sense.native_empty": "義項沒有中文（不限主義項）",
    "sense.native_has_latin": "義項中文夾雜拉丁字母／殘字",
    "photo.fewer_than_3_tags": "照片標籤少於 3 個",
    "photo_tag.sense_low_priority": "照片標籤只剩低優先義項",
    "photo_tag.sense_without_chinese": "照片標籤義項沒有中文",
    "entry.full_without_senses": "完整詞條沒有義項",
    "entry.pos_unknown": "詞性 unknown",
    "pronunciation.ipa_is_arpabet": "IPA 欄位混進 ARPAbet",
    "entry.full_without_ipa": "完整詞條沒有 IPA",
    "entry.full_without_audio": "完整詞條沒有音檔",
}


def file_issues(violations: dict, run_id: str) -> list:
    """One issue per rule: create once, then update count; 0 -> fixed."""
    from app import qc_fix
    try:
        listing = _req("GET", ISSUES + "?limit=1000")
    except Exception as e:  # issue page down: skip, never fail the run
        return [f"issues unavailable: {type(e).__name__}"]
    items = listing if isinstance(listing, list) else listing.get("items") or listing.get("issues") or []
    by_title = {i.get("title", ""): i for i in items}
    done = []
    rules = set(violations) | {r for r in RULE_TITLES}
    for rule in sorted(rules):
        n = len(violations.get(rule, []))
        policy = qc_fix.POLICY.get(rule, "human")
        title = f"[qc] {rule}：{RULE_TITLES.get(rule, rule)}"
        existing = next((i for t, i in by_title.items() if t.startswith(f"[qc] {rule}：")), None)
        sample = json.dumps(violations.get(rule, [])[:15], ensure_ascii=False)
        note = f"qc run {run_id}：{n} 筆（處理方式：{policy}）。樣本：{sample}"
        if existing is None:
            if n == 0:
                continue
            created = _req("POST", ISSUES, {
                "kind": "bug", "status": "open", "severity": "medium", "area": "data", "title": title[:300],
                "detail": f"由 qc 自動彙整（規則 {rule}，每條規則一張，不逐字）。處理方式：{policy}。",
                "reporter": "qc-bot", "note": note})
            done.append((created.get("id"), rule, n, "created"))
        else:
            body = {"note": note, "reporter": "qc-bot", "title": title[:300]}
            if n == 0 and existing.get("status") != "fixed":
                body["status"] = "fixed"
            elif n and existing.get("status") == "fixed":
                body["status"] = "open"
            _req("PUT", f"{ISSUES}/{existing['id']}", body)
            done.append((existing["id"], rule, n, body.get("status", existing.get("status"))))
    return done


def run(trigger: str, dry_run: bool, issues: bool) -> int:
    from app import db, qc_fix
    OUT.mkdir(parents=True, exist_ok=True)
    run_id = qc_fix.new_run_id(trigger)
    t0 = time.time()
    golden = qc.load_golden()
    before_pack = build_pack()
    before = qc.snapshot(before_pack, golden)
    violations = qc.validate(before_pack)
    with db.session_scope() as s:
        applied = qc_fix.apply_fixers(s, run_id, before_pack, violations)
        if dry_run:
            s.rollback()
    if dry_run:
        print(json.dumps({"run_id": run_id, "dry_run": applied}, ensure_ascii=False, indent=1))
        return 0
    after_pack = build_pack()
    after = qc.snapshot(after_pack, golden)
    bad = qc.compare(before, after)
    rolled = 0
    if bad:
        with db.session_scope() as s:
            rolled = qc_fix.rollback(s, run_id)
    final = qc.validate(after_pack if not bad else before_pack)
    report = {"run_id": run_id, "trigger": trigger, "seconds": round(time.time() - t0, 1),
              "applied": applied, "regressions": bad, "rolled_back": rolled,
              "metrics_before": before["metrics"], "metrics_after": after["metrics"],
              "golden_before": before["golden"]["rates"], "golden_after": after["golden"]["rates"],
              "remaining": qc_fix.remaining_by_policy(final)}
    if issues:
        report["issues"] = file_issues(final, run_id)
    (OUT / f"run-{run_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if bad else 0


def check_pack(source: str | None, out: str, before: str | None, live: bool) -> int:
    """Read-only golden/QC guard, also usable without database credentials.

    `--live` builds the pack in-process (same as `run`, via serve_app.live_pack)
    instead of reading a URL/file; it is the only way to get `catalog_images` for
    the photo golden checks, since plain exports and the admin API don't include
    them. Needs DB access, same as `run` does.
    """
    if live:
        pack = build_pack()
    elif source.startswith(('http://', 'https://')):
        with urllib.request.urlopen(source, timeout=120) as response:
            pack = json.load(response)
    else:
        pack = json.loads(Path(source).read_text(encoding='utf-8'))
    snapshot = qc.snapshot(pack, qc.load_golden())
    if live:
        # Values vs lexemes drift is only visible in the database (#281).
        from app import db, qc_drift
        with db.session_scope() as s:
            counts, samples = qc_drift.metrics(s)
        snapshot["metrics"].update(counts)
        snapshot["samples"].update(samples)
    bad = qc.compare(json.loads(Path(before).read_text(encoding='utf-8')), snapshot) if before else []
    Path(out).write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'metrics': snapshot['metrics'], 'golden': snapshot['golden']['rates'],
                      'regressions': bad}, ensure_ascii=False, indent=1))
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="qc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--trigger", default="manual")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-issues", action="store_true")
    rb = sub.add_parser("rollback")
    rb.add_argument("run_id")
    sub.add_parser("runs")
    check = sub.add_parser('check', help='read-only metrics and golden set; no fixers')
    check.add_argument('--pack', help='URL or file; omit with --live')
    check.add_argument('--live', action='store_true',
                        help='build the pack in-process (needs DB access) instead of '
                        'reading --pack; the only way to include catalog_images, so use '
                        'this for photo golden/QC checks')
    check.add_argument('--out', required=True)
    check.add_argument('--before')
    a = ap.parse_args(argv)
    if a.cmd == 'check':
        if not a.live and not a.pack:
            ap.error('check requires --pack or --live')
        return check_pack(a.pack, a.out, a.before, a.live)
    if a.cmd == "run":
        return run(a.trigger, a.dry_run, not a.no_issues)
    from app import db, qc_fix
    with db.session_scope() as s:
        qc_fix.ensure_schema(s)
        if a.cmd == "rollback":
            print("rolled back", qc_fix.rollback(s, a.run_id), "changes of", a.run_id)
        else:
            from sqlalchemy import text
            for row in s.execute(text(
                    "SELECT run_id, rule, status, count(*) FROM qc_changes GROUP BY 1,2,3 ORDER BY 1 DESC, 2 LIMIT 60")):
                print(*row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
