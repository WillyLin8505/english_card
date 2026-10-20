import json,re,statistics as st,collections as C,sys
p=json.load(open(sys.argv[1],encoding='utf8'))
lex={l['id']:l for l in p['lexemes']}
imgs=p['catalog_images']
brk=re.compile(r'[\s\-–—/、，,；;：:（）()「」]+')
def tags(i): return [t for t in i.get('tags',[]) if t.get('review_status')=='approved']
def native(t):
  w=lex.get(t['lexeme_id']); 
  if not w: return None,''
  s=[x for x in w['senses'] if x['id']==t.get('sense_id')]
  return w, (s[0].get('native') if s else None) or ''
def tm(t,q):
  w,n=native(t)
  if not w: return None
  best=None
  for text in [w['lemma'],n]:
    tt=text.strip().lower()
    for part in [tt,*brk.split(tt)]:
      if part==q: return 0
      if part.startswith(q): best=1
  return best
def im(i,q):
  b=None
  for t in tags(i):
    m=tm(t,q)
    if m is not None and (b is None or m<b): b=m
    if b==0: break
  return b
qs='cat ant rat car pen man sun cup bag hat bed dog box egg map art bus ice tea toy'.split()
tot=ex=0
for q in qs:
  r=[im(i,q) for i in imgs]; e=r.count(0); pr=r.count(1); tot+=e+pr; ex+=e
  print(q,'exact',e,'prefix',pr)
print('total',tot,'exact',ex)
# tags per image, distinct lemmas, unknown lexeme
n=[len(tags(i)) for i in imgs]
print('imgs',len(imgs),'tags/img median',st.median(n),'p90',sorted(n)[int(.9*len(n))],'zero',n.count(0))
miss=sum(1 for i in imgs for t in tags(i) if t['lexeme_id'] not in lex)
print('tags w/o lexeme in pack',miss,'of',sum(n))
nolvl=sum(1 for i in imgs for t in tags(i) if not (t.get('cefr') or (lex.get(t['lexeme_id']) or {}).get('cefr')))
print('tags w/o level',nolvl)
nonat=sum(1 for i in imgs for t in tags(i) if t['lexeme_id'] in lex and not native(t)[1])
print('tags w/o native',nonat)
# duplicate lemma on same image
dup=sum(1 for i in imgs if len({lex[t['lexeme_id']]['lemma'] for t in tags(i) if t['lexeme_id'] in lex})<len([t for t in tags(i) if t['lexeme_id'] in lex]))
print('imgs with duplicate lemma tags',dup)
# per level images
lv=C.Counter()
for i in imgs:
  for L in {(t.get('cefr') or '').upper() for t in tags(i)}: lv[L]+=1
print('imgs per level',dict(lv))
print('---dups')
k=0
for i in imgs:
  ts=[t for t in tags(i) if t['lexeme_id'] in lex]
  c=C.Counter(lex[t['lexeme_id']]['lemma'] for t in ts)
  d=[l for l,v in c.items() if v>1]
  if d and k<8:
    k+=1
    for l in d:
      print(i['id'],[(lex[t['lexeme_id']]['pos'],native(t)[1],t.get('cefr'),t.get('origin')) for t in ts if lex[t['lexeme_id']]['lemma']==l])
same=0
for i in imgs:
  ts=[t for t in tags(i) if t['lexeme_id'] in lex]
  c=C.Counter((lex[t['lexeme_id']]['lemma'],native(t)[1]) for t in ts)
  same+=sum(v-1 for v in c.values() if v>1)
print('identical lemma+native dup tags',same)
for q in ['ant','bus','car']:
  c=C.Counter()
  for i in imgs:
    if im(i,q)==1:
      for t in tags(i):
        if tm(t,q)==1: c[lex[t['lexeme_id']]['lemma']]+=1
  print(q,c.most_common(8))
