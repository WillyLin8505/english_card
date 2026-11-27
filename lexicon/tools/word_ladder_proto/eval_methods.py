"""Owner 11/27 「來源都可以查詢、要的只是單字，多嘗試不同方法」: score cheap, no-LLM ways to keep or drop Qwen's
candidates, against the two reviews of batch 00 (Claude card #1464, Codex card #1466).

gold +  = kept by both reviewers for that sense (matched by WordNet synset id)
gold -  = kept by neither
(one-reviewer words are left out)

    python lexicon/tools/word_ladder_proto/eval_methods.py
"""
import json, os, re, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.stdout.reconfigure(encoding='utf-8')
import word_ladder as wl

D = wl.OUT
qwen = json.load(open(os.path.join(D, 'qwen_batch_00.json'), encoding='utf-8'))
revs = [json.load(open(os.path.join(D, f), encoding='utf-8')) for f in ('checked_batch_00.json', 'checked_batch_00_codex.json')]


def kept(doc):
    out = {}
    for w in doc['words']:
        for s in w.get('senses', []):
            if s.get('ssid'):
                out.setdefault((w['word'], w['pos'], s['ssid']), set()).update(m['w'] for m in s.get('members') or [])
    return out


K = [kept(r) for r in revs]
W = wl.wordnet()
_gl = {}


def glosses(x, pos):
    """Every definition of x in this part of speech: WordNet + Wiktionary (the 'retrieved' context)."""
    if (x, pos) not in _gl:
        g = [s.definition() for p in wl.WNPOS[pos] for s in W.synsets(x, pos=p)]
        g += [r[0] for r in wl.lexdb().execute("""select s.definition from lexemes l join senses s on s.lexeme_id=l.id
              where l.normalized=? and l.pos=?""", (x, wl.KPOS[pos])).fetchall()]
        _gl[(x, pos)] = g
    return _gl[(x, pos)]


def m_wordnet(word, pos, ss, x):
    """Same synset, or a 'similar to' / verb-group neighbour."""
    if x in {l.lower() for l in ss.lemmas()}:
        return True
    near = ss.get_related('similar') + ss.get_related('also') + ss.get_related('verb_group')
    return any(x in {l.lower() for l in n.lemmas()} for n in near)


def m_reverse(word, pos, ss, x):
    """x's own dictionary definitions name the headword or the sense's other lemmas (commence: 'to begin, start')."""
    keys = {word} | {l.lower() for l in ss.lemmas() if ' ' not in l} - {x}
    pat = re.compile(r'\b(' + '|'.join(map(re.escape, keys)) + r')(s|es|ed|d|ing)?\b')
    return any(pat.search(g.lower()) for g in glosses(x, pos))


def m_overlap(word, pos, ss, x):
    """Two content words shared between x's definitions and this sense's definition (Lesk)."""
    mine = wl.content(ss.definition()) - {word[:5]}
    return any(len(mine & wl.content(g)) >= 2 for g in glosses(x, pos))


def m_wup(word, pos, ss, x, th=0.8):
    best = 0
    for p in wl.WNPOS[pos]:
        for s in W.synsets(x, pos=p):
            try:
                best = max(best, wn_sim.wup(ss, s, simulate_root=True))
            except Exception:
                pass
    return best >= th


import wn.similarity as wn_sim  # noqa: E402

METHODS = {'wordnet': m_wordnet, 'reverse': m_reverse, 'overlap': m_overlap, 'wup.8': m_wup}
rows = []
t = time.time()
for e in qwen['entries']:
    for s in e['senses']:
        if not s.get('ssid'):
            continue
        key = (e['word'], e['pos'], s['ssid'])
        if not all(key in k for k in K):
            continue
        ss = W.synset(s['ssid'])
        for c in s['cands']:
            x = c.split('|')[0]
            a, b = (x in K[0][key]), (x in K[1][key])
            if a != b:
                continue
            pos = 'adverb' if '|adv<-' in c else e['pos']
            if pos == 'adverb':
                continue
            rows.append((key, x, a, {n: f(e['word'], e['pos'], ss, x) for n, f in METHODS.items()}))
print(f'{len(rows)} judged candidates ({sum(r[2] for r in rows)} gold +), {time.time() - t:.1f}s')


def report(name, pred):
    tp = sum(1 for r in rows if r[2] and pred(r[3]))
    fp = sum(1 for r in rows if not r[2] and pred(r[3]))
    fn = sum(1 for r in rows if r[2] and not pred(r[3]))
    p = tp / (tp + fp) if tp + fp else 0
    rc = tp / (tp + fn) if tp + fn else 0
    print(f'{name:28s} precision {p:5.1%}  recall {rc:5.1%}  kept {tp + fp}')


report('keep all (Qwen only)', lambda m: True)
for n in METHODS:
    report(n, lambda m, n=n: m[n])
report('wordnet or reverse', lambda m: m['wordnet'] or m['reverse'])
report('wordnet or reverse or wup', lambda m: m['wordnet'] or m['reverse'] or m['wup.8'])
report('any 2 of 4', lambda m: sum(m.values()) >= 2)
report('wordnet or (reverse+overlap)', lambda m: m['wordnet'] or (m['reverse'] and m['overlap']))
