import sys, collections
sys.path.insert(0,"lexicon/backend"); sys.path.insert(0,"lexicon/tools"); sys.stdout.reconfigure(encoding="utf-8")
sys.argv=['x']
import card381_translations as T
from app.adapters.base import Context
from app.adapters.kaikki import _gloss, _pos
from sqlalchemy import text
from app import db

def table_sizes(lemma):
    ents=T.entries_of(lemma) or []
    ctx=Context("en","zh-TW",lemma,lemma)
    senses=T.AD.senses(ents,ctx)
    langs=collections.defaultdict(set)
    for e in ents:
        pos=_pos(e); raw=e.get("senses",[])
        home={id(x["sense"]):x["sense_key"] for x in senses if x["entry"] is e}
        first=next((x for x in senses if x["pos"]==pos),None)
        trs=list(e.get("translations",[]))
        for x in raw: trs+=[dict(t,sense=t.get("sense") or _gloss(x)) for t in x.get("translations",[])]
        groups=collections.defaultdict(set); rep={}
        for t in trs:
            if t.get("word") and t.get("lang_code"):
                key=(t.get("sense"),t.get("_dis1")); groups[key].add(t["lang_code"]); rep[key]=t
        for key,ls in groups.items():
            k,_=T.AD.place_translation(rep[key],senses,raw,home,first,pos)
            if k: langs[k]|=ls
    return {k:len(v) for k,v in langs.items()}, senses

words=sys.argv[1:] if len(sys.argv)>1 else None
with db.SessionLocal() as s:
    rows=s.execute(text("select l.lemma,l.pos,sn.sense_key,sn.ordinal,sn.labels,(select d.text from definitions d where d.sense_id=sn.id and d.language='en' order by d.id limit 1) from lexemes l join senses sn on sn.lexeme_id=l.id where l.language='en' and l.status='full' and l.cefr in ('A1','A2') order by l.lemma,l.pos,sn.ordinal")).all()
by=collections.OrderedDict()
for r in rows: by.setdefault((r[0],r[1]),[]).append(r)
n=0; prom=0
for (lemma,pos),ss in by.items():
    if len(ss)<2: continue
    sizes,_=table_sizes(lemma)
    t=[sizes.get(r[2],0) for r in ss]
    t0=t[0]; j=max(range(len(t)),key=lambda i:t[i])
    if j>0 and t0>=1 and t[j]>=15 and t[j]>=2*t0:
        prom+=1
        if prom<=400: print(f"{lemma:10} {pos:5} s0[{t0}] {(ss[0][5] or '')[:45]:45} | s{j}[{t[j]}] {(ss[j][5] or '')[:50]}")
print("lexemes",len(by),"promote",prom)
