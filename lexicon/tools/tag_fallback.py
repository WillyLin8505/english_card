"""Photo labelling fallback: Codex / Cursor CLI look at photos when Qwen can't (問題回報 #327, 卡 #330).

    python lexicon/tools/tag_fallback.py status
    python lexicon/tools/tag_fallback.py ask --golden --backend codex --dir D --chunk 0:12
    python lexicon/tools/tag_fallback.py golden --dir D            # Qwen vs fallback, nothing written
    python lexicon/tools/tag_fallback.py run [--force] [--batch 20] # one batch on the live queue

`ask` only calls the CLI (parallel, no database writes) and caches one answer file per
photo in --dir; `apply` / `run` put the answers through the normal label pipeline
(app.vision_fallback.label → images._settle), one picture per transaction under the Qwen
workers' advisory lock, skipping pictures Qwen labelled meanwhile. `run` does nothing
unless tag_fallback_config.json has enabled=true (or --force) AND Qwen is paused or the
queue is at the threshold; it stops at the first usage-limit message (and honours
dispatch_state.json limits). Cost and time per photo: lexicon/logs/tag_fallback/cost.jsonl.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lexicon' / 'backend'))
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402
from app import db, images, models as m, qc, vision_fallback as vf  # noqa: E402

CONFIG = Path(__file__).with_name('tag_fallback_config.json')
LOG_DIR = ROOT / 'lexicon' / 'logs' / 'tag_fallback'
COST_LOG = LOG_DIR / 'cost.jsonl'


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def log_cost(row: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with COST_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def _gaps_after(asset_id: int, backend: str, answers: list[dict]) -> list[str]:
    """CEFR bands still short after these answers (dry run of the pipeline, rolled back)."""
    with db.SessionLocal() as s:
        try:
            asset = s.get(m.ImageAsset, asset_id)
            vf.label(s, asset, answers, backend)
            return images.cefr_gaps(asset.tags or [])
        finally:
            s.rollback()


def ask_photo(asset_id: int, backend: str, cfg: dict, mode: str) -> dict:
    with db.SessionLocal() as s:
        asset = s.get(m.ImageAsset, asset_id)
        path = vf.media_path(asset)
    model = cfg.get(f'{backend}_model')
    kw = dict(model=model, effort=cfg.get('codex_effort', 'low'), timeout=int(cfg.get('timeout_seconds', 300)))
    row = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'mode': mode,
           'asset': asset_id, 'backend': backend, 'rounds': 0, 'seconds': 0.0, 'usage': {}}
    answers = []
    try:
        levels, exclude = list(images.CEFR_LEVELS), []
        for rnd in range(max(1, int(cfg.get('max_rounds', 1)))):
            got = vf.ask(backend, path, vf.build_prompt(levels, exclude, '18-24' if rnd == 0 else '8-12'), **kw)
            answers.append(got)
            row['rounds'] += 1
            row['seconds'] = round(row['seconds'] + got['seconds'], 1)
            for k, v in got['usage'].items():
                row['usage'][k] = row['usage'].get(k, 0) + v
            if got['payload'].get('adult') is True:
                break
            levels = _gaps_after(asset_id, backend, answers)
            if not levels:
                break
            exclude = [str(c.get('word')) for a in answers for c in a['payload'].get('candidates') or []]
        row['ok'] = True
        row['candidates'] = sum(len(a['payload'].get('candidates') or []) for a in answers)
    except vf.QuotaExhausted as e:
        row.update(ok=False, limit=str(e))
    except Exception as e:  # noqa: BLE001 — one photo's failure must not stop the batch
        row.update(ok=False, error=f'{type(e).__name__}: {e}'[:300])
    log_cost(row)
    return {'asset': asset_id, 'backend': backend, 'answers': answers, 'row': row}


def ask_many(ids: list[int], backend: str, cfg: dict, out: Path, mode: str, parallel: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    todo = [i for i in ids if not (out / f'{i}.json').is_file()]
    stats = {'asked': 0, 'ok': 0, 'failed': 0, 'limit': None, 'seconds': 0.0, 'input_tokens': 0,
             'output_tokens': 0}
    if vf.limited(backend):
        stats['limit'] = vf.limited(backend)
        return stats
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        for res in pool.map(lambda i: ask_photo(i, backend, cfg, mode), todo):
            row = res['row']
            stats['asked'] += 1
            stats['seconds'] += row['seconds']
            stats['input_tokens'] += row['usage'].get('input_tokens', 0)
            stats['output_tokens'] += row['usage'].get('output_tokens', 0)
            if row.get('limit'):
                stats['limit'] = row['limit']
                vf.mark_limited(backend, row['limit'])
            if row.get('ok'):
                stats['ok'] += 1
                (out / f'{res["asset"]}.json').write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')
            else:
                stats['failed'] += 1
    stats['seconds'] = round(stats['seconds'], 1)
    return stats


def load_answers(folder: Path) -> dict[int, dict]:
    return {int(p.stem): json.loads(p.read_text(encoding='utf-8')) for p in folder.glob('*.json')
            if p.stem.isdigit()}


def apply_answers(folder: Path) -> dict:
    stats = {'applied': 0, 'skipped_taken': 0, 'blocked': 0, 'errors': 0, 'tags': 0}
    for asset_id, res in sorted(load_answers(folder).items()):
        done_mark = folder / f'{asset_id}.applied'
        if done_mark.exists():
            continue
        with db.session_scope() as s:
            locked = s.scalar(text('SELECT pg_try_advisory_xact_lock(:k, :id)'),
                              {'k': images.TAG_LOCK, 'id': asset_id})
            if not locked or not vf.still_eligible(s, asset_id):
                stats['skipped_taken'] += 1
                done_mark.write_text('skipped', encoding='utf-8')
                continue
            try:
                got = vf.label(s, s.get(m.ImageAsset, asset_id), res['answers'], res['backend'])
            except Exception as e:  # noqa: BLE001
                stats['errors'] += 1
                print(f'  #{asset_id}: {type(e).__name__}: {e}'[:200])
                s.rollback()
                continue
        stats['blocked' if got['blocked'] else 'applied'] += 1
        stats['tags'] += got['passed']
        done_mark.write_text(json.dumps(got, ensure_ascii=False), encoding='utf-8')
    return stats


# ---------------------------------------------------------------- golden comparison

def _photo_stats(pack: dict, ids: set[int]) -> dict:
    sub = {**pack, 'catalog_images': [im for im in pack.get('catalog_images') or [] if im['id'] in ids]}
    golden = qc.load_golden()
    golden = {**golden, 'photos': [p for p in golden['photos'] if p['id'] in ids], 'words': []}
    res = qc.evaluate_golden(sub, golden)
    return {'rates': res['rates'], 'counts': res['counts'],
            'fails': {k: v[:8] for k, v in res['fails'].items()}}


def _tag_stats(s, ids: list[int]) -> dict:
    tags, full_bands, words = 0, 0, {}
    for i in ids:
        a = s.get(m.ImageAsset, i)
        ts = a.tags or []
        tags += len(ts)
        full_bands += sum(1 for n in images.cefr_counts(ts).values() if n >= 3)
        words[i] = {str(t.get('word')).lower() for t in ts}
    return {'labels_per_photo': round(tags / max(1, len(ids)), 1),
            'bands_with_3_per_photo': round(full_bands / max(1, len(ids)), 2), 'words': words}


def golden(folder: Path, out: Path | None, base_file: Path | None = None) -> dict:
    import importlib.util
    import serve_app
    spec = importlib.util.spec_from_file_location('tools_qc', Path(__file__).with_name('qc.py'))
    tools_qc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tools_qc)
    ids = [p['id'] for p in qc.load_golden()['photos']]
    answers = load_answers(folder)
    have = [i for i in ids if i in answers]
    if base_file and base_file.is_file():  # live_pack takes ~9 min; reuse one build per comparison
        base = json.loads(base_file.read_text(encoding='utf-8'))
    else:
        base = tools_qc.build_pack()
        if base_file:
            base_file.write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
    with db.SessionLocal() as s:
        qwen = _tag_stats(s, have)
        try:
            for i in have:
                vf.label(s, s.get(m.ImageAsset, i), answers[i]['answers'], answers[i]['backend'])
            s.flush()
            fb = _tag_stats(s, have)
            _, catalog = serve_app.catalog_snapshot(s, 'en')
        finally:
            s.rollback()
    by_id = {im['id']: im for im in catalog}
    # The compared photos come only from the fallback's catalog (a photo left
    # without approved labels drops out, as it would in the app).
    after = {**base, 'catalog_images': [im for im in base.get('catalog_images') or [] if im['id'] not in set(have)]
             + [by_id[i] for i in have if i in by_id]}
    overlap = [len(qwen['words'][i] & fb['words'][i]) / max(1, len(qwen['words'][i] | fb['words'][i]))
               for i in have]
    report = {'photos_compared': len(have), 'photos_in_golden': len(ids),
              'qwen': {'golden': _photo_stats(base, set(have)), **{k: v for k, v in qwen.items() if k != 'words'}},
              'fallback': {'golden': _photo_stats(after, set(have)), **{k: v for k, v in fb.items() if k != 'words'}},
              'label_overlap_jaccard': round(sum(overlap) / max(1, len(overlap)), 3)}
    if out:
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return report


# ---------------------------------------------------------------- live batch

def run(cfg: dict, force: bool, batch: int | None, backend: str | None) -> dict:
    if not cfg.get('enabled') and not force:
        return {'skipped': 'tag_fallback_config.json enabled=false（golden 比較通過後才開）'}
    with db.SessionLocal() as s:
        why = vf.qwen_busy(s, int(cfg.get('pending_threshold', 200)))
        if not why and not force:
            return {'skipped': 'Qwen 未暫停且佇列低於門檻'}
        ids = vf.pick_batch(s, batch or int(cfg.get('batch', 20)))
    if not ids:
        return {'skipped': '沒有待打標的照片', 'why': why}
    for name in ([backend] if backend else cfg.get('backends', ['codex'])):
        if vf.limited(name):
            continue
        folder = LOG_DIR / 'batches' / f'{datetime.now():%Y%m%d-%H%M%S}-{name}'
        asked = ask_many(ids, name, cfg, folder, 'live', int(cfg.get('parallel', 4)))
        applied = apply_answers(folder)
        return {'why': why, 'backend': name, 'ids': len(ids), 'ask': asked, 'apply': applied,
                'folder': str(folder)}
    return {'skipped': '所有備援額度用完', 'limits': {b: vf.limited(b) for b in vf.BACKENDS}}


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status')
    a = sub.add_parser('ask')
    a.add_argument('--backend', default='codex', choices=sorted(vf.BACKENDS))
    a.add_argument('--dir', required=True)
    a.add_argument('--golden', action='store_true', help='the 50 golden photos')
    a.add_argument('--ids', help='comma-separated asset ids')
    a.add_argument('--chunk', help='start:end slice of the id list (keep each call < 10 min)')
    a.add_argument('--parallel', type=int)
    p = sub.add_parser('apply')
    p.add_argument('--dir', required=True)
    g = sub.add_parser('golden')
    g.add_argument('--dir', required=True)
    g.add_argument('--out')
    g.add_argument('--base', help='cached live pack (built and saved here when missing)')
    r = sub.add_parser('run')
    r.add_argument('--force', action='store_true', help='ignore enabled=false and the queue check')
    r.add_argument('--batch', type=int)
    r.add_argument('--backend', choices=sorted(vf.BACKENDS))
    args = ap.parse_args()
    cfg = load_config()
    if args.cmd == 'status':
        with db.SessionLocal() as s:
            out = {'enabled': cfg.get('enabled'), 'pending': vf.pending_count(s),
                   'threshold': cfg.get('pending_threshold'),
                   'fallback_now': vf.qwen_busy(s, int(cfg.get('pending_threshold', 200))),
                   'limits': {b: vf.limited(b) for b in vf.BACKENDS}}
    elif args.cmd == 'ask':
        ids = [p['id'] for p in qc.load_golden()['photos']] if args.golden else \
            [int(x) for x in (args.ids or '').split(',') if x.strip()]
        if args.chunk:
            lo, hi = (int(x) if x else None for x in args.chunk.split(':'))
            ids = ids[lo:hi]
        t0 = time.time()
        out = ask_many(ids, args.backend, cfg, Path(args.dir), 'golden' if args.golden else 'ask',
                       args.parallel or int(cfg.get('parallel', 4)))
        out['wall_seconds'] = round(time.time() - t0, 1)
    elif args.cmd == 'apply':
        out = apply_answers(Path(args.dir))
    elif args.cmd == 'golden':
        out = golden(Path(args.dir), Path(args.out) if args.out else None,
                     Path(args.base) if args.base else None)
    else:
        out = run(cfg, args.force, args.batch, args.backend)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == '__main__':
    sys.exit(main())
