"""Word ladder (單字上下游) pipeline, card #1450 / issue #1875. Clean version of word_ladder_proto/ladder30.py.

  python lexicon/tools/word_ladder.py words                  # print the 1,000-word list + counts
  python lexicon/tools/word_ladder.py run [--batch N] [--limit-batches K] [--force-day]
  python lexicon/tools/word_ladder.py open-issues            # one [上下游檢查] issue per batch file without one
  python lexicon/tools/word_ladder.py build-app              # checked_batch_NN.json -> app/assets/word_ladder_en.json
  python lexicon/tools/word_ladder.py sample N               # N random words (Qwen + filtered) for the result.md
  python lexicon/tools/word_ladder.py pack N                 # qwen_batch_NN.json -> review_batch_NN.txt (short, for the reviewer)
  python lexicon/tools/word_ladder.py apply N [--suffix _codex]  # review_batch_NN.tsv -> checked_batch_NN.json

Steps per batch of 75 words: list senses (WordNet + Wiktionary) -> reuse groups already made for the same
WordNet synset -> Qwen finds candidates (4 words at once = llama-server's 4 slots) -> program filter ->
raw-data/word_ladder/qwen_batch_NN.json (compact, for the Claude check). Qwen only runs 01:00-07:00 Taipei
unless --force-day. The Wiktionary export is never modified: the index lives on a copy (lex.sqlite).
"""
import argparse, json, os, random, re, shutil, sqlite3, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tagger'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_gate  # card #1465: shared GPU throttle
OUT = os.path.join(ROOT, 'lexicon', 'raw-data', 'word_ladder')
EXPORT = os.path.join(ROOT, 'lexicon', 'exports', 'language-data-en-zh-TW-20261028-0929',
                      'language-data-en-zh-TW-20261028-0929.sqlite')
LEXDB_PATH = os.path.join(OUT, 'lex.sqlite')
STATE = os.path.join(OUT, 'groups_state.json')
APP_ASSET = os.path.join(ROOT, 'app', 'assets', 'word_ladder_en.json')
API = 'http://127.0.0.1:5173'
N_WORDS, BATCH_SIZE, SLOTS = 1000, 75, 4
MAX_QWEN_SENSES = 6  # owner 11/27 「時間太長」: 8 -> 6 senses, 8+10 -> 6+6 candidates
PACK_CANDS = 12  # candidates per sense shown to the reviewer (WordNet lemmas first)

LV = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
K = {'adj.': 'adjective', 'adv.': 'adverb'}
WNPOS = {'noun': ['n'], 'verb': ['v'], 'adjective': ['a', 's']}
NAME = {'noun': 'nouns', 'verb': 'verbs', 'adjective': 'adjectives or adverbs (e.g. quick, quickly)'}
KPOS = {'noun': 'noun', 'verb': 'verb', 'adjective': 'adj'}
MAX_SENSES = {'verb': 5, 'noun': 4, 'adjective': 4}
DROP_TAGS = ('dated', 'obsolete', 'slang', 'vulgar', 'offensive', 'derogatory', 'rare', 'nonstandard')
OLDTAG = ('dated', 'archaic', 'obsolete', 'old-fashioned', 'rare')
BADTAGS = ('offensive', 'derogatory', 'slang', 'vulgar', 'pejorative', 'slur')
BLOCK = set('homo fag faggot dyke retard tranny negro gypsy midget spaz cripple'.split())
STOP = set('a an the of or and to in on for with by as at from that this is be being been not only any one '
           'some something someone especially often usually very more most it its'.split())
GENERAL = set('go get have do make take put give say thing stuff place way time person people '
              'one something good bad big small new old part kind type sort lot set use show see know '
              'come let keep feel find work area item object matter piece bit'.split())
ACADEMIC = re.compile(r'(ology|ism|ity|ization|isation|ics|oid|ive)$')

# words with no ladder: months, weekdays, numbers, function / auxiliary words, units, people's names
EXCLUDE = set('''january february march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday
zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen
eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion
first second third fourth fifth last next half double single dozen
be am is are was were been being have has had having do does did done doing can could may might must shall should
will would ought need dare let
a an the this that these those i me my you your he him his she her it its we us our they them their
metre meter kilometre kilometer centimetre centimeter millimetre millimeter mile yard foot inch pound ounce gram kilogram
litre liter gallon pint hour minute second week month year day percent degree dollar cent penny euro
mr mrs ms miss sir madam dr
'''.split())

_W = _CC = _ts = _cefr = _lexdb = None


# ---------- resources ----------
def ts():
    global _ts
    if _ts is None:
        import tagging_server
        _ts = tagging_server
    return _ts


def wordnet():
    global _W
    if _W is None:
        import wn
        _W = wn.Wordnet('oewn:2024')
    return _W


def cefr():
    global _cefr
    if _cefr is None:
        _cefr = json.load(open(os.path.join(ROOT, 'app', 'assets', 'cefr_en.json'), encoding='utf-8'))['words']
    return _cefr


def lexdb():
    """Copy of the Wiktionary export with indexes (the export itself is never touched)."""
    global _lexdb
    if _lexdb is None:
        os.makedirs(OUT, exist_ok=True)
        if not os.path.exists(LEXDB_PATH):
            tmp = LEXDB_PATH + '.tmp'
            shutil.copyfile(EXPORT, tmp)
            c = sqlite3.connect(tmp)
            c.execute('create index if not exists ix_lex_norm on lexemes(normalized,pos)')
            c.execute('create index if not exists ix_sense_lex on senses(lexeme_id)')
            c.execute('create index if not exists ix_ex_sense on examples(sense_id)')
            c.commit()
            c.close()
            os.replace(tmp, LEXDB_PATH)
        _lexdb = sqlite3.connect(LEXDB_PATH)
    return _lexdb


# ---------- levels and word lists ----------
def info(w):
    e = cefr().get(w)
    return {K.get(k, k): v for k, v in e[1].items()} if e and e[1] else {}


def zipf_level(w):
    z = ts()._wordfreq_zipf(w)
    return ts().zipf_level(z) if z is not None else None


def level(w, pos):
    """CEFR list level; one band up when the list has only another part of speech; one band down when
    the frequency says it is two or more bands easier."""
    p = info(w)
    lv = (p.get(pos) or sorted(p.values(), key=LV.index)[0]) if p else None
    if p and pos not in p and lv:
        lv = LV[min(LV.index(lv) + 1, 5)]
    zl = zipf_level(w)
    if lv and zl and LV.index(lv) - LV.index(zl) >= 2:
        return LV[LV.index(lv) - 1]
    return lv or zl or 'C2'


def common(w):
    if info(w):
        return True
    z = ts()._wordfreq_zipf(w)
    return z is not None and z >= 2.8


def row_of(x, pos):
    """Row the word may stand in: noun->noun, verb->verb, adjective->adjective or adverb."""
    p = info(x)
    if pos != 'adjective':
        return pos if (not p or pos in p) else None
    if p:
        return 'adverb' if 'adverb' in p and 'adjective' not in p else ('adjective' if 'adjective' in p else None)
    return 'adverb' if x.endswith('ly') else 'adjective'


def pick_words(n=N_WORDS):
    """The n most common words: CEFR A1 up, same level by frequency (high first). -> [(word, [pos...])]"""
    W = wordnet()
    rows = []
    for w, e in cefr().items():
        if not w.isalpha() or w in EXCLUDE or w[0].isupper() or len(w) < 2 or not e[1]:
            continue
        poss = {K.get(k, k): v for k, v in e[1].items()}
        mine = {p: v for p, v in poss.items() if p in WNPOS}
        if not mine:
            continue
        mine = {p: v for p, v in mine.items() if any(W.synsets(w, pos=x) for x in WNPOS[p])}
        if mine:
            rows.append((min(LV.index(v) for v in mine.values()), -(e[0] or 0), w, sorted(mine, key=lambda p: LV.index(mine[p]))))
    rows.sort()
    return [(w, ps) for _, _, w, ps in rows[:n]]


# ---------- senses ----------
def content(text):  # word stems (first 5 letters): fastener ~ fastening
    return {w[:5] for w in re.findall(r'[a-z]+', text.lower()) if w not in STOP and len(w) > 2}


def kaikki_senses(word, pos):
    rows = lexdb().execute("""select s.id, l.id, s.labels, s.definition,
        (select e.text from examples e where e.sense_id=s.id order by e.ordinal limit 1)
        from lexemes l join senses s on s.lexeme_id=l.id where l.normalized=? and l.pos=? order by s.ordinal""",
                           (word, KPOS[pos])).fetchall()
    out = []
    for sid, lid, labels, definition, example in rows:
        labels = (labels or '').lower()
        if any(t in labels for t in DROP_TAGS) or not definition:
            continue
        out.append({'gloss': definition, 'example': example or '', 'archaic': 'archaic' in labels,
                    'sense_id': sid, 'lexeme_id': lid})
    return out


def lexeme_id(word, pos):
    if pos not in KPOS:  # members may be adverbs: no lexeme row to link
        return None
    r = lexdb().execute('select id from lexemes where normalized=? and pos=? order by id limit 1',
                        (word, KPOS[pos])).fetchone()
    return r[0] if r else None


def link_ok(score, mine):
    """card #1467: one shared stem is a coincidence (house: dwelling ~ dynasty 'family'); need 2, or 1 for a very short gloss."""
    return score >= 2 or (score >= 1 and len(mine) <= 2)


def best_synset(word, pos, gloss):
    best, top = None, 0
    mine = content(gloss) - {word[:5]}
    for ss in [s for x in WNPOS[pos] for s in wordnet().synsets(word, pos=x)]:
        score = len(mine & ((content(ss.definition()) | {l.lower()[:5] for l in ss.lemmas()}) - {word[:5]}))
        if score > top:
            best, top = ss, score
    return best if best is not None and link_ok(top, mine) else None


def is_dated(word, pos, gloss, synonyms):
    """A WordNet sense that matches a Wiktionary dated/archaic sense better than any current one (gay = happy)."""
    rows = lexdb().execute("""select s.labels, s.definition from lexemes l join senses s on s.lexeme_id=l.id
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


def all_senses(word, pos):
    """WordNet synsets (12) + Wiktionary senses (20, not dated/slang/...), duplicates joined."""
    W = wordnet()
    out = [{'gloss': s.definition(), 'example': (s.examples() or [''])[0], 'archaic': False, 'ss': s,
            'src': 'WN', 'sense_id': None} for x in WNPOS[pos] for s in W.synsets(word, pos=x)][:12]
    for k in kaikki_senses(word, pos)[:20]:
        mine = content(k['gloss']) - {word[:5]}
        twin = next((o for o in out if len(mine & ((content(o['gloss']) | (
            {l.lower()[:5] for l in o['ss'].lemmas()} if o['ss'] else set())) - {word[:5]})) >= 2), None) if mine else None
        if twin:
            twin['src'] = 'WN+Wiki'
            twin['sense_id'] = twin['sense_id'] or k['sense_id']
            if not twin['example'] and k['example']:
                twin['example'] = k['example']
            continue
        k['ss'] = best_synset(word, pos, k['gloss'])
        k['src'] = 'Wiki'
        out.append(k)
    taken = {}  # card #1467: a Wiktionary sense id belongs to one sense of this word only
    for s in out:
        if s['sense_id'] is not None:
            if s['sense_id'] in taken:
                s['sense_id'] = None
            else:
                taken[s['sense_id']] = s
    for s in out:  # WordNet-only senses: the closest Wiktionary sense gives the App's senseId
        if s['sense_id'] is None and s['ss'] is not None:
            s['sense_id'] = closest_sense_id(word, pos, s['ss'], set(taken))
            if s['sense_id'] is not None:
                taken[s['sense_id']] = s
    return out


def closest_sense_id(word, pos, ss, taken=()):
    """The Wiktionary sense of word+pos that says the same as the WordNet synset, or None (card #1467).
    Never a dated / slang / vulgar sense (the App must not show them), never one already used, and the match must
    share enough stems (link_ok) -- before, any single shared stem linked long -> 'having a long penis'."""
    rows = lexdb().execute("""select s.id, s.definition, s.labels from lexemes l join senses s on s.lexeme_id=l.id
        where l.normalized=? and l.pos=? order by s.ordinal""", (word, KPOS[pos])).fetchall()
    mine = (content(ss.definition()) | {l.lower()[:5] for l in ss.lemmas() if l.lower() != word}) - {word[:5]}
    best = None
    for sid, definition, labels in rows:
        if sid in taken or not definition or any(t in (labels or '').lower() for t in DROP_TAGS):
            continue
        score = len(mine & (content(definition) - {word[:5]}))
        if link_ok(score, mine) and (best is None or score > best[1]):
            best = (sid, score)
    return best[0] if best else None


# ---------- Qwen ----------
SCHEMA = {'type': 'object', 'properties': {'senses': {'type': 'array', 'maxItems': 8, 'items': {
    'type': 'object', 'properties': {
        'current': {'type': 'boolean'},
        'english_easier': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string'}},
        'english_harder': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string'}}},
    'required': ['current', 'english_easier', 'english_harder']}}}, 'required': ['senses']}


def qwen(word, pos, senses):
    """senses: [(gloss, example)] -> one answer dict per sense (thread-safe: no sqlite / WordNet here)."""
    numbered = '\n'.join(f'{i + 1}. {g}' + (f' Example: "{e}"' if e else '') for i, (g, e) in enumerate(senses))
    prompt = (f'English {pos} "{word}" has these meanings:\n{numbered}\n'
              'For EACH meaning, in the same order, give: "current": true only if people still commonly use '
              f'"{word}" with this meaning today; "english_easier": simpler, more common everyday ENGLISH '
              f'{NAME[pos]} that could REPLACE "{word}" in the example sentence (or a natural sentence with this '
              f'meaning) without changing its meaning; "english_harder": less common, more precise or advanced '
              f'ENGLISH {NAME[pos]} that could replace it the same way. Give up to 6 easier and 6 harder '
              'candidates; a later check removes wrong ones. English single words only, dictionary '
              'form, lowercase; no slang. Reply with JSON only.')
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 1500,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': SCHEMA}}}
    for attempt in range(3):
        try:
            req = urllib.request.Request(ts().LLAMACPP_URL + '/v1/chat/completions', data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json'})
            raw = json.load(model_gate.urlopen(req, timeout=300, source='word_ladder'))['choices'][0]['message']['content'] or '{}'
            return ts().loads_salvaging(raw).get('senses', []) or []
        except Exception as e:  # llama-server busy / restarting: retry, then give up on this word
            err = e
            time.sleep(5 * (attempt + 1))
    print('  qwen failed', word, pos, err, flush=True)
    return None


# ---------- filter ----------
def inflected(x, word, others):
    for suf, rep in (('ies', 'y'), ('es', ''), ('s', ''), ('ing', ''), ('ing', 'e'), ('ed', ''), ('ed', 'e'), ('d', '')):
        if x.endswith(suf) and x[:-len(suf)] + rep in ({word} | set(others)):
            return True
    return False


def norm_spelling(w):
    for a, b in (('ise', 'ize'), ('isation', 'ization'), ('our', 'or'), ('llery', 'lry'), ('ellery', 'elry'),
                 ('tre', 'ter'), ('ogue', 'og'), ('lled', 'led'), ('lling', 'ling'), ('ae', 'e'), ('oe', 'e')):
        w = w.replace(a, b)
    return w


def spelling_variant(x, word):
    return x != word and norm_spelling(x) == norm_spelling(word)


def offensive(x):
    rows = lexdb().execute("""select s.labels from lexemes l join senses s on s.lexeme_id=l.id
        where l.normalized=?""", (x,)).fetchall()
    tagged = [r[0] for r in rows if r[0] and any(t in r[0].lower() for t in BADTAGS)]
    if x in BLOCK:
        return True
    return bool(rows) and (len(tagged) == len(rows) or any(
        'offensive' in (r or '').lower() or 'derogatory' in (r or '').lower() for r in tagged))


def adverbs(adj):
    """WordNet adverbs made from an adjective (quick -> quickly)."""
    W, out = wordnet(), set()
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


def broader(ss, depth=2):
    out, frontier = set(), [ss]
    for _ in range(depth):
        nxt = []
        for s in frontier:
            for r in s.hypernyms():
                out |= {l.lower() for l in r.lemmas()}
                nxt.append(r)
        frontier = nxt
    return out


def antonyms_of(word, pos):
    W, out = wordnet(), set()
    for x in WNPOS[pos]:
        for ss in W.synsets(word, pos=x):
            for s in ss.senses():
                if s.word().lemma().lower() == word:
                    out |= {a.word().lemma().lower() for a in s.get_related('antonym')}
            for sim in ss.get_related('similar'):  # adjective clusters: antonyms of similar heads
                for s in sim.senses():
                    out |= {a.word().lemma().lower() for a in s.get_related('antonym')}
    return out


def filter_sense(word, pos, sense, answer, antonyms, stats):
    ss = sense['ss']
    lemmas = [l.lower() for l in ss.lemmas()] if ss else []
    raw = list(answer.get('english_easier') or []) + list(answer.get('english_harder') or []) + lemmas
    stats['qwen'] += len(raw)
    far = broader(ss) if ss else set()
    words, broad_set, adv_from = [], set(), {}
    for x in raw:
        x = x.strip().lower()
        if x == word or x in words or ' ' in x or '-' in x or (x in GENERAL and x not in lemmas):
            continue
        if (inflected(x, word, words) or not row_of(x, pos) or spelling_variant(x, word)
                or any(spelling_variant(x, y) for y in words) or offensive(x) or x in antonyms):
            continue
        z = ts()._wordfreq_zipf(x) or 0
        if x not in lemmas and (z < 2.5 or (ACADEMIC.search(x) and not info(x) and z < 3.5)):
            continue
        if x in far and x not in lemmas:
            broad_set.add(x)
        words.append(x)
    if pos == 'adjective':
        for x in [word] + [l for l in lemmas if l in words]:
            for adv in sorted(adverbs(x)):
                if adv not in words and common(adv):
                    words.append(adv)
                    adv_from[adv] = x
    return [{'w': x, 'level': level(x, 'adverb' if x in adv_from else pos), 'adverb': x in adv_from,
             'from': adv_from.get(x), 'broad': x in broad_set} for x in words]


def merge_senses(senses, stats):
    merged = []
    for sense in senses:
        mine = {c['w'] for c in sense['candidates']}
        twin = next((m for m in merged if (sense.get('ssid') and sense['ssid'] == m.get('ssid')) or (
            mine and len(mine & {c['w'] for c in m['candidates']}) >= len(mine) / 3)), None)
        if twin:
            have = {c['w'] for c in twin['candidates']}
            twin['candidates'] += [c for c in sense['candidates'] if c['w'] not in have]
            twin['gloss'] += ' / ' + sense['gloss']
            stats['merged'] += 1
        else:
            merged.append(sense)
    return merged


# ---------- batches ----------
def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding='utf-8'))
    return {'ssid_group': {}, 'done_words': []}


def save_state(st):
    tmp = STATE + '.tmp'
    json.dump(st, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(tmp, STATE)


def prepare(word, pos, st):
    """Sequential (WordNet / sqlite): senses to send to Qwen, senses reusing an existing group."""
    senses = all_senses(word, pos)[:MAX_QWEN_SENSES]
    todo, shared, mine = [], [], set()
    for s in senses:
        ssid = s['ss'].id if s['ss'] else None
        if ssid and ssid in mine:  # two dictionary senses of this word on one synset: merged later
            todo.append(s)
        elif ssid and ssid in st['ssid_group']:
            shared.append({'ssid': ssid, 'senseId': s['sense_id'], 'gloss': s['gloss'], 'group': st['ssid_group'][ssid]})
        else:
            todo.append(s)
            if ssid:
                mine.add(ssid)
                st['ssid_group'][ssid] = 'g_' + ssid  # provisional: this sense starts the group
    return {'word': word, 'pos': pos, 'todo': todo, 'shared': shared, 'lexeme_id': lexeme_id(word, pos)}


def finish(job, answers, stats):
    word, pos = job['word'], job['pos']
    entry = {'word': word, 'pos': pos, 'level': level(word, pos), 'lexemeId': job['lexeme_id'],
             'senses': [], 'old': [], 'shared': job['shared']}
    antonyms = antonyms_of(word, pos)
    for i, sense in enumerate(job['todo']):
        a = answers[i] if answers and i < len(answers) else {}
        ss = sense['ss']
        if (sense['archaic'] and a.get('current') is False) or (ss and is_dated(word, pos, ss.definition(), [])):
            entry['old'].append(sense['gloss'])
            continue
        cands = filter_sense(word, pos, sense, a, antonyms, stats)
        entry['senses'].append({'ssid': ss.id if ss else None, 'senseId': sense['sense_id'], 'gloss': sense['gloss'],
                                'example': sense['example'], 'src': sense['src'],
                                'group': ('g_' + ss.id) if ss else None, 'candidates': cands})
    entry['senses'] = merge_senses(entry['senses'], stats)
    stats['to_claude'] += sum(len(x['candidates']) for x in entry['senses'])
    return entry


def compact(entry):
    """Claude-facing format: one string per candidate, 'word|LV' plus ' adv<-x' / ' broad'."""
    def cand(c):
        return c['w'] + '|' + c['level'] + (f"|adv<-{c['from']}" if c['adverb'] else '') + ('|broad' if c['broad'] else '')
    return {'word': entry['word'], 'pos': entry['pos'], 'level': entry['level'], 'lexemeId': entry['lexemeId'],
            'senses': [{'ssid': s['ssid'], 'senseId': s['senseId'], 'group': s['group'], 'gloss': s['gloss'],
                        'example': s['example'], 'cands': [cand(c) for c in s['candidates']]} for s in entry['senses']],
            'shared': entry['shared'], 'old': entry['old']}


def in_night():
    t = datetime.now(timezone(timedelta(hours=8)))
    return 1 <= t.hour < 7


def run_words(items, st, stats):
    """items: [(word, pos)] -> entries. 4 Qwen requests at once."""
    ts()
    jobs = [prepare(w, p, st) for w, p in items]
    t = time.time()
    with ThreadPoolExecutor(SLOTS) as pool:
        futs = [pool.submit(qwen, j['word'], j['pos'], [(s['gloss'], s['example']) for s in j['todo']]) if j['todo'] else None
                for j in jobs]
        answers = [f.result() if f else [] for f in futs]
    stats['qwen_seconds'] += round(time.time() - t, 1)
    return [finish(j, a, stats) for j, a in zip(jobs, answers)]


def cmd_run(args):
    if not (in_night() or args.force_day):
        sys.exit('Qwen runs only 01:00-07:00 Taipei (owner 11/27); use --force-day for a test')
    words = pick_words()
    items = [(w, p) for w, ps in words for p in ps]
    os.makedirs(OUT, exist_ok=True)
    st = load_state()
    batches = [words[i:i + BATCH_SIZE] for i in range(0, len(words), BATCH_SIZE)]
    ran = 0
    for n, batch in enumerate(batches, 1):
        path = os.path.join(OUT, f'qwen_batch_{n:02d}.json')
        if os.path.exists(path) or (args.batch and n != args.batch):
            continue
        if args.limit_batches and ran >= args.limit_batches:
            break
        if not (in_night() or args.force_day):
            print('night window over, stop (rerun resumes)')
            break
        stats = {'qwen': 0, 'to_claude': 0, 'merged': 0, 'qwen_seconds': 0.0}
        t = time.time()
        entries = run_words([(w, p) for w, ps in batch for p in ps], st, stats)
        doc = {'batch': n, 'words': [w for w, _ in batch], 'stats': stats, 'seconds': round(time.time() - t, 1),
               'entries': [compact(e) for e in entries]}
        json.dump(doc, open(path + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        os.replace(path + '.tmp', path)
        save_state(st)
        ran += 1
        print(f'batch {n:02d}: {len(batch)} words, {len(entries)} entries, {stats}, {doc["seconds"]}s', flush=True)


# ---------- lean review (owner 11/27: fewer tokens, faster) ----------
# The reviewer (Codex) reads one short text file and writes one TSV line per sense; member Chinese comes
# from ECDICT here, so the reviewer writes Chinese only for each sense. Shared senses are not reviewed.
ECDICT = os.path.join(ROOT, 'lexicon', 'raw-data', 'ecdict.sqlite3')
ECPOS = {'noun': ('n.',), 'verb': ('v.', 'vt.', 'vi.'), 'adjective': ('a.', 'adj.'), 'adverb': ('ad.', 'adv.')}
_ecd = None


def ecdict_zh(w, pos):
    """ECDICT's first meaning for this part of speech, Taiwan wording ('' when none)."""
    global _ecd, _CC
    if _ecd is None:
        import opencc
        _ecd, _CC = sqlite3.connect(ECDICT), opencc.OpenCC('s2twp')
    r = _ecd.execute('select translation from e where lower=? limit 1', (w.lower(),)).fetchone()
    for line in re.split(r'\\n|\n', (r[0] or '') if r else ''):
        line = line.strip()
        if line.startswith(ECPOS[pos]):
            t = re.sub(r'^[a-z]+\.\s*', '', line)
            t = re.sub(r'\[[^\]]*\]|（[^）]*）|\([^)]*\)', '', t)
            return _CC.convert(re.split(r'[，,；;]', t)[0].strip())[:8]
    return ''


def ranked(cands):
    """WordNet lemmas (not broad) first, then Qwen's order; at most PACK_CANDS."""
    return sorted(cands, key=lambda c: ('|broad' in c, ))[:PACK_CANDS]


_gl = {}


def glosses(x, pos):
    """Every definition of x in this part of speech (WordNet + Wiktionary)."""
    if (x, pos) not in _gl:
        W = wordnet()
        g = [s.definition() for p in WNPOS[pos] for s in W.synsets(x, pos=p)]
        g += [r[0] for r in lexdb().execute("""select s.definition from lexemes l join senses s on s.lexeme_id=l.id
              where l.normalized=? and l.pos=?""", (x, KPOS[pos])).fetchall()]
        _gl[(x, pos)] = g
    return _gl[(x, pos)]


def plausible(word, pos, ssid, x):
    """Dictionary-only prefilter (eval_methods.py on batch 00: keeps 88 % of the words both reviewers kept,
    drops 57 % of Qwen's candidates): same synset / 'similar' neighbour, or x's own definitions name the
    headword or a sense lemma, or Wu-Palmer similarity >= 0.8."""
    if not ssid:
        return True
    import wn.similarity as sim
    W = wordnet()
    ss = W.synset(ssid)
    lem = {l.lower() for l in ss.lemmas()}
    near = ss.get_related('similar') + ss.get_related('also') + ss.get_related('verb_group')
    if x in lem or any(x in {l.lower() for l in n.lemmas()} for n in near):
        return True
    keys = ({word} | {l for l in lem if ' ' not in l}) - {x}
    pat = re.compile(r'\b(' + '|'.join(map(re.escape, keys)) + r')(s|es|ed|d|ing)?\b')
    if any(pat.search(g.lower()) for g in glosses(x, pos)):
        return True
    for p in WNPOS[pos]:
        for s in W.synsets(x, pos=p):
            try:
                if sim.wup(ss, s, simulate_root=True) >= 0.8:
                    return True
            except Exception:
                pass
    return False


def prefiltered(entry):
    for s in entry['senses']:
        s['cands'] = [c for c in s['cands'] if '|adv<-' in c or plausible(entry['word'], entry['pos'], s.get('ssid'), c.split('|')[0])]
    return entry


def pack_text(doc):
    lines = [f"# batch {doc['batch']:02d}. One block per word/pos; numbered lines = senses to review.",
             '# gloss :: example || candidates (* wider word, ~ adverb)']
    for e in doc['entries']:
        lines.append(f"{e['word']}/{e['pos']} {e['level']}")
        for i, s in enumerate(e['senses'], 1):
            ex = (s.get('example') or '')[:50]
            gloss = s['gloss'].split(' / ')[0][:70]
            cands = [c.split('|')[0] + ('*' if '|broad' in c else '') + ('~' if '|adv<-' in c else '') for c in ranked(s['cands'])]
            lines.append(f" {i} {gloss}" + (f' :: {ex}' if ex else '') + ' || ' + ' '.join(cands))
        for s in e.get('shared') or []:
            lines.append(f" = {s['gloss'][:60]} (shared, no review)")
    return '\n'.join(lines) + '\n'


def cmd_pack(args):
    n = args.batch
    doc = json.load(open(os.path.join(OUT, f'qwen_batch_{n:02d}.json'), encoding='utf-8'))
    if not args.no_prefilter:
        doc['entries'] = [prefiltered(e) for e in doc['entries']]
    path = os.path.join(OUT, f'review_batch_{n:02d}.txt')
    open(path, 'w', encoding='utf-8').write(pack_text(doc))
    print(path, os.path.getsize(path), 'bytes')


def member_pos(x, pos):
    if pos != 'adjective':
        return pos
    return 'adverb' if row_of(x, pos) == 'adverb' else 'adjective'


def apply_review(doc, tsv, reviewer):
    """review TSV: word/pos <TAB> sense number | + (new sense) | -n (drop) <TAB> zh <TAB> members (space; w=中文 overrides ECDICT)."""
    by = {}
    for raw in tsv.splitlines():
        if not raw.strip() or raw.startswith('#'):
            continue
        parts = raw.rstrip('\n').split('\t') + ['', '', '']
        by.setdefault(parts[0].strip(), []).append([p.strip() for p in parts[1:4]])
    words, unreviewed = [], []
    for e in doc['entries']:
        key, rows = f"{e['word']}/{e['pos']}", by.get(f"{e['word']}/{e['pos']}")
        if rows is None:
            unreviewed.append(key)
            continue
        senses = [{'group': s['group'], 'senseId': s['senseId'], 'shared': True} for s in e.get('shared') or []]
        for n, zh, members in rows:
            if n.startswith('-'):
                continue
            src = e['senses'][int(n) - 1] if n.isdigit() and 0 < int(n) <= len(e['senses']) else None
            ms = []
            for x in dict.fromkeys(members.replace(',', ' ').split()):
                x, _, own = x.partition('=')  # adore=非常喜歡: the reviewer's Chinese when ECDICT's is off
                x = x.lower()
                if x != e['word']:
                    p = member_pos(x, e['pos'])
                    ms.append({'w': x, 'pos': p, 'zh': own or ecdict_zh(x, p), 'zh_source': 'AI' if own else 'ECDICT'})
            senses.append({'ssid': src['ssid'] if src else None, 'senseId': src['senseId'] if src else None,
                           'group': (src['group'] if src and src['group'] else
                                     f"g_b{doc['batch']:02d}_{e['word']}_{e['pos']}_{len(senses)}"),
                           'zh': zh, 'zh_source': 'AI', 'members': ms})
        words.append({'word': e['word'], 'pos': e['pos'], 'senses': senses})
    return {'batch': doc['batch'], 'reviewer': reviewer, 'words': words}, unreviewed


def cmd_apply(args):
    n = args.batch
    doc = json.load(open(os.path.join(OUT, f'qwen_batch_{n:02d}.json'), encoding='utf-8'))
    tsv = open(os.path.join(OUT, f'review_batch_{n:02d}{args.suffix}.tsv'), encoding='utf-8').read()
    out, missing = apply_review(doc, tsv, args.reviewer)
    path = os.path.join(OUT, f'checked_batch_{n:02d}{args.suffix}.json')
    json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ns = sum(len(w['senses']) for w in out['words'])
    nm = sum(len(s.get('members') or []) for w in out['words'] for s in w['senses'])
    print(path, len(out['words']), 'entries', ns, 'senses', nm, 'members; not reviewed:', missing[:20])


def lean_instructions(n, suffix=''):
    """Check-card text (owner 11/27: fewer tokens). Read only the short pack, write only the TSV."""
    d = 'lexicon/raw-data/word_ladder/'
    return (f'只讀 {d}review_batch_{n:02d}.txt（不要讀 qwen_batch 或其他檔，不要寫例句、稽核檔或說明），'
            f'只寫 {d}review_batch_{n:02d}{suffix}.tsv，然後執行 python lexicon/tools/word_ladder.py apply {n}'
            + (f' --suffix {suffix}' if suffix else '') + '。\n'
            'TSV 每行：word/pos<TAB>意思編號<TAB>這個意思的台灣中文（AI）<TAB>同義字（空格分隔）。\n'
            '- 每個編號都要有一行；要刪的意思寫 -編號（例：like/verb<TAB>-3）；漏掉的常用意思寫 +。\n'
            '- 同義字：能在例句裡直接替換的才留，名詞→名詞、動詞→動詞、形容詞→形容詞或副詞；可以補字。'
            '每個意思盡量 3–8 個，簡單（A1–B1）和難（B2–C2）都要，讓難度條有字可換。\n'
            '- 常用基本意思即使沒有同義字也要留（第四欄空白），例：white 白色的、right 右邊、back 後面；'
            '冷門或過時意思才刪（gay＝快樂、number＝表演節目）。\n'
            '- 同義字的中文由程式從 ECDICT 帶入；只有 ECDICT 的意思明顯不對時才寫 字=中文（例 adore=非常喜歡）。\n'
            '- 標 = 的意思已和別的字共用一組，不用寫。\n'
            '在 result.md 寫開始與結束時間。')


# ---------- board ----------
def api(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode('utf-8') if body is not None else None,
                                 headers={'Content-Type': 'application/json; charset=utf-8'})
    return json.load(urllib.request.urlopen(req, timeout=30))


def cmd_open_issues(_):
    issues = api('GET', '/api/issues')
    issues = (issues.get('items') or issues.get('issues') or []) if isinstance(issues, dict) else issues
    have = {i.get('title', '') for i in issues}
    for fn in sorted(os.listdir(OUT)):
        m = re.fullmatch(r'qwen_batch_(\d+)\.json', fn)
        if not m:
            continue
        n = int(m.group(1))
        doc = json.load(open(os.path.join(OUT, fn), encoding='utf-8'))
        title = f'[上下游檢查] 批次 {n:02d}（{len(doc["words"])} 字）'
        if title in have or os.path.exists(os.path.join(OUT, f'checked_batch_{n:02d}.json')):
            continue
        body = lean_instructions(n)
        r = api('POST', '/api/issues', {'title': title, 'kind': 'todo', 'area': 'data', 'difficulty': 3,
                                        'detail': body, 'by': 'card1450'})
        print('opened', title, r.get('id') if isinstance(r, dict) else r)


# ---------- sense-id links (card #1467) ----------
def link_problem(lid, sense_id, gloss):
    """Why this senseId must not stay on a ladder sense (None = fine): wrong lexeme, dropped label, no shared meaning."""
    r = lexdb().execute('select s.lexeme_id, s.definition, s.labels from senses s where s.id=?', (sense_id,)).fetchone()
    if not r:
        return 'missing'
    if lid and r[0] != lid:
        return 'other-lexeme'
    if any(t in (r[2] or '').lower() for t in DROP_TAGS):
        return 'dropped-label'
    mine = content(gloss or '')
    if mine and not link_ok(len(mine & content(r[1] or '')), mine):
        return 'meaning-differs'
    return None


def library_links():
    """[(file, word, pos, sense dict)] over every checked batch."""
    out = []
    for fn in sorted(os.listdir(OUT)):
        if re.fullmatch(r'checked_batch_\d+\.json', fn):
            doc = json.load(open(os.path.join(OUT, fn), encoding='utf-8'))
            out += [(fn, w, s) for w in doc['words'] for s in w.get('senses', [])]
    return out


def cmd_audit(_):
    """Measure the whole library: wrong / shared senseIds in the checked batches (read only)."""
    kind, owners, n = {}, {}, 0
    gloss_of = {}
    for fn in sorted(os.listdir(OUT)):
        if re.fullmatch(r'qwen_batch_\d+\.json', fn):
            for e in json.load(open(os.path.join(OUT, fn), encoding='utf-8')).get('entries', []):
                for x in e.get('senses', []):
                    gloss_of[(e['word'], e['pos'], x.get('ssid'))] = x.get('gloss')
    for fn, w, s in library_links():
        if not s.get('senseId'):
            continue
        n += 1
        lid = lexeme_id(w['word'], w['pos'])
        owners.setdefault((lid, s['senseId']), set()).add(s.get('ssid'))
        gloss = gloss_of.get((w['word'], w['pos'], s.get('ssid')))
        if not gloss and s.get('ssid'):
            try:
                gloss = wordnet().synset(s['ssid']).definition()
            except Exception:
                gloss = None
        why = link_problem(lid, s['senseId'], gloss)
        if why:
            kind.setdefault(why, []).append(f"{w['word']}/{w['pos']}:{s['senseId']}")
    shared = {k: v for k, v in owners.items() if len(v) > 1}
    print('links', n, '| problems', {k: len(v) for k, v in kind.items()}, '| senseIds shared by >1 synset', len(shared))
    for k, v in kind.items():
        print(' ', k, v[:12])


def cmd_relink(_):
    """Re-derive every senseId in the checked batches with the strict matching (backup first, only senseId changes)."""
    bk = os.path.join(OUT, 'card1467_backup')
    os.makedirs(bk, exist_ok=True)
    changed = dropped = 0
    for fn in sorted(os.listdir(OUT)):
        if not re.fullmatch(r'checked_batch_\d+\.json', fn):
            continue
        path = os.path.join(OUT, fn)
        if not os.path.exists(os.path.join(bk, fn)):
            shutil.copyfile(path, os.path.join(bk, fn))
        doc = json.load(open(path, encoding='utf-8'))
        for w in doc['words']:
            fresh = {x['ss'].id: x['sense_id'] for x in all_senses(w['word'], w['pos']) if x['ss'] is not None}
            for s in w.get('senses', []):
                new = fresh.get(s.get('ssid'))
                if new != s.get('senseId'):
                    changed += 1
                    dropped += new is None
                    s['senseId'] = new
        tmp = path + '.tmp'
        json.dump(doc, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(tmp, path)
    print('senseIds changed', changed, '(set to none:', dropped, ')')


# ---------- App asset ----------
def cmd_build_app(_):
    senses, groups, clashes = {}, {}, []
    for fn in sorted(os.listdir(OUT)):
        if not re.fullmatch(r'checked_batch_\d+\.json', fn):
            continue
        doc = json.load(open(os.path.join(OUT, fn), encoding='utf-8'))
        for w in doc['words']:
            lid = lexeme_id(w['word'], w['pos'])
            for s in w.get('senses', []):
                gid = s.get('group') or ('g_' + str(s.get('ssid')))
                grp = groups.setdefault(gid, {})
                grp[(w['word'], w['pos'])] = {'lemma': w['word'], 'pos': w['pos'], 'cefr': level(w['word'], w['pos']), 'lexemeId': lid}
                for m in s.get('members', []):
                    grp[(m['w'], m['pos'])] = {'lemma': m['w'], 'pos': m['pos'], 'cefr': level(m['w'], m['pos']),
                                               'lexemeId': lexeme_id(m['w'], m['pos'])}
                if lid and s.get('senseId') and not link_problem(lid, s['senseId'], None):
                    key = f"{lid}:{s['senseId']}"
                    if senses.setdefault(key, gid) != gid:  # card #1467: first ladder keeps the sense, no overwrite
                        clashes.append(key)
    doc = {'senses': senses, 'groups': {g: list(m.values()) for g, m in groups.items() if len(m) > 1}}
    doc['senses'] = {k: g for k, g in senses.items() if g in doc['groups']}
    json.dump(doc, open(APP_ASSET, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('sense clashes kept as first', len(clashes))
    print('app asset', len(doc['senses']), 'senses', len(doc['groups']), 'groups', os.path.getsize(APP_ASSET), 'bytes')


def cmd_words(_):
    words = pick_words()
    items = sum(len(ps) for _, ps in words)
    print(len(words), 'words', items, 'word+pos entries', len(words) // BATCH_SIZE + 1, 'batches')
    by = {}
    for w, ps in words:
        by[level(w, ps[0])] = by.get(level(w, ps[0]), 0) + 1
    print(by)
    print(' '.join(w for w, _ in words[:40]), '...', ' '.join(w for w, _ in words[-20:]))


def cmd_sample(args):
    words = pick_words()
    random.seed(args.seed)
    pick = random.sample(words, args.n)
    st = {'ssid_group': {}, 'done_words': []}
    stats = {'qwen': 0, 'to_claude': 0, 'merged': 0, 'qwen_seconds': 0.0}
    out = []
    for i in range(0, len(pick), 4):
        for e in run_words([(w, ps[0]) for w, ps in pick[i:i + 4]], st, stats):
            out.append(compact(e))
    json.dump({'stats': stats, 'entries': out}, open(os.path.join(OUT, 'sample.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(stats)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('words')
    r = sub.add_parser('run')
    r.add_argument('--batch', type=int)
    r.add_argument('--limit-batches', type=int)
    r.add_argument('--force-day', action='store_true')
    sub.add_parser('open-issues')
    sub.add_parser('build-app')
    sub.add_parser('audit')
    sub.add_parser('relink')
    s = sub.add_parser('sample')
    s.add_argument('n', type=int)
    s.add_argument('--seed', type=int, default=1450)
    pk = sub.add_parser('pack')
    pk.add_argument('batch', type=int)
    pk.add_argument('--no-prefilter', action='store_true')
    ar = sub.add_parser('apply')
    ar.add_argument('batch', type=int)
    ar.add_argument('--suffix', default='')
    ar.add_argument('--reviewer', default='Codex')
    a = ap.parse_args()
    {'pack': cmd_pack, 'apply': cmd_apply, 'words': cmd_words, 'run': cmd_run, 'open-issues': cmd_open_issues, 'build-app': cmd_build_app, 'audit': cmd_audit, 'relink': cmd_relink, 'sample': cmd_sample}[a.cmd](a)
