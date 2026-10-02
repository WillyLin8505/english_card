"""Concurrent, read-only learner simulation for the card preview service."""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from simulate_learning import KINDS, all_words, get, validate_exercise


LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')


def timed_get(base: str, path: str, **query):
    started = perf_counter()
    result = get(base, path, **query)
    return result, (perf_counter() - started) * 1000


def learner(user_id: int, base: str, target: str, native: str,
            pool: list[dict], rounds: int, seed: int) -> dict:
    rng = random.Random(f'{seed}:{user_id}')
    preferred_level = LEVELS[user_id % len(LEVELS)]
    preferred = [word for word in pool if word.get('cefr') == preferred_level]
    current = pool.index(rng.choice(preferred or pool))
    latency = []
    failures = []
    issues = []
    actions = Counter()
    kinds = Counter()
    outcomes = Counter()
    levels = Counter()

    try:
        _, elapsed = timed_get(base, '/api/templates', target=target, native=native)
        latency.append(elapsed)
        actions['template_load'] += 1
    except Exception as error:
        failures.append({'user': user_id, 'step': -1, 'action': 'template_load',
                         'message': f'{type(error).__name__}: {error}'})

    for step in range(rounds):
        navigation = ('next', 'previous', 'random')[step % 3]
        if navigation == 'next':
            current = min(current + 1, len(pool) - 1)
        elif navigation == 'previous':
            current = max(current - 1, 0)
        else:
            current = rng.randrange(len(pool))
        actions[navigation] += 1
        summary = pool[current]
        levels[summary.get('cefr') or 'unknown'] += 1
        try:
            word, elapsed = timed_get(base, f"/api/card/{summary['id']}",
                                      target=target, native=native)
            latency.append(elapsed)
        except Exception as error:
            failures.append({'user': user_id, 'step': step, 'action': navigation,
                             'lexeme_id': summary['id'], 'lemma': summary['lemma'],
                             'message': f'{type(error).__name__}: {error}'})
            continue
        senses = word.get('senses') or []
        if not senses:
            failures.append({'user': user_id, 'step': step, 'action': navigation,
                             'lexeme_id': word['id'], 'lemma': word['lemma'],
                             'message': '詞條沒有可切換的義項'})
            continue
        sense = senses[(step + user_id) % min(3, len(senses))]
        kind = KINDS[(step + user_id) % len(KINDS)]
        kinds[kind] += 1
        try:
            exercise, elapsed = timed_get(base, f"/api/exercise/{word['id']}",
                                          target=target, native=native,
                                          kind=kind, sense=sense['id'])
            latency.append(elapsed)
        except Exception as error:
            failures.append({'user': user_id, 'step': step, 'action': kind,
                             'lexeme_id': word['id'], 'lemma': word['lemma'],
                             'sense_id': sense['id'],
                             'message': f'{type(error).__name__}: {error}'})
            continue
        for message in validate_exercise(word, sense, kind, exercise):
            issues.append({'user': user_id, 'step': step, 'lexeme_id': word['id'],
                           'lemma': word['lemma'], 'sense_id': sense['id'],
                           'kind': kind, 'message': message})
        if not exercise.get('available'):
            outcomes['unavailable'] += 1
            continue

        # Alternate the same decisions a learner makes in the browser. These do
        # not write review state; they verify that both paths are representable.
        correct_turn = (step + user_id) % 2 == 0
        if kind == 'cloze':
            chosen = exercise.get('answer') if correct_turn else '__wrong__'
            outcomes['correct' if chosen == exercise.get('answer') else 'wrong'] += 1
        elif kind == 'photo_choice':
            ids = [option['id'] for option in exercise.get('options', [])]
            chosen = exercise.get('correct_id') if correct_turn else next(
                (item for item in ids if item != exercise.get('correct_id')), None)
            outcomes['correct' if chosen == exercise.get('correct_id') else 'wrong'] += 1
        elif kind == 'similar':
            outcomes['correct' if correct_turn else 'wrong_then_correct'] += 1
        elif kind == 'drag':
            outcomes['correct' if correct_turn else 'wrong_then_correct'] += 1
        else:
            outcomes['reveal'] += 1
        actions['flip_to_back'] += 1

    return {'user': user_id, 'preferred_level': preferred_level,
            'actions': dict(actions), 'kinds': dict(kinds),
            'outcomes': dict(outcomes), 'levels': dict(levels),
            'latency_ms': latency, 'failures': failures, 'issues': issues}


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def run(base: str, target: str, native: str, users: int, rounds: int, seed: int) -> dict:
    pool = all_words(base, target, native)
    results = []
    with ThreadPoolExecutor(max_workers=users) as executor:
        futures = [executor.submit(learner, user, base, target, native,
                                   pool, rounds, seed) for user in range(users)]
        for future in as_completed(futures):
            results.append(future.result())
    latency = [value for result in results for value in result['latency_ms']]
    failures = [item for result in results for item in result['failures']]
    issues = [item for result in results for item in result['issues']]
    return {
        'run_at': datetime.now(timezone.utc).isoformat(),
        'base_url': base,
        'target_language': target,
        'native_language': native,
        'seed': seed,
        'users': users,
        'rounds_per_user': rounds,
        'words_in_pool': len(pool),
        'request_count': len(latency),
        'latency_ms': {
            'median': round(percentile(latency, .5), 2),
            'p95': round(percentile(latency, .95), 2),
            'max': round(max(latency, default=0), 2),
        },
        'failures': failures,
        'issues': issues,
        'learners': sorted(results, key=lambda item: item['user']),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8772')
    parser.add_argument('--target', default='en')
    parser.add_argument('--native', default='zh-TW')
    parser.add_argument('--users', type=int, default=8)
    parser.add_argument('--rounds', type=int, default=40)
    parser.add_argument('--seed', type=int, default=9302026)
    parser.add_argument('--output', type=Path,
                        default=Path(__file__).parent / 'data' / 'simulation-concurrent.json')
    args = parser.parse_args()
    if not 1 <= args.users <= 32 or not 1 <= args.rounds <= 1000:
        parser.error('users must be 1–32 and rounds must be 1–1000')
    report = run(args.base_url, args.target, args.native,
                 args.users, args.rounds, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in
                      ('users', 'rounds_per_user', 'words_in_pool', 'request_count',
                       'latency_ms', 'failures', 'issues')}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report['failures'] or report['issues'] else 0)


if __name__ == '__main__':
    main()
