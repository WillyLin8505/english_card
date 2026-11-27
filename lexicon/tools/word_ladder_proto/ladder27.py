"""Round 3: sense list = WordNet's first 4 (roughly by frequency) + Wiktionary's first 4
(non-dated), merged when they match; Claude decides which senses a learner meets. Stricter
filter for academic words on the hard side (frequency >= 2.5, -ology/-ism/... endings)."""
import os, sys
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ladder21.py'), encoding='utf-8').read()
exec(_src[:_src.index('\nby = {p:')])

OLDTAG = ('dated', 'obsolete')  # archaic: Qwen decides (Wiktionary marks 'political party' archaic)

def spelling_variant(x, word):
    """British / American spellings of the same word (jewellery, categorise)."""
    def norm(w):
        for a, b in (('ise', 'ize'), ('isation', 'ization'), ('our', 'or'), ('llery', 'lry'), ('ellery', 'elry'),
                     ('tre', 'ter'), ('ogue', 'og'), ('lled', 'led'), ('lling', 'ling'), ('ae', 'e'), ('oe', 'e')):
            w = w.replace(a, b)
        return w
    return x != word and norm(x) == norm(word)


BLOCK = set('homo fag faggot dyke retard tranny negro gypsy midget spaz cripple'.split())
BADTAGS = ('offensive', 'derogatory', 'slang', 'vulgar', 'pejorative', 'slur')


def offensive(x):
    """Every Wiktionary sense of the word is offensive, slang or vulgar (homo)."""
    rows = LEXDB.execute("""select s.labels from lexemes l join senses s on s.lexeme_id=l.id
        where l.normalized=?""", (x,)).fetchall()
    tagged = [r[0] for r in rows if r[0] and any(t in r[0].lower() for t in BADTAGS)]
    if x in BLOCK:
        return True
    return bool(rows) and (len(tagged) == len(rows) or any('offensive' in (r or '').lower() or 'derogatory' in (r or '').lower() for r in tagged))


ACADEMIC = re.compile(r'(ology|ism|ity|ization|isation|ics|oid|ive)$')


def all_senses(word, pos):
    """Every dictionary sense: WordNet synsets + Wiktionary senses (not dated), duplicates joined."""
    out = [{'gloss': s.definition(), 'example': (s.examples() or [''])[0], 'archaic': False, 'ss': s, 'src': 'WN'}
           for x in WNPOS[pos] for s in W.synsets(word, pos=x)][:10]
    for k in kaikki_senses(word, pos)[:12]:
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
    return out


PICK = {'type': 'object', 'properties': {'common': {'type': 'array', 'maxItems': 4, 'items': {'type': 'integer'}}},
        'required': ['common']}


def sense_list(word, pos):
    """Round 8: Qwen picks today's most common meanings FROM the dictionary list (never invents)."""
    senses = all_senses(word, pos)
    if len(senses) <= 3:
        return senses
    listing = '\n'.join(f'{i + 1}. {s["gloss"]}' for i, s in enumerate(senses))
    prompt = (f'English {pos} "{word}". Here are its dictionary meanings:\n{listing}\n'
              f'Which of these meanings do people use most often in everyday English TODAY? Give up to '
              f'{MAX_SENSES[pos]} numbers, most common first. Skip old, rare, technical or specialist meanings. '
              'Reply with JSON only.')
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 100,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': PICK}}}
    req = urllib.request.Request(ts.LLAMACPP_URL + '/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    q = ts.loads_salvaging(json.load(urllib.request.urlopen(req, timeout=120))['choices'][0]['message']['content'] or '{}')
    picked = [senses[n - 1] for n in (q.get('common') or []) if isinstance(n, int) and 1 <= n <= len(senses)]
    # round 9: the first WordNet sense and the first Wiktionary sense are always in (sick = ill)
    first_wn = next((x for x in senses if x['src'].startswith('WN')), None)
    first_wiki = next((x for x in senses if 'Wiki' in x['src']), None)
    picked = [x for x in (first_wn, first_wiki) if x] + picked
    seen, out = set(), []
    for s_ in picked:
        if id(s_) not in seen:
            seen.add(id(s_))
            out.append(s_)
    return out[:5] or senses[:MAX_SENSES[pos]]


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
    ANTONYMS = {a.word().lemma().lower() for x in WNPOS[pos] for ss_ in W.synsets(word, pos=x)
                for s_ in ss_.senses() if s_.word().lemma().lower() == word for a in s_.get_related('antonym')}
    for ss_ in [s for x in WNPOS[pos] for s in W.synsets(word, pos=x)]:  # adjective clusters: antonyms of similar heads
        for sim in ss_.get_related('similar'):
            for s_ in sim.senses():
                ANTONYMS |= {a.word().lemma().lower() for a in s_.get_related('antonym')}
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
            if inflected(x, word, words) or not row_of(x, pos) or spelling_variant(x, word) or any(spelling_variant(x, y) for y in words) or offensive(x) or x in ANTONYMS:
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
        entry['senses'].append({'ssid': ss.id if ss else None, 'gloss': sense['gloss'], 'example': sense['example'], 'src': sense['src'],
                                'candidates': [{'w': x, 'level': level(x, 'adverb' if x in ADVS else pos),
                                                'adverb': x in ADVS, 'from': FROM.get(x), 'broad': x in BROAD}
                                               for x in words]})
    merged = []
    for sense in entry['senses']:
        mine = {c['w'] for c in sense['candidates']}
        twin = next((m for m in merged if (sense.get('ssid') and sense['ssid'] == m.get('ssid')) or (mine and len(mine & {c['w'] for c in m['candidates']}) >= len(mine) / 3)), None)
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
