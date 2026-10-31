"""Pick English example sentences from our pack that also have a human recording on Tatoeba."""
import json, os, time, urllib.parse, urllib.request
WORDS = ['cat', 'house', 'eat', 'water', 'book', 'friend', 'school', 'happy', 'weather', 'remember']
pack = json.load(open(os.environ['TEMP'] + '/p.json', encoding='utf-8'))
ours = {x['lemma']: [e['text'] for e in x.get('examples') or []] for x in pack['lexemes'] if x['lemma'] in WORDS}
picked = []
for w in WORDS:
    found = None
    for page in (1, 2, 3):
        q = urllib.parse.urlencode({'from': 'eng', 'has_audio': 'yes', 'query': f'={w}', 'sort': 'words', 'page': page})
        res = json.load(urllib.request.urlopen(f'https://tatoeba.org/en/api_v0/search?{q}', timeout=30))['results']
        mine = set(ours.get(w, []))
        for r in res:
            if r['text'] in mine and r.get('audios') and len(r['text'].split()) >= 5:
                found = r; break
        if found or not res:
            break
        time.sleep(1)
    if found:
        a = found['audios'][0]
        picked.append({'word': w, 'text': found['text'], 'tatoeba_id': found['id'], 'audio_id': a['id'],
                       'author': a.get('author'), 'license': a.get('license')})
        print(w, '|', found['text'], '|', a.get('author'))
    else:
        print(w, '| no match in pack')
    time.sleep(1)
json.dump(picked, open('picked.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
