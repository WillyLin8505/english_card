"""ladder15 + owner 11/27 optimisations: (1) general-word stoplist, (2) WordNet hypernyms /
hyponyms dropped, (3) inflected forms dropped, (5) senses ranked by Wiktionary (Kaikki) order,
unmatched rare senses dropped, (6) WordNet example sentence given to Qwen, (8) suspicious CEFR
levels corrected by frequency. Output: candidates for Claude's check (JSON + markdown)."""
import os, sys
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ladder15.py'), encoding='utf-8').read()
exec(_src[:_src.index('\nby = {p:')])

def content(text):  # word stems (first 5 letters): fastener ~ fastening, running ~ runs
    return {w[:5] for w in re.findall(r'[a-z]+', text.lower()) if w not in STOP and len(w) > 2}


GENERAL = set('go get have do make take put give say thing stuff place way thing time person people '
              'one something good bad big small new old part kind type sort lot set use show see know '
              'come let keep feel find work area item object matter piece bit'.split())


def zipf_level(w):
    z = ts._wordfreq_zipf(w)
    return ts.zipf_level(z) if z is not None else None


def level(w, pos):  # (8) list level, unless frequency says it is two or more bands easier
    p = info(w)
    lv = (p.get(pos) or sorted(p.values(), key=LV.index)[0]) if p else None
    zl = zipf_level(w)
    if lv and zl and LV.index(lv) - LV.index(zl) >= 2:
        return LV[LV.index(lv) - 1]
    return lv or zl or 'C2'


def related_out(ss, depth=2):
    """Lemmas of hypernyms and hyponyms (two steps): broader or narrower, not the same."""
    out, frontier = set(), [ss]
    for _ in range(depth):
        nxt = []
        for s in frontier:
            for r in s.hypernyms():  # broader words only; narrower ones (gnaw for bite) are good harder words
                out |= {l.lower() for l in r.lemmas()}
                nxt.append(r)
        frontier = nxt
    return out


def inflected(x, word, others):
    for suf, rep in (('ies', 'y'), ('es', ''), ('s', ''), ('ing', ''), ('ing', 'e'), ('ed', ''), ('ed', 'e'), ('d', '')):
        if x.endswith(suf) and x[:-len(suf)] + rep in ({word} | set(others)):
            return True
    return False


def kaikki_rank(word, pos, ss):
    """(5) Position of the best-matching Wiktionary sense; None when nothing matches."""
    rows = LEXDB.execute("""select s.ordinal, s.definition from lexemes l join senses s on s.lexeme_id=l.id
        where l.normalized=? and l.pos=? order by s.ordinal""", (word, KPOS[pos])).fetchall()
    mine = content(ss.definition()) | {l.lower()[:5] for l in ss.lemmas() if l.lower() != word}
    best = None
    for n, (ordinal, definition) in enumerate(rows):
        score = len(mine & content(definition or ''))
        if score and (best is None or score > best[1]):
            best = (n, score)
    return best[0] if best else None


SCHEMA = {'type': 'object', 'properties': {'senses': {'type': 'array', 'maxItems': 4, 'items': {
    'type': 'object', 'properties': {
        'current': {'type': 'boolean'},
        'english_easier': {'type': 'array', 'maxItems': 8, 'items': {'type': 'string'}},
        'english_harder': {'type': 'array', 'maxItems': 10, 'items': {'type': 'string'}}},
    'required': ['current', 'english_easier', 'english_harder']}}}, 'required': ['senses']}


def qwen(word, pos, senses):
    numbered = '\n'.join(f'{i + 1}. {g}' + (f' Example: "{e}"' if e else '') for i, (g, e) in enumerate(senses))
    prompt = (f'English {pos} "{word}" has these meanings:\n{numbered}\n'
              'For EACH meaning, in the same order, give: "current": true only if people still commonly use '
              f'"{word}" with this meaning today; "english_easier": simpler, more common everyday ENGLISH '
              f'{NAME[pos]} that could REPLACE "{word}" in the example sentence (or a natural sentence with this '
              f'meaning) without changing its meaning; "english_harder": less common, more precise or advanced '
              f'ENGLISH {NAME[pos]} that could replace it the same way. Give as many candidates as you can (up to '
              '8 easier and 10 harder); a later check removes wrong ones. English single words only, dictionary '
              'form, lowercase; no slang. Reply with JSON only.')
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 2000,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': SCHEMA}}}
    req = urllib.request.Request(ts.LLAMACPP_URL + '/v1/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    q = ts.loads_salvaging(json.load(urllib.request.urlopen(req, timeout=240))['choices'][0]['message']['content'] or '{}')
    return q.get('senses', []) or []


by = {p: [w for w in CEFR if w.isalpha() and info(w).get(p) in ('A1', 'A2', 'B1')
          and any(W.synsets(w, pos=x) for x in WNPOS[p])] for p in ALLOW}
random.seed(time.time())
picks = ([tuple(x.split(':')) for x in sys.argv[1:]] or
         [(random.choice(by[p]), p) for p in ('noun', 'noun', 'verb', 'verb', 'adjective')])
result, stats = [], {'qwen': 0, 'filtered': 0}
for word, pos in picks:
    t = time.time()
    all_ss = [s for x in WNPOS[pos] for s in W.synsets(word, pos=x)]
    ranked = sorted(((kaikki_rank(word, pos, s), i, s) for i, s in enumerate(all_ss)),
                    key=lambda r: (r[0] is None, r[0] if r[0] is not None else 99, r[1]))
    chosen = [s for rk, i, s in ranked if rk is not None or i == 0][:4]
    answers = qwen(word, pos, [(s.definition(), (s.examples() or [''])[0]) for s in chosen])
    entry = {'word': word, 'pos': pos, 'level': level(word, pos), 'senses': [], 'old': []}
    for i, ss in enumerate(chosen):
        a = answers[i] if i < len(answers) else {}
        raw = list(a.get('english_easier') or []) + list(a.get('english_harder') or []) + list(ss.lemmas())
        # harder-list words and the sense's narrower words may be rarer (enunciate, gnaw)
        HARDER = {x.strip().lower() for x in (a.get('english_harder') or [])} | {
            l.lower() for h in ss.hyponyms() for l in h.lemmas()}
        stats['qwen'] += len(raw)
        far = related_out(ss)
        wn_same = {l.lower() for l in ss.lemmas()}
        words, why = [], {}
        for x in raw:
            x = x.strip().lower()
            reason = None
            if x == word or x in words:
                continue
            if ' ' in x or '-' in x:
                reason = '片語'
            elif x in GENERAL and x not in wn_same:
                reason = '太空泛'
            elif x in far and x not in wn_same:
                reason = '上下位'
            elif inflected(x, word, words):
                reason = '變化形'
            elif not (common(x) or (x in HARDER and (ts._wordfreq_zipf(x) or 0) >= 2.0)):
                reason = '罕見'
            elif not row_of(x, pos):
                reason = '詞性'
            if reason:
                why[x] = reason
                continue
            words.append(x)
        if pos == 'adjective':
            for x in [word] + words:
                for adv in sorted(adverbs(x)):
                    if adv not in words and common(adv):
                        words.append(adv)
                        ADVS.add(adv)
        stats['filtered'] += len(words)
        if a.get('current') is False or is_dated(word, pos, ss.definition(), words):
            entry['old'].append(ss.definition())
            continue
        entry['senses'].append({'gloss': ss.definition(), 'example': (ss.examples() or [''])[0],
                                'candidates': [{'w': x, 'level': level(x, 'adverb' if x in ADVS else pos),
                                                'adverb': x in ADVS} for x in words],
                                'dropped': why})
    entry['seconds'] = round(time.time() - t, 1)
    result.append(entry)
base = os.path.abspath(__file__).replace('.py', '')
json.dump({'stats': stats, 'words': result}, open(base + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
lines = [f"Qwen 候選 {stats['qwen']} 個 → 程式過濾後 {stats['filtered']} 個給 Claude"]
for e in result:
    lines.append(f"\n## {e['word']} ({e['pos']}, {e['level']}) {e['seconds']}s；排除的過時意思：{'; '.join(e['old']) or '無'}")
    for s in e['senses']:
        lines.append(f"- {s['gloss']} | 例：{s['example']}")
        lines.append('  候選：' + ', '.join(f"{c['w']}({c['level']}{',adv' if c['adverb'] else ''})" for c in s['candidates']))
        lines.append('  程式刪：' + ', '.join(f'{k}[{v}]' for k, v in s['dropped'].items()))
open(base + '.md', 'w', encoding='utf-8').write('\n'.join(lines))
print('done', picks, stats)
