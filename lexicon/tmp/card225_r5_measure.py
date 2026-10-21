import json,sys,collections as C
p=json.load(open(sys.argv[1],encoding='utf8'))
lex={l['id']:l for l in p['lexemes']}
lem={l['lemma'] for l in p['lexemes']}
imgs=p['catalog_images']
tags=[(i,t) for i in imgs for t in i.get('tags',[]) if t.get('review_status')=='approved']
def base(w):
  for suf,rep in [('ing',''),('ing','e'),('ed',''),('ed','e'),('d','')]:
    if w.endswith(suf) and len(w)-len(suf)>=3:
      b=w[:-len(suf)]+rep
      if b in lem and b!=w: return b
  if len(w)>4 and w[-3]==w[-4] and w.endswith(('ing',)) and w[:-4] in lem: return w[:-4]
  return None
infl={l['lemma']:base(l['lemma']) for l in p['lexemes'] if base(l['lemma'])}
print('lexemes',len(lex),'inflection-like lemmas',len(infl))
ti=C.Counter(lex[t['lexeme_id']]['lemma'] for i,t in tags if lex[t['lexeme_id']]['lemma'] in infl)
print('tags on inflection-like lemmas',sum(ti.values()),'imgs',len({i['id'] for i,t in tags if lex[t['lexeme_id']]['lemma'] in infl}))
print('top',[(w,n,infl[w]) for w,n in ti.most_common(12)])
both=sum(1 for i in imgs if (ls:={lex[t['lexeme_id']]['lemma'] for t in i.get('tags',[]) if t.get('review_status')=='approved'}) and any(w in infl and infl[w] in ls for w in ls))
print('imgs having both base and inflected tag',both)
cap=[l['lemma'] for l in p['lexemes'] if l['lemma'][:1].isupper()]
capt=C.Counter(lex[t['lexeme_id']]['lemma'] for i,t in tags if lex[t['lexeme_id']]['lemma'][:1].isupper())
print('capitalized lemmas',len(cap),'tags',sum(capt.values()),capt.most_common(10))
