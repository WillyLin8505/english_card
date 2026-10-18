"""Replay frozen real dictionary records against an explicitly limited library.

Run from the repository root with --capture once before editing production code.
The fixture is a test library, not a claim about any real user's collection.
"""
import argparse
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'card_preview'))
from domain import live_exercise

OUT = ROOT / 'lexicon/logs/agents'
FIXTURE = OUT / 'card38.owned-fixture.json'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.capture:
        from repository import Repository
        pack = json.loads((OUT / 'card38.pack-before.json').read_text(encoding='utf-8'))
        names = {'card', 'apple', 'coffee', 'bread', 'knife', 'plate', 'plant', 'leaf', 'flower', 'water'}
        ids = sorted({e['id'] for e in pack['lexemes'] if e['lemma'] in names and e['status'] == 'full'})
        repo = Repository()
        words = [repo.entry(i, 'en', 'zh-TW') for i in ids]
        FIXTURE.write_text(json.dumps({'source': 'live database; fixed ten-word test library',
                                      'owned_ids': ids, 'words': words}, ensure_ascii=False, default=str), encoding='utf-8')
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    owned = set(fixture['owned_ids'])
    kwargs = {'owned_lexeme_ids': owned} if 'owned_lexeme_ids' in inspect.signature(live_exercise).parameters else {}
    totals = {k: dict(attempts=0, available=0, violating_questions=0, unowned_options=0) for k in ('similar', 'photo_choice')}
    examples = []
    for word in fixture['words']:
        for sense in word['senses']:
            for kind, stats in totals.items():
                stats['attempts'] += 1
                result = live_exercise(word, kind, sense['id'], **kwargs)
                if not result['available']:
                    continue
                stats['available'] += 1
                bad = [o['label'] for o in result.get('options', []) if o['id'] not in owned]
                stats['violating_questions'] += bool(bad)
                stats['unowned_options'] += len(bad)
                if bad:
                    examples.append(dict(word=word['lemma'], sense=sense['id'], kind=kind, unowned=bad))
    result = dict(library_size=len(owned), totals=totals, violations=examples)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(totals))


if __name__ == '__main__':
    main()
