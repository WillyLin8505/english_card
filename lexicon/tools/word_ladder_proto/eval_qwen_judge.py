"""RAG + local Qwen as the judge (owner 11/27 「壓縮成 rag 也可以，多嘗試」): for each sense, the program
retrieves each candidate's closest dictionary definition and Qwen only answers which candidates fit.
No Claude / Codex tokens. Scored against the same gold as eval_methods.py.

    python lexicon/tools/word_ladder_proto/eval_qwen_judge.py [N_SENSES] [--prefilter]
"""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_methods as em  # builds rows / gold (prints its own report first)
wl = em.wl

N = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 60
PRE = '--prefilter' in sys.argv
SCHEMA = {'type': 'object', 'properties': {'keep': {'type': 'array', 'items': {'type': 'integer'}}}, 'required': ['keep']}


def best_gloss(x, pos, ss, word):
    mine = wl.content(ss.definition()) | {word[:5]}
    gs = em.glosses(x, pos)
    return max(gs, key=lambda g: len(mine & wl.content(g)), default='')[:90] if gs else ''


by = {}
for key, x, gold, m in em.rows:
    if PRE and not (m['wordnet'] or m['reverse'] or m['wup.8']):
        continue
    by.setdefault(key, []).append((x, gold))
keys = list(by)[:N]
sense_info = {}
for e in em.qwen['entries']:
    for s in e['senses']:
        if s.get('ssid'):
            sense_info[(e['word'], e['pos'], s['ssid'])] = s


def judge(key):
    word, pos, ssid = key
    ss, s = em.W.synset(ssid), sense_info[key]
    lines = '\n'.join(f'{i + 1}. {x}: {best_gloss(x, pos, ss, word)}' for i, (x, _) in enumerate(by[key]))
    prompt = (f'Meaning of the English {pos} "{word}": {ss.definition()}'
              + (f' Example: "{s.get("example")}"' if s.get('example') else '') +
              f'\nCandidates (with their closest dictionary definition):\n{lines}\n'
              f'Which candidates can replace "{word}" in this meaning (same meaning, same part of speech, '
              'a natural sentence still works)? Be strict. Reply with JSON {"keep": [numbers]}.')
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 200,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': SCHEMA}}}
    req = urllib.request.Request(wl.ts().LLAMACPP_URL + '/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    raw = json.load(wl.model_gate.urlopen(req, timeout=300, source='word_ladder'))['choices'][0]['message']['content']
    keep = set(json.loads(raw or '{}').get('keep') or [])
    return [(x, g, (i + 1) in keep) for i, (x, g) in enumerate(by[key])]


wl.ts()
t = time.time()
with ThreadPoolExecutor(4) as pool:
    out = [r for rs in pool.map(judge, keys) for r in rs]
sec = time.time() - t
tp = sum(1 for _, g, k in out if g and k)
fp = sum(1 for _, g, k in out if not g and k)
fn = sum(1 for _, g, k in out if g and not k)
ks = set(keys)
fn = sum(1 for key, x, g, _ in em.rows if key in ks and g) - tp  # gold the prefilter dropped counts as missed
print(f'qwen judge{" +prefilter" if PRE else ""}: {len(keys)} senses, {len(out)} candidates, {sec:.0f}s '
      f'({sec / len(keys):.1f}s/sense) precision {tp / max(tp + fp, 1):.1%} recall {tp / max(tp + fn, 1):.1%}')
