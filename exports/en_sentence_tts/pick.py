"""Pick English example sentences from our pack that also have a human recording on Tatoeba."""
import json, os, time, urllib.parse, urllib.request
WORDS = ['cat', 'house', 'eat', 'water', 'book', 'friend', 'school', 'happy', 'weather', 'remember']
pack = json.load(open(os.environ['TEMP'] + '/p.json', encoding='utf-8'))
ours = {x['lemma']: [e for e in x.get('examples') or [] if e.get('source') == 'tatoeba'] for x in pack['lexemes'] if x['lemma'] in WORDS}
picked = []
for w in WORDS:
    found = None
    for e in ours.get(w, [])[:12]:
        q = urllib.parse.urlencode({'from': 'eng', 'has_audio': 'yes', 'query': '"' + e['text'] + '"'})
        res = json.load(urllib.request.urlopen(f'https://tatoeba.org/en/api_v0/search?{q}', timeout=30))['results']
        time.sleep(1)
        hit = next((r for r in res if r['text'] == e['text'] and r.get('audios')), None)
        if hit:
            found = (hit, e); break
    if found:
        hit, e = found
        a = hit['audios'][0]
        picked.append({'word': w, 'text': hit['text'], 'zh': e.get('translation'), 'tatoeba_id': hit['id'],
                       'audio_id': a['id'], 'author': a.get('author'), 'license': a.get('license')})
        print(w, '|', hit['text'], '|', a.get('author'))
    else:
        print(w, '| none of', len(ours.get(w, [])), 'tatoeba sentences has audio (first 12 checked)')
json.dump(picked, open('picked.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
