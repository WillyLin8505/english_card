"""New ladder method (owner 11/27 「單字量還是很少，想想方法是不是最好的」): candidates come from existing
thesauri instead of a small model inventing them, then the program sorts them into senses and levels.

  1. pool   : Moby Thesaurus II (public domain, lexicon/raw-data/moby/mthesaur.txt) + Datamuse means-like
              (cached in raw-data/word_ladder/datamuse_cache.json) + WordNet synset / similar / sibling lemmas
  2. filter : single word, same part of speech (CEFR list, else WordNet), not rare (zipf >= 2.5 or on the
              CEFR list), not an inflection / spelling variant / antonym / offensive word
  3. senses : MiniLM (CPU) cosine between each sense's gloss (+ example) and the candidate's own
              definitions in that part of speech; a candidate goes to its best sense if close enough
  4. levels : word_ladder.level() (CEFR list, else frequency)
No LLM. A reviewer (Sonnet) would then only delete wrong words and write Chinese.

    python lexicon/tools/word_ladder_proto/source_pool.py hope:verb hope:noun period:noun ...
"""
import json, os, re, sys, time, urllib.request
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.stdout.reconfigure(encoding='utf-8')
import word_ladder as wl

MOBY = os.path.join(wl.ROOT, 'lexicon', 'raw-data', 'moby', 'mthesaur.txt')
DM_CACHE = os.path.join(wl.OUT, 'datamuse_cache.json')
M = os.path.join(wl.ROOT, 'lexicon', 'raw-data', 'ls_models', 'minilm')
SIM_MIN = float(os.environ.get('LADDER_SIM_MIN', '0.45'))
DMPOS = {'noun': 'n', 'verb': 'v', 'adjective': 'adj'}

_moby = None


def moby():
    global _moby
    if _moby is None:
        _moby = {}
        if os.path.exists(MOBY):
            for line in open(MOBY, encoding='latin-1'):
                parts = line.rstrip('\n\r').split(',')
                _moby[parts[0].lower()] = parts[1:]
    return _moby


def datamuse(word):
    cache = json.load(open(DM_CACHE, encoding='utf-8')) if os.path.exists(DM_CACHE) else {}
    if word not in cache:
        url = f'https://api.datamuse.com/words?ml={urllib.request.quote(word)}&max=150&md=p'
        cache[word] = json.load(urllib.request.urlopen(url, timeout=20))
        json.dump(cache, open(DM_CACHE, 'w', encoding='utf-8'))
        time.sleep(0.2)
    return cache[word]


def wordnet_pool(word, pos):
    W, out = wl.wordnet(), set()
    for p in wl.WNPOS[pos]:
        for ss in W.synsets(word, pos=p):
            out |= {l.lower() for l in ss.lemmas()}
            for r in ss.get_related('similar') + ss.get_related('also') + ss.hypernyms():
                out |= {l.lower() for l in r.lemmas()}
                if pos == 'verb' and r in ss.hypernyms():  # verb siblings: suppose / guess / imagine
                    for sib in r.hyponyms():
                        out |= {l.lower() for l in sib.lemmas()}
    return out


def pool(word, pos):
    src = {}
    for x in moby().get(word, []):
        src.setdefault(x.lower(), set()).add('moby')
    try:
        for d in datamuse(word):
            if DMPOS[pos] in d.get('tags', []) or (pos == 'adjective' and 'adv' in d.get('tags', [])):
                src.setdefault(d['word'].lower(), set()).add('datamuse')
    except Exception as e:
        print('  datamuse failed', word, e)
    for x in wordnet_pool(word, pos):
        src.setdefault(x, set()).add('wordnet')
    return src


def keep(word, pos, x, antonyms):
    if x == word or not re.fullmatch(r'[a-z]+', x) or x in antonyms:
        return None
    row = wl.row_of(x, pos)
    if not row:
        return None
    if not wl.info(x):  # not on the CEFR list: WordNet must know it in this part of speech, and not rare
        if not any(wl.wordnet().synsets(x, pos=p) for p in (wl.WNPOS.get(row) or ['r'])):
            return None
        if (wl.ts()._wordfreq_zipf(x) or 0) < 2.5:
            return None
    if wl.inflected(x, word, []) or wl.spelling_variant(x, word) or wl.offensive(x):
        return None
    return row


# ---------- MiniLM ----------
_mini = None


def embed(texts):
    global _mini
    if _mini is None:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        o = ort.SessionOptions()
        o.intra_op_num_threads = 4
        _mini = (ort.InferenceSession(os.path.join(M, 'model_quantized.onnx'), o, providers=['CPUExecutionProvider']),
                 Tokenizer.from_file(os.path.join(M, 'tokenizer.json')))
    sess, tok = _mini
    out = []
    for i in range(0, len(texts), 64):
        enc = [tok.encode(t[:300]) for t in texts[i:i + 64]]
        n = max(len(e.ids) for e in enc)
        ids = np.array([e.ids + [0] * (n - len(e.ids)) for e in enc], dtype=np.int64)
        att = np.array([[1] * len(e.ids) + [0] * (n - len(e.ids)) for e in enc], dtype=np.int64)
        feed = {'input_ids': ids, 'attention_mask': att}
        if 'token_type_ids' in [x.name for x in sess.get_inputs()]:
            feed['token_type_ids'] = np.zeros_like(ids)
        h = sess.run(None, feed)[0]
        v = (h * att[..., None]).sum(1) / att.sum(1, keepdims=True)
        out.append(v / np.linalg.norm(v, axis=1, keepdims=True))
    return np.vstack(out) if out else np.zeros((0, 384))


def ladder(word, pos):
    t = time.time()
    senses = [s for s in wl.all_senses(word, pos)[:wl.MAX_QWEN_SENSES]
              if not (s['ss'] and (wl.is_dated(word, pos, s['ss'].definition(), [])
                                   or s['ss'].get_related('instance_hypernym')))]  # people's names
    src = pool(word, pos)
    antonyms = wl.antonyms_of(word, pos)
    cands = {}
    for x, how in src.items():
        if how == {'datamuse'}:  # Datamuse 'means like' alone is too loose (hope -> clown, gem, male)
            continue
        row = keep(word, pos, x, antonyms)
        if row:
            cands[x] = (row, how)
    sv = embed([f"{word}: {s['gloss']}" + (f" e.g. {s['example']}" if s.get('example') else '') for s in senses])
    names, glosses = [], []
    for x, (row, _) in cands.items():
        gs = wl.glosses(x, 'adverb' if row == 'adverb' else pos) if row != 'adverb' else \
            [ss.definition() for ss in wl.wordnet().synsets(x, pos='r')]
        for g in gs[:8]:
            names.append(x)
            glosses.append(f'{x}: {g}')
    gv = embed(glosses)
    best = {}
    if len(gv) and len(sv):
        sims = gv @ sv.T
        for k, x in enumerate(names):
            j = int(sims[k].argmax())
            if x not in best or sims[k, j] > best[x][1]:
                best[x] = (j, float(sims[k, j]))
    lemmas = [({l.lower() for l in s['ss'].lemmas()} if s['ss'] else set()) for s in senses]
    out = [{'gloss': s['gloss'], 'words': []} for s in senses]
    for x, (row, how) in cands.items():
        hit = [j for j, ls in enumerate(lemmas) if x in ls]
        if hit:
            j, sim = hit[0], 1.0
        elif x in best and best[x][1] >= SIM_MIN:
            j, sim = best[x]
        else:
            continue
        out[j]['words'].append({'w': x, 'level': wl.level(x, row), 'row': row, 'sim': round(sim, 2), 'src': sorted(how)})
    for s in out:
        s['words'].sort(key=lambda c: (wl.LV.index(c['level']), -c['sim']))
    return {'word': word, 'pos': pos, 'pool': len(src), 'kept': len(cands), 'seconds': round(time.time() - t, 1),
            'senses': out}


def show(r):
    print(f"\n## {r['word']} {r['pos']}  pool {r['pool']} → kept {r['kept']} → placed "
          f"{sum(len(s['words']) for s in r['senses'])}  ({r['seconds']}s)")
    for s in r['senses']:
        if not s['words']:
            continue
        by = {}
        for c in s['words']:
            by.setdefault(c['level'], []).append(c['w'] + ('·adv' if c['row'] == 'adverb' else ''))
        print(f"  {s['gloss'][:60]}")
        for lv in wl.LV:
            if lv in by:
                print(f"     {lv}: {' '.join(by[lv][:14])}" + (f' …+{len(by[lv]) - 14}' if len(by[lv]) > 14 else ''))


if __name__ == '__main__':
    wl.ts()
    items = [a.split(':') for a in sys.argv[1:]] or [['hope', 'verb'], ['hope', 'noun']]
    res = [ladder(w, p) for w, p in items]
    for r in res:
        show(r)
    json.dump(res, open(os.path.join(wl.OUT, 'source_pool_sample.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
