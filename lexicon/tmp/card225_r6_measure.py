"""card225 r6: photo tags that point at a form-of lexeme (all senses are 'present participle of…' etc.)."""
import json,sys,re,collections as C
p=json.load(open(sys.argv[1],encoding='utf8'))
lex={l['id']:l for l in p['lexemes']}
FORM=re.compile(r'^(present participle|simple past|past participle|third-person singular|plural of|comparative|superlative)',re.I)
def formof(l):
  ss=l.get('senses',[]); return bool(ss) and all(FORM.match((s.get('gloss') or s.get('definition') or '').strip()) for s in ss)
fo={i for i,l in lex.items() if formof(l)}
tags=[(im,t) for im in p['catalog_images'] for t in im.get('tags',[]) if t.get('review_status')=='approved']
hit=[(im,t) for im,t in tags if t['lexeme_id'] in fo]
c=C.Counter((lex[t['lexeme_id']]['lemma'],lex[t['lexeme_id']]['pos']) for im,t in hit)
print('form-of lexemes',len(fo),'| tags on them',len(hit),'imgs',len({im['id'] for im,t in hit}),'lemmas',len(c),'| no cefr among them',sum(1 for im,t in hit if not t.get('cefr')))
print(c.most_common(15))
lemmas_with_other={(l['lemma']) for i,l in lex.items() if i not in fo}
print('of these lemmas, also have a non-form-of lexeme (adj/noun) with same spelling:',sum(1 for (w,_) in c if w in lemmas_with_other))
