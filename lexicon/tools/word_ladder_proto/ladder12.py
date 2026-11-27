"""ladder8 + owner 11/27 feedback: a second Qwen check per sense (same meaning? Chinese in
this meaning), adverbs from WordNet for adjectives, near-duplicate WordNet senses merged."""
import os, sys
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ladder8.py'), encoding='utf-8').read()
exec(_src[:_src.index('by = {p:')])


SCHEMA = {'type': 'object', 'properties': {'senses': {'type': 'array', 'maxItems': 6, 'items': {
    'type': 'object', 'properties': {
        'current': {'type': 'boolean'},
        'english_easier': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string'}},
        'english_harder': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string'}},
        'zh': {'type': 'string'}},
    'required': ['current', 'english_easier', 'english_harder', 'zh']}}}, 'required': ['senses']}


def qwen(word, pos, glosses):
    numbered = '\n'.join(f'{i + 1}. {g}' for i, g in enumerate(glosses))
    prompt = (f'English {pos} "{word}" has these meanings:\n{numbered}\n'
              'For EACH meaning, in the same order, give: "current": true only if people still commonly use '
              f'"{word}" with this meaning today (false if it is old-fashioned, dated or rare now, e.g. "gay" '
              'meaning cheerful); "english_easier": simpler, more common everyday '
              f'ENGLISH {NAME[pos]} with the same meaning; "english_harder": less common, more precise or '
              f'advanced ENGLISH {NAME[pos]} with the same meaning; "zh": the meaning in Traditional Chinese '
              '(Taiwan), 2 to 6 characters. The word lists are English words only, single words, dictionary '
              'form, lowercase. Only words that really mean this; no slang, no archaic or scientific jargon. '
              'Reply with JSON only.')
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 1200,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': SCHEMA}}}
    req = urllib.request.Request(ts.LLAMACPP_URL + '/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    q = ts.loads_salvaging(json.load(urllib.request.urlopen(req, timeout=180))['choices'][0]['message']['content'] or '{}')
    return q.get('senses', []) or []


CHECK = {'type': 'object', 'properties': {'words': {'type': 'array', 'maxItems': 20, 'items': {
    'type': 'object', 'properties': {'w': {'type': 'string'}, 'same_meaning': {'type': 'boolean'},
                                     'zh': {'type': 'string'}},
    'required': ['w', 'same_meaning', 'zh']}}}, 'required': ['words']}


def check(word, pos, gloss, words):
    """Second pass: keep a word only if it really means this; its Chinese in THIS meaning."""
    if not words:
        return {}
    prompt = (f'English {pos} "{word}" in the meaning: "{gloss}".\n'
              'For each word below say whether it means the same or nearly the same as this meaning '
              '("same_meaning"), and give its Traditional Chinese (Taiwan) translation IN THIS MEANING, '
              '2 to 5 characters ("zh"). Keep the order and copy each word exactly.\n'
              + '\n'.join(f'- {w}' for w in words) + '\nReply with JSON only.')
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 900,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': CHECK}}}
    req = urllib.request.Request(ts.LLAMACPP_URL + '/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    reply = json.load(urllib.request.urlopen(req, timeout=180))['choices'][0]['message']['content']
    q = ts.loads_salvaging(reply or '{}')
    return {str(x.get('w', '')).lower(): x for x in q.get('words', []) or []}


def adverbs(adj):
    """WordNet adverbs made from an adjective (quick -> quickly)."""
    out = set()
    for ss in W.synsets(adj, pos='a') + W.synsets(adj, pos='s'):
        for s in ss.senses():
            if s.word().lemma().lower() != adj:
                continue
            for d in s.get_related('pertainym') + s.get_related('derivation'):
                if d.synset().pos == 'r':
                    out.add(d.word().lemma().lower())
    forms = [adj + 'ly']
    if adj.endswith('y'):
        forms.append(adj[:-1] + 'ily')
    if adj.endswith('ic'):
        forms.append(adj + 'ally')
    if adj.endswith('le'):
        forms.append(adj[:-2] + 'ly')
    for f in forms:
        if W.synsets(f, pos='r'):
            out.add(f)
    return out


ADVS = set()
OLD = []
LEXDB = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lex.sqlite'))
KPOS = {'noun': 'noun', 'verb': 'verb', 'adjective': 'adj'}
STOP = set('a an the of or and to in on for with by as at from that this is be being been not only any one '
           'some something someone especially often usually very more most it its'.split())
OLDTAG = ('dated', 'archaic', 'obsolete', 'old-fashioned', 'rare')


def content(text):
    return {w for w in re.findall(r'[a-z]+', text.lower()) if w not in STOP and len(w) > 2}


def is_dated(word, pos, gloss, synonyms):
    """Owner 11/27 「意思太舊也要排除」: Wiktionary (Kaikki) labels senses dated/archaic/obsolete.
    A WordNet sense whose gloss and synonyms match a labelled-old Wiktionary sense better than
    any current one is left out (gay = happy)."""
    rows = LEXDB.execute("""select s.labels, s.definition from lexemes l join senses s on s.lexeme_id=l.id
        where l.normalized=? and l.pos=?""", (word, KPOS[pos])).fetchall()
    if not rows:
        return False
    mine = content(gloss) | set(synonyms)
    best_old = best_new = 0
    for labels, definition in rows:
        score = len(mine & content(definition or ''))
        if any(t in (labels or '') for t in OLDTAG):
            best_old = max(best_old, score)
        else:
            best_new = max(best_new, score)
    return best_old > 0 and best_old > best_new
by = {p: [w for w in CEFR if w.isalpha() and info(w).get(p) in ('A1', 'A2', 'B1')
          and any(W.synsets(w, pos=x) for x in WNPOS[p])] for p in ALLOW}
random.seed(time.time())
picks = ([tuple(x.split(':')) for x in sys.argv[1:]] or
         [(random.choice(by[p]), p) for p in ('noun', 'noun', 'verb', 'verb', 'adjective')])
out = []
for word, pos in picks:
    t = time.time()
    synsets = [s for x in WNPOS[pos] for s in W.synsets(word, pos=x)][:6]
    answers = qwen(word, pos, [s.definition() for s in synsets])
    senses = []
    for i, ss in enumerate(synsets):
        a = answers[i] if i < len(answers) else {}
        if a.get('current') is False:
            OLD.append(f'{word}：{a.get("zh", "")}（{ss.definition()}）')
            continue
        words = []
        for x in list(a.get('english_easier') or []) + list(a.get('english_harder') or []) + list(ss.lemmas()):
            x = x.strip().lower()
            if x != word and x not in words and ' ' not in x and '-' not in x and common(x) and row_of(x, pos):
                words.append(x)
        words = [x for x in words if not (pos == 'adjective' and W.synsets(x, pos='r') and not W.synsets(x, pos='a') and not W.synsets(x, pos='s'))]
        verdict = check(word, pos, ss.definition(), words)
        # WordNet's own synonyms for this sense are the same meaning by definition (autumn / fall).
        wn_same = {l.lower() for l in ss.lemmas()}
        kept = [(x, verdict.get(x, {}).get('zh', '') or zh(x, pos)) for x in words
                if verdict.get(x, {}).get('same_meaning') is True or x in wn_same]
        if is_dated(word, pos, ss.definition(), [k for k, _ in kept]):
            OLD.append(f'{word}：{a.get("zh", "")}（{ss.definition()}；維基詞典標為過時）')
            continue
        dropped = [x for x in words if x not in dict(kept)]
        if pos == 'adjective':
            # Owner 11/27: adverbs made from a kept adjective keep its meaning; no second check.
            for x in [word] + [k for k, _ in kept]:
                for adv in sorted(adverbs(x)):
                    if adv not in dict(kept) and common(adv):
                        kept.append((adv, zh(adv, 'adverb')))
                        ADVS.add(adv)
        zh_sense = a.get('zh', '')
        # WordNet splits finely: a sense with the same Chinese or mostly the same words joins the earlier one.
        twin = None
        for s in senses:
            overlap = len(set(dict(kept)) & set(dict(s['kept'])))
            if s['zh'] == zh_sense or (kept and overlap >= max(1, len(kept) // 2)):
                twin = s
                break
        if twin:
            have = dict(twin['kept'])
            twin['kept'] += [k for k in kept if k[0] not in have]
            twin['dropped'] += [d for d in dropped if d not in twin['dropped']]
            twin['merged'] += 1
            continue
        senses.append({'zh': zh_sense, 'gloss': ss.definition(), 'kept': kept, 'dropped': dropped, 'merged': 0})
    out.append(f'### {word}（{R[pos]}）')
    for i, s in enumerate(senses):
        grid = {r: {l: [] for l in LV} for r in ALLOW[pos]}
        grid[pos][level(word, pos)].append(f'**{word}**')
        for x, z in s['kept']:
            r = 'adverb' if x in ADVS else pos
            grid[r][level(x, r)].append(x + (f' {z}' if z else ''))
        merged = f'，併入 {s["merged"]} 個相同意思' if s['merged'] else ''
        out.append(f'\n**意思 {i + 1}：{s["zh"]}**（{s["gloss"]}{merged}）\n\n| | ' + ' | '.join(LV)
                   + ' |\n|---|' + '---|' * 6)
        for r, c in grid.items():
            out.append('| ' + R[r] + ' | ' + ' | '.join('<br>'.join(c[l]) for l in LV) + ' |')
        out.append(f'\n第二次檢查刪掉：{", ".join(s["dropped"]) or "無"}')
    out.append(f'\n（{time.time() - t:.1f} 秒）\n')
out.append('**排除的過時意思：** ' + ('；'.join(OLD) or '無'))
open(os.path.abspath(__file__).replace('.py', '.md'), 'w', encoding='utf-8').write('\n'.join(out))
print('done', picks)
