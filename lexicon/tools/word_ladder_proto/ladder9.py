"""ladder8 + owner 11/27 feedback: a second Qwen check per sense (same meaning? Chinese in
this meaning), adverbs from WordNet for adjectives, near-duplicate WordNet senses merged."""
import os, sys
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ladder8.py'), encoding='utf-8').read()
exec(_src[:_src.index('by = {p:')])

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


by = {p: [w for w in CEFR if w.isalpha() and info(w).get(p) in ('A1', 'A2', 'B1')
          and any(W.synsets(w, pos=x) for x in WNPOS[p])] for p in ALLOW}
random.seed(time.time())
picks = ([tuple(x.split(':')) for x in sys.argv[1:]] or
         [(random.choice(by[p]), p) for p in ('noun', 'noun', 'verb', 'verb', 'adjective')])
out = []
for word, pos in picks:
    t = time.time()
    synsets = [s for x in WNPOS[pos] for s in W.synsets(word, pos=x)][:3]
    answers = qwen(word, pos, [s.definition() for s in synsets])
    senses = []
    for i, ss in enumerate(synsets):
        a = answers[i] if i < len(answers) else {}
        words = []
        for x in list(a.get('english_easier') or []) + list(a.get('english_harder') or []) + list(ss.lemmas()):
            x = x.strip().lower()
            if x != word and x not in words and ' ' not in x and '-' not in x and common(x) and row_of(x, pos):
                words.append(x)
        if pos == 'adjective':
            for x in list(words) + [word]:
                for adv in sorted(adverbs(x)):
                    if adv not in words and common(adv):
                        words.append(adv)
        verdict = check(word, pos, ss.definition(), words)
        kept = [(x, verdict.get(x, {}).get('zh', '')) for x in words
                if verdict.get(x, {}).get('same_meaning') is True]
        dropped = [x for x in words if x not in dict(kept)]
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
            r = 'adverb' if pos == 'adjective' and x.endswith('ly') else (row_of(x, pos) or pos)
            grid[r][level(x, r)].append(x + (f' {z}' if z else ''))
        merged = f'，併入 {s["merged"]} 個相同意思' if s['merged'] else ''
        out.append(f'\n**意思 {i + 1}：{s["zh"]}**（{s["gloss"]}{merged}）\n\n| | ' + ' | '.join(LV)
                   + ' |\n|---|' + '---|' * 6)
        for r, c in grid.items():
            out.append('| ' + R[r] + ' | ' + ' | '.join('<br>'.join(c[l]) for l in LV) + ' |')
        out.append(f'\n第二次檢查刪掉：{", ".join(s["dropped"]) or "無"}')
    out.append(f'\n（{time.time() - t:.1f} 秒）\n')
open(os.path.abspath(__file__).replace('.py', '.md'), 'w', encoding='utf-8').write('\n'.join(out))
print('done', picks)
