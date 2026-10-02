"""Repeatable read-only learner simulation for the card preview service.

The simulator samples real lexemes, opens their senses through the same HTTP API
as the browser, attempts every exercise type, and checks user-visible invariants.
It never writes FSRS state or dictionary data.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

KINDS = ('cloze', 'photo_choice', 'similar', 'photo_recall', 'drag')


def get(base: str, path: str, **query):
    url = base.rstrip('/') + path
    if query:
        url += '?' + urlencode(query)
    with urlopen(url, timeout=20) as response:
        return json.load(response)


def all_words(base: str, target: str, native: str) -> list[dict]:
    """Read the complete full-word scope through the API's 100-row pages."""
    items = []
    offset = 0
    while True:
        page = get(base, '/api/words', target=target, native=native, scope='full',
                   offset=offset, limit=100)
        items.extend(page['items'])
        offset += len(page['items'])
        if not page['items'] or offset >= page['total']:
            return items


def validate_exercise(word: dict, sense: dict, kind: str, exercise: dict) -> list[str]:
    issues = []
    if exercise.get('kind') != kind:
        issues.append('回傳的題型與請求不一致')
    if exercise.get('sense_id') != sense['id']:
        issues.append('回傳的義項與請求不一致')
    if not exercise.get('available'):
        return issues

    if kind == 'similar':
        options = exercise.get('options') or []
        ids = [item.get('id') for item in options]
        if not 2 <= len(options) <= 4:
            issues.append(f'相似詞情境題實際有 {len(options)} 個選項')
        if len(set(ids)) != len(ids) or len({str(p.get('label', '')).casefold() for p in options}) != len(options):
            issues.append('相似詞情境題出現重複詞條或文字')
        correct_id = exercise.get('correct_id')
        labels = [str(item.get('label', '')).casefold() for item in options]
        # A spelling card can merge several POS lexemes.  The exercise uses the
        # primary lexeme as its canonical correct_id, while ``word['id']`` here
        # may be the usage that owns the selected sense.
        if ids.count(correct_id) != 1 or labels.count(str(word.get('lemma', '')).casefold()) != 1:
            issues.append('相似詞情境題沒有唯一的本題單字')
        if not exercise.get('example') or not exercise.get('prompt'):
            issues.append('相似詞情境題缺少原始例句或遮罩句')
        correct = next((item for item in options if item.get('id') == correct_id), {})
        if str(correct.get('label', '')).casefold() in str(exercise.get('prompt', '')).casefold():
            issues.append('相似詞情境題正面洩漏答案')

    if kind == 'photo_choice':
        options = exercise.get('options') or []
        if len(options) != 3:
            issues.append(f'三選一題型實際有 {len(options)} 個選項')
        ids = [item.get('id') for item in options]
        labels = [str(item.get('label', '')).casefold() for item in options]
        if len(set(ids)) != len(ids) or len(set(labels)) != len(labels):
            issues.append('選項出現重複詞條或文字')
        if ids.count(exercise.get('correct_id')) != 1:
            issues.append('正確答案不是唯一選項')
        # Alternate correct and incorrect choices to exercise both feedback paths.
        chosen = exercise.get('correct_id') if word['id'] % 2 else next((i for i in ids if i != exercise.get('correct_id')), None)
        expected = chosen == exercise.get('correct_id')
        if expected not in (True, False):
            issues.append('無法判定模擬作答結果')

    if kind == 'photo_choice' and not exercise.get('image'):
        issues.append('看圖選單字缺少圖片')
    if kind == 'photo_recall':
        images = exercise.get('images') or []
        if not images:
            issues.append('母語說明＋照片缺少圖片')
        if not str(sense.get('translation') or '').strip():
            issues.append('母語說明＋照片缺少母語提示')
        if any(image.get('sense_id') != sense['id'] for image in images):
            issues.append('母語說明＋照片混入其他義項圖片')
    if kind == 'cloze':
        answer = str(exercise.get('answer', '')).casefold()
        prompt = str(exercise.get('prompt', '')).casefold()
        if answer and answer in prompt:
            issues.append('句子填空正面洩漏答案')
    if kind == 'drag':
        options = exercise.get('options') or []
        if not 1 <= len(options) <= 5:
            issues.append(f'拖曳題型實際有 {len(options)} 個詞籤')
        if not exercise.get('image'):
            issues.append('拖曳題型缺少圖片')
        if len({item.get('id') for item in options}) != len(options):
            issues.append('拖曳題型出現重複詞條')
        for item in options:
            box = item.get('box')
            if (not isinstance(box, list) or len(box) != 4
                    or any(type(value) not in (int, float) for value in box)
                    or min(box) < 0 or box[2] <= 0 or box[3] <= 0
                    or box[0] + box[2] > 1.000001 or box[1] + box[3] > 1.000001):
                issues.append(f"拖曳詞籤 {item.get('label')} 的座標無效")
    return issues


def run(base: str, target: str, native: str, count: int, seed: int) -> dict:
    pool = all_words(base, target, native)
    rng = random.Random(seed)
    sample = rng.sample(pool, min(count, len(pool)))
    availability = defaultdict(Counter)
    cefr_coverage = Counter()
    issues = []
    attempts = 0

    unavailable_reasons = defaultdict(Counter)
    for word_index, summary in enumerate(sample, 1):
        cefr_coverage[summary.get('cefr') or 'unknown'] += 1
        try:
            word = get(base, f"/api/card/{summary['id']}", target=target, native=native)
        except Exception as error:
            issues.append({'lexeme_id': summary['id'], 'lemma': summary['lemma'],
                           'sense_id': None, 'kind': 'card',
                           'message': f'詞條 API 失敗：{type(error).__name__}: {error}'})
            continue
        for sense in word.get('senses', [])[:3]:
            # A card merges every POS usage; exercises run on the usage that owns the sense.
            usage = {**word, 'id': sense.get('lexeme_id', word['id'])}
            for kind in KINDS:
                attempts += 1
                try:
                    exercise = get(base, f"/api/exercise/{usage['id']}", target=target, native=native,
                                   kind=kind, sense=sense['id'])
                except Exception as error:
                    issues.append({'lexeme_id': word['id'], 'lemma': word['lemma'],
                                   'sense_id': sense['id'], 'kind': kind,
                                   'message': f'題目 API 失敗：{type(error).__name__}: {error}'})
                    continue
                availability[kind]['available' if exercise.get('available') else 'unavailable'] += 1
                if not exercise.get('available'):
                    for reason in exercise.get('reasons') or ['未提供原因']:
                        unavailable_reasons[kind][reason] += 1
                for message in validate_exercise(usage, sense, kind, exercise):
                    issues.append({'lexeme_id': word['id'], 'lemma': word['lemma'],
                                   'sense_id': sense['id'], 'kind': kind, 'message': message})
        if word_index % 25 == 0 or word_index == len(sample):
            print(f'progress {word_index}/{len(sample)} words, {attempts} exercises, {len(issues)} issues',
                  file=sys.stderr, flush=True)

    warnings = []
    if not sample:
        warnings.append('這個語言方向沒有可抽樣的完整詞條')
    elif not any(counts.get('available', 0) for counts in availability.values()):
        warnings.append('抽樣詞條的所有題型皆因資料不足而不可作答')
    return {
        'run_at': datetime.now(timezone.utc).isoformat(),
        'base_url': base,
        'target_language': target,
        'native_language': native,
        'seed': seed,
        'sampled_words': len(sample),
        'attempts': attempts,
        'cefr_coverage': dict(cefr_coverage),
        'availability': {kind: dict(counts) for kind, counts in availability.items()},
        'unavailable_reasons': {kind: dict(counts) for kind, counts in unavailable_reasons.items()},
        'warnings': warnings,
        'issues': issues,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8772')
    parser.add_argument('--target', default='en')
    parser.add_argument('--native', default='zh-TW')
    parser.add_argument('--count', type=int, default=30)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'data' / 'simulation-latest.json')
    args = parser.parse_args()
    report = run(args.base_url, args.target, args.native, args.count, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report['issues'] else 0)


if __name__ == '__main__':
    main()
