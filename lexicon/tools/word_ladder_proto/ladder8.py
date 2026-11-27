"""Hybrid word ladder: senses from OEWN (real, never invented), words per sense from Qwen
(given the WordNet gloss) plus the sense's own WordNet synonyms, levels from CEFR-J/Oxford
(frequency for unlisted words), Chinese from ECDICT by part of speech (zh-TW via OpenCC),
else Qwen's translation of the sense."""
import sys, json, urllib.request, random, time, re, sqlite3
sys.path.insert(0, 'D:/vibe_coding/english_card/tagger')
import tagging_server as ts
import wn, opencc

W = wn.Wordnet('oewn:2024')
CC = opencc.OpenCC('s2twp')
ECD = sqlite3.connect('D:/vibe_coding/english_card/lexicon/raw-data/ecdict.sqlite3')
CEFR = json.load(open('D:/vibe_coding/english_card/app/assets/cefr_en.json', encoding='utf-8'))['words']
LV = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
K = {'adj.': 'adjective', 'adv.': 'adverb'}
WNPOS = {'noun': ['n'], 'verb': ['v'], 'adjective': ['a', 's']}
ALLOW = {'noun': ['noun'], 'verb': ['verb'], 'adjective': ['adjective', 'adverb']}
NAME = {'noun': 'nouns', 'verb': 'verbs', 'adjective': 'adjectives or adverbs (e.g. quick, quickly)'}
R = {'noun': '名詞', 'verb': '動詞', 'adjective': '形容詞', 'adverb': '副詞'}
ECPOS = {'noun': ('n.',), 'verb': ('v.', 'vt.', 'vi.'), 'adjective': ('a.', 'adj.'), 'adverb': ('ad.', 'adv.')}


def info(w):
    e = CEFR.get(w)
    return {K.get(k, k): v for k, v in e[1].items()} if e and e[1] else {}


def level(w, pos):
    p = info(w)
    if p:
        return p.get(pos) or sorted(p.values(), key=LV.index)[0]
    return ts.word_cefr(w, None)[0] or 'C2'


def common(w):
    if info(w):
        return True
    z = ts._wordfreq_zipf(w)
    return z is not None and z >= 2.8


def zh(w, pos):
    """ECDICT's line for this part of speech, first meaning, Taiwan wording."""
    r = ECD.execute('select translation from e where lower=? limit 1', (w.lower(),)).fetchone()
    if not r or not r[0]:
        return ''
    for line in re.split(r'\\n|\n', r[0]):
        line = line.strip()
        if line.startswith(ECPOS[pos]):
            t = re.sub(r'^[a-z]+\.\s*', '', line)
            t = re.sub(r'\[[^\]]*\]|（[^）]*）|\([^)]*\)', '', t)
            return CC.convert(re.split(r'[，,；;]', t)[0].strip())[:8]
    return ''


def row_of(x, pos):
    if pos != 'adjective':
        p = info(x)
        return pos if (not p or pos in p) else None
    p = info(x)
    if p:
        return 'adverb' if 'adverb' in p and 'adjective' not in p else ('adjective' if 'adjective' in p else None)
    return 'adverb' if x.endswith('ly') else 'adjective'


SCHEMA = {'type': 'object', 'properties': {'senses': {'type': 'array', 'maxItems': 3, 'items': {
    'type': 'object', 'properties': {
        'english_easier': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string'}},
        'english_harder': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string'}},
        'zh': {'type': 'string'}},
    'required': ['english_easier', 'english_harder', 'zh']}}}, 'required': ['senses']}


def qwen(word, pos, glosses):
    numbered = '\n'.join(f'{i + 1}. {g}' for i, g in enumerate(glosses))
    prompt = (f'English {pos} "{word}" has these meanings:\n{numbered}\n'
              'For EACH meaning, in the same order, give: "english_easier": simpler, more common everyday '
              f'ENGLISH {NAME[pos]} with the same meaning; "english_harder": less common, more precise or '
              f'advanced ENGLISH {NAME[pos]} with the same meaning; "zh": the meaning in Traditional Chinese '
              '(Taiwan), 2 to 6 characters. The word lists are English words only, single words, dictionary '
              'form, lowercase. Only words that really mean this; no slang, '
              'no archaic or scientific jargon. Reply with JSON only.')
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 700,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': SCHEMA}}}
    req = urllib.request.Request(ts.LLAMACPP_URL + '/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    q = ts.loads_salvaging(json.load(urllib.request.urlopen(req, timeout=180))['choices'][0]['message']['content'] or '{}')
    return q.get('senses', []) or []


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
    out.append(f'### {word}（{R[pos]}）')
    for i, ss in enumerate(synsets):
        a = answers[i] if i < len(answers) else {}
        a = {'zh': a.get('zh', ''), 'easier': a.get('english_easier', []) or [], 'harder': a.get('english_harder', []) or []}
        grid = {r: {l: [] for l in LV} for r in ALLOW[pos]}
        grid[pos][level(word, pos)].append(f'**{word}**')
        seen, dropped = {word}, []
        for x in list(a['easier']) + list(a['harder']) + [l for l in ss.lemmas()]:
            x = x.strip().lower()
            if x in seen:
                continue
            seen.add(x)
            r = row_of(x, pos) if (' ' not in x and '-' not in x and common(x)) else None
            if not r:
                dropped.append(x)
                continue
            z = zh(x, r)
            grid[r][level(x, r)].append(x + (f' {z}' if z else ''))
        out.append(f'\n**意思 {i + 1}：{a["zh"]}**（{ss.definition()}）\n\n| | ' + ' | '.join(LV) + ' |\n|---|' + '---|' * 6)
        for r, c in grid.items():
            out.append('| ' + R[r] + ' | ' + ' | '.join('<br>'.join(c[l]) for l in LV) + ' |')
        out.append(f'\n過濾掉（片語、罕見字、詞性不符）：{", ".join(dropped) or "無"}')
    out.append(f'\n（{time.time() - t:.1f} 秒）\n')
open(sys.argv[0].replace('.py', '.md'), 'w', encoding='utf-8').write('\n'.join(out))
print('done', picks)
