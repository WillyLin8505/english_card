"""Round 3: sense list = WordNet's first 4 (roughly by frequency) + Wiktionary's first 4
(non-dated), merged when they match; Claude decides which senses a learner meets. Stricter
filter for academic words on the hard side (frequency >= 2.5, -ology/-ism/... endings)."""
import os, sys
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ladder21.py'), encoding='utf-8').read()
exec(_src[:_src.index('\nby = {p:')])

OLDTAG = ('dated', 'obsolete')  # archaic: Qwen decides (Wiktionary marks 'political party' archaic)
ACADEMIC = re.compile(r'(ology|ism|ity|ization|isation|ics|oid|ive)$')


def sense_list(word, pos):
    wn_ss = [s for x in WNPOS[pos] for s in W.synsets(word, pos=x)][:4]
    out = [{'gloss': s.definition(), 'example': (s.examples() or [''])[0], 'archaic': False, 'ss': s, 'src': 'WN'}
           for s in wn_ss]
    for k in kaikki_senses(word, pos)[:4]:
        mine = content(k['gloss'])
        twin = next((o for o in out if len(mine & (content(o['gloss']) | (
            {l.lower()[:5] for l in o['ss'].lemmas()} if o['ss'] else set()))) >= 2), None) if mine else None
        if twin:
            twin['src'] = 'WN+Wiki'
            if not twin['example'] and k['example']:
                twin['example'] = k['example']
            continue
        k['ss'] = best_synset(word, pos, k['gloss'])
        k['src'] = 'Wiki'
        out.append(k)
    return out[:7]


by = {p: [w for w in CEFR if w.isalpha() and info(w).get(p) in ('A1', 'A2', 'B1')
          and any(W.synsets(w, pos=x) for x in WNPOS[p])] for p in ALLOW}
random.seed(time.time())
picks = ([tuple(x.split(':')) for x in sys.argv[1:]] or
         [(random.choice(by[p]), p) for p in ('noun', 'noun', 'verb', 'verb', 'adjective')])
BROAD, FROM = set(), {}
result, stats = [], {'qwen': 0, 'to_claude': 0, 'merged': 0}
for word, pos in picks:
    t = time.time()
    senses = sense_list(word, pos)
    answers = qwen(word, pos, [(s['gloss'], s['example']) for s in senses])
    entry = {'word': word, 'pos': pos, 'level': level(word, pos), 'senses': [], 'old': []}
    for i, sense in enumerate(senses):
        a = answers[i] if i < len(answers) else {}
        ss = sense['ss']
        if (sense['archaic'] and a.get('current') is False) or (ss and is_dated(word, pos, ss.definition(), [])):
            entry['old'].append(sense['gloss'])
            continue
        lemmas = [l.lower() for l in ss.lemmas()] if ss else []
        raw = list(a.get('english_easier') or []) + list(a.get('english_harder') or []) + lemmas
        stats['qwen'] += len(raw)
        far = related_out(ss) if ss else set()
        narrower = {l.lower() for h in ss.hyponyms() for l in h.lemmas()} if ss else set()
        words = []
        for x in raw:
            x = x.strip().lower()
            if x == word or x in words or ' ' in x or '-' in x or (x in GENERAL and x not in lemmas):
                continue
            if inflected(x, word, words) or not row_of(x, pos):
                continue
            z = ts._wordfreq_zipf(x) or 0
            if x not in lemmas and (z < 2.5 or (ACADEMIC.search(x) and not info(x) and z < 3.5)):
                continue
            if x in far and x not in lemmas:
                BROAD.add(x)
            words.append(x)
        if pos == 'adjective':
            for x in [word] + [l for l in lemmas if l in words]:
                for adv in sorted(adverbs(x)):
                    if adv not in words and common(adv):
                        words.append(adv)
                        ADVS.add(adv)
                        FROM[adv] = x
        entry['senses'].append({'gloss': sense['gloss'], 'example': sense['example'], 'src': sense['src'],
                                'candidates': [{'w': x, 'level': level(x, 'adverb' if x in ADVS else pos),
                                                'adverb': x in ADVS, 'from': FROM.get(x), 'broad': x in BROAD}
                                               for x in words]})
    merged = []
    for sense in entry['senses']:
        mine = {c['w'] for c in sense['candidates']}
        twin = next((m for m in merged if mine and len(mine & {c['w'] for c in m['candidates']}) >= len(mine) / 2), None)
        if twin:
            have = {c['w'] for c in twin['candidates']}
            twin['candidates'] += [c for c in sense['candidates'] if c['w'] not in have]
            twin['gloss'] += ' / ' + sense['gloss']
            stats['merged'] += 1
        else:
            merged.append(sense)
    entry['senses'] = merged
    stats['to_claude'] += sum(len(x['candidates']) for x in merged)
    entry['seconds'] = round(time.time() - t, 1)
    result.append(entry)
base = os.path.abspath(__file__).replace('.py', '')
json.dump({'stats': stats, 'words': result}, open(base + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('done', picks, stats)
