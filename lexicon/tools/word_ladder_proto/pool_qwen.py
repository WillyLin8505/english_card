"""AI-combination test (owner 11/28 「不同的 AI 組合都幫我測試」): local Qwen sorts the same Moby+WordNet pool
(review_batch_93.txt / qwen_batch_93.json) into senses, as Sonnet / Opus / Codex / Cursor do on cards #1899,
#1475-1477. Writes review_batch_93_pool_qwen.tsv in the same TSV format, then word_ladder.apply. Night only.

    python lexicon/tools/word_ladder_proto/pool_qwen.py
"""
import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.stdout.reconfigure(encoding='utf-8')
import word_ladder as wl

D = wl.OUT
text = open(os.path.join(D, 'review_batch_93.txt'), encoding='utf-8').read()
doc = json.load(open(os.path.join(D, 'qwen_batch_93.json'), encoding='utf-8'))
blocks = re.split(r'\n(?=\S+/\S+ [A-C][12]\n)', text.split('\n', 2)[2])
SCHEMA = {'type': 'object', 'properties': {'senses': {'type': 'array', 'items': {'type': 'object', 'properties': {
    'n': {'type': 'integer'}, 'keep': {'type': 'boolean'}, 'zh': {'type': 'string'},
    'words': {'type': 'array', 'maxItems': 15, 'items': {'type': 'string'}}}, 'required': ['n', 'keep', 'zh', 'words']}}},
    'required': ['senses']}


def ask(block):
    head = block.split('\n', 1)[0].split()[0]
    prompt = ('You build a vocabulary ladder. Below is an English word with its numbered meanings and a pool of '
              'candidate words (word:CEFR level).\n' + block +
              '\nFor EACH numbered meaning give: "keep" (false if the meaning is rare, old or technical), "zh" '
              '(Traditional Chinese as used in Taiwan for this meaning), and "words": the pool words that can '
              'replace the word in this meaning (same part of speech). Use as many fitting words as possible, from '
              'easy to hard; you may add common synonyms that are missing. Reply with JSON only.')
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 4000,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': SCHEMA}}}
    req = urllib.request.Request(wl.ts().LLAMACPP_URL + '/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    raw = json.load(wl.model_gate.urlopen(req, timeout=600, source='word_ladder'))['choices'][0]['message']['content']
    rows = []
    try:
        got = wl.ts().loads_salvaging(raw or '{}').get('senses', [])
    except ValueError as e:
        print('  qwen reply unusable', head, e)
        return rows
    for s in got:
        if not s.get('keep'):
            rows.append(f"{head}\t-{s['n']}")
        else:
            rows.append(f"{head}\t{s['n']}\t{s.get('zh', '')}\t" + ' '.join(w.strip().lower() for w in s.get('words', [])
                                                                       if re.fullmatch(r'[A-Za-z]+', w.strip())))
    return rows


if __name__ == '__main__':
    if not (wl.in_night() or '--force-day' in sys.argv):
        sys.exit('Qwen runs only 01:00-07:00 Taipei (owner 11/27)')
    wl.ts()
    t = time.time()
    with ThreadPoolExecutor(4) as pool:
        out = [r for rows in pool.map(ask, blocks) for r in rows]
    sec = time.time() - t
    open(os.path.join(D, 'review_batch_93_pool_qwen.tsv'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    res, missing = wl.apply_review(doc, '\n'.join(out), 'Qwen')
    json.dump(res, open(os.path.join(D, 'checked_batch_93_pool_qwen.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'qwen pool sort: {len(blocks)} words, {sec:.0f}s, not reviewed {missing}')
