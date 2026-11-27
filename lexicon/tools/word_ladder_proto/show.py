import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print(d['stats'])
for e in d['words']:
  print('##',e['word'],e['pos'],e['level'],e['seconds'],'s old:',[o[:40] for o in e['old']])
  for s in e['senses']: print('  -',s['gloss'][:90],'| ex:',s['example'][:40],'|',', '.join(c['w']+'('+c['level']+(',BROAD' if c.get('broad') else '')+(',adv<-'+str(c.get('from')) if c['adverb'] else '')+')' for c in s['candidates']))
