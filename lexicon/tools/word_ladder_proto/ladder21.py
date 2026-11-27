"""Round 2: senses come from Wiktionary (Kaikki) in its order — the common meanings first —
skipping dated/obsolete/slang ones (archaic ones only when Qwen also says they are not used
today). WordNet adds same-sense synonyms (matched synset), narrower words and the broader-word
flag. Adverbs only from the word itself and WordNet's synonyms."""
import os, sys
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ladder20.py'), encoding='utf-8').read()
exec(_src[:_src.index('\nby = {p:')])

DROP_TAGS = ('dated', 'obsolete', 'slang', 'vulgar', 'offensive', 'derogatory', 'rare', 'nonstandard')
MAX_SENSES = {'verb': 5, 'noun': 4, 'adjective': 4}


def kaikki_senses(word, pos):
    rows = LEXDB.execute("""select s.id, s.ordinal, s.labels, s.definition,
        (select e.text from examples e where e.sense_id=s.id order by e.ordinal limit 1)
        from lexemes l join senses s on s.lexeme_id=l.id where l.normalized=? and l.pos=? order by s.ordinal""",
                         (word, KPOS[pos])).fetchall()
    out = []
    for sid, ordinal, labels, definition, example in rows:
        labels = (labels or '').lower()
        if any(t in labels for t in DROP_TAGS) or not definition:
            continue
        out.append({'gloss': definition, 'example': example or '', 'archaic': 'archaic' in labels})
    return out


def best_synset(word, pos, gloss):
    best, top = None, 0
    mine = content(gloss)
    for ss in [s for x in WNPOS[pos] for s in W.synsets(word, pos=x)]:
        score = len(mine & (content(ss.definition()) | {l.lower()[:5] for l in ss.lemmas()}))
        if score > top:
            best, top = ss, score
    return best


SCHEMA = {'type': 'object', 'properties': {'senses': {'type': 'array', 'maxItems': 8, 'items': {
    'type': 'object', 'properties': {
        'current': {'type': 'boolean'},
        'english_easier': {'type': 'array', 'maxItems': 8, 'items': {'type': 'string'}},
        'english_harder': {'type': 'array', 'maxItems': 10, 'items': {'type': 'string'}}},
    'required': ['current', 'english_easier', 'english_harder']}}}, 'required': ['senses']}

by = {p: [w for w in CEFR if w.isalpha() and info(w).get(p) in ('A1', 'A2', 'B1')
          and any(W.synsets(w, pos=x) for x in WNPOS[p])] for p in ALLOW}
random.seed(time.time())
picks = ([tuple(x.split(':')) for x in sys.argv[1:]] or
         [(random.choice(by[p]), p) for p in ('noun', 'noun', 'verb', 'verb', 'adjective')])
BROAD, FROM = set(), {}
result, stats = [], {'qwen': 0, 'to_claude': 0, 'merged': 0}
for word, pos in picks:
    t = time.time()
    senses = kaikki_senses(word, pos)[:MAX_SENSES[pos]]
    if not senses:  # word missing from Wiktionary: fall back to WordNet's first senses
        senses = [{'gloss': s.definition(), 'example': (s.examples() or [''])[0], 'archaic': False}
                  for x in WNPOS[pos] for s in W.synsets(word, pos=x)][:3]
    answers = qwen(word, pos, [(s['gloss'], s['example']) for s in senses])
    entry = {'word': word, 'pos': pos, 'level': level(word, pos), 'senses': [], 'old': []}
    for i, sense in enumerate(senses):
        a = answers[i] if i < len(answers) else {}
        if sense['archaic'] and a.get('current') is False:
            entry['old'].append(sense['gloss'])
            continue
        ss = best_synset(word, pos, sense['gloss'])
        lemmas = [l.lower() for l in ss.lemmas()] if ss else []
        raw = list(a.get('english_easier') or []) + list(a.get('english_harder') or []) + lemmas
        stats['qwen'] += len(raw)
        far = related_out(ss) if ss else set()
        HARDER = {x.strip().lower() for x in (a.get('english_harder') or [])} | (
            {l.lower() for h in ss.hyponyms() for l in h.lemmas()} if ss else set())
        words = []
        for x in raw:
            x = x.strip().lower()
            if x == word or x in words or ' ' in x or '-' in x or (x in GENERAL and x not in lemmas):
                continue
            if inflected(x, word, words) or not row_of(x, pos):
                continue
            if not (common(x) or (x in HARDER and (ts._wordfreq_zipf(x) or 0) >= 2.0)):
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
        entry['senses'].append({'gloss': sense['gloss'], 'example': sense['example'],
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
