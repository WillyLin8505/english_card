"""Per-picture labelling time, stage by stage (問題回報 #229, owner decision:
keep the full quality pipeline; ≤10 s per picture is a target to measure, not a promise).

  summary   Read lexicon/logs/tag_timing.jsonl (written by images.tag_asset) and print
            the median / p90 of the whole run and of each stage, the tagger's
            queue / prep / prompt / decode split, and how many pictures took ≤10 s.
            Never calls the model.
  run       The small hardware check: at most 3 pictures, stop starting new ones
            after a 120 s budget. Runs the current images.tag_asset in this fresh
            process (so the single-round code is what is measured, not a stale
            worker) and ROLLS BACK — no label in the database changes.
            Refuses unless --authorized (the owner's maintenance window) and
            refuses while Qwen is paused on the board.
            The tagger's own split appears only after tagger/start_tagger.bat
            has restarted the tagger with the card #296 code.

Usage:
  python lexicon/tools/tag_timing_probe.py summary [--last 200]
  python lexicon/tools/tag_timing_probe.py run --authorized [--assets 12,34,56] [--budget 120]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

TARGET_MS = 10_000
MAX_PICTURES = 3
PAUSED_FILE = ROOT / 'state' / 'paused_agents.json'


def _pct(values: list[float], q: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def summarize(lines: list[dict]) -> list[str]:
    if not lines:
        return ['沒有計時紀錄（tag_timing.jsonl 是空的）']
    totals = [l['totalMs'] for l in lines]
    ok = [l for l in lines if l.get('outcome') == 'ok']
    out = [f'圖片 {len(lines)} 張（成功 {len(ok)}）：中位 {statistics.median(totals) / 1000:.1f} 秒、'
           f'p90 {_pct(totals, 0.9) / 1000:.1f} 秒、≤10 秒 {sum(t <= TARGET_MS for t in totals)} 張']
    stage_ms, split = defaultdict(list), defaultdict(list)
    for line in lines:
        per_kind = defaultdict(int)
        for st in line.get('stages') or []:
            per_kind[str(st.get('stage', '?')).split('-')[0]] += st.get('ms') or 0
            for t in st.get('tagger') or []:
                for key in ('queueMs', 'prepMs', 'modelMs', 'promptMs', 'decodeMs'):
                    if isinstance(t.get(key), (int, float)):
                        split[key].append(t[key])
        for kind, ms in per_kind.items():
            stage_ms[kind].append(ms)
    for kind, values in sorted(stage_ms.items(), key=lambda kv: -statistics.median(kv[1])):
        out.append(f'  {kind:<18} 中位 {statistics.median(values) / 1000:6.1f} 秒  '
                   f'p90 {_pct(values, 0.9) / 1000:6.1f} 秒  （{len(values)} 張）')
    if split:
        total = sum(sum(split[k]) for k in ('queueMs', 'prepMs', 'modelMs')) or 1
        out.append('  tagger 分段（全部請求加總）：' + '、'.join(
            f'{k[:-2]} {sum(split[k]) / 1000:.1f} 秒' for k in
            ('queueMs', 'prepMs', 'modelMs', 'promptMs', 'decodeMs') if split[k]))
        if split['decodeMs']:
            out.append(f'  decode 佔 queue+prep+model {sum(split["decodeMs"]) / total:.0%}')
    else:
        out.append('  （沒有 tagger 分段：tagger 還在跑卡 #296 之前的程式）')
    return out


def read_log(path: Path, last: int) -> list[dict]:
    if not path.exists():
        return []
    lines = []
    with open(path, encoding='utf-8') as f:
        for raw in f:
            try:
                lines.append(json.loads(raw))
            except ValueError:
                continue
    return lines[-last:]


def qwen_paused() -> bool:
    try:
        data = json.loads(PAUSED_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and 'Qwen' in data


def run(asset_ids: list[int], budget: float) -> int:
    from sqlalchemy import select
    from app import db, images, models as m
    s = db.SessionLocal()
    started, done = time.monotonic(), []
    try:
        if not asset_ids:
            asset_ids = list(s.execute(
                select(m.ImageAsset.id).where(m.ImageAsset.status == 'ready',
                                              m.ImageAsset.tag_status == 'pending')
                .order_by(m.ImageAsset.id).limit(MAX_PICTURES)).scalars())
        for asset_id in asset_ids[:MAX_PICTURES]:
            if time.monotonic() - started > budget:
                print(f'預算 {budget:.0f} 秒已用完，停止')
                break
            t0 = time.monotonic()
            try:
                images.tag_asset(s, asset_id)
                result = 'ok'
            except Exception as exc:  # noqa: BLE001 — report and continue
                result = f'{type(exc).__name__}: {str(exc)[:120]}'
            print(f'圖片 #{asset_id}：{time.monotonic() - t0:.1f} 秒 {result}')
            done.append(asset_id)
    finally:
        s.rollback()  # measuring only: never keep these labels
        s.close()
    # Workers may log other pictures meanwhile: keep this run's lines only.
    lines = [l for l in read_log(images.TAG_TIMING_LOG, 50) if l.get('asset') in done][-len(done):] \
        if done else []
    print('\n'.join(summarize(lines)))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p_sum = sub.add_parser('summary')
    p_sum.add_argument('--last', type=int, default=200)
    p_run = sub.add_parser('run')
    p_run.add_argument('--authorized', action='store_true',
                       help="the owner's maintenance window: uses the GPU")
    p_run.add_argument('--assets', default='')
    p_run.add_argument('--budget', type=float, default=120)
    args = ap.parse_args(argv)
    if args.cmd == 'summary':
        from app import images
        print('\n'.join(summarize(read_log(images.TAG_TIMING_LOG, args.last))))
        return 0
    if not args.authorized:
        print('拒絕：小樣本 GPU 驗證只在 owner 授權的維護時段執行（加 --authorized）')
        return 2
    if qwen_paused():
        print('拒絕：Qwen 在看板上是暫停狀態；請 owner 先在看板按 ▶ 開始')
        return 2
    ids = [int(x) for x in args.assets.split(',') if x.strip()]
    return run(ids, min(args.budget, 120))


if __name__ == '__main__':
    sys.exit(main())
