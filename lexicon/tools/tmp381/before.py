import sys, json, re
sys.path.insert(0,"lexicon/backend"); sys.path.insert(0,"lexicon/tools"); sys.stdout.reconfigure(encoding="utf-8")
import card381_learner as L
from app import quality
nb=json.load(open("lexicon/raw-data/card381_native_before.json",encoding="utf-8"))
tr={r[1]:(r[3],r[5]) for r in nb["sense_translations"] if r[2]=="zh-TW"}
ords={int(k):v for k,v in json.load(open("lexicon/raw-data/card381_ordinals_before.json")).items()}
cb=json.load(open("lexicon/raw-data/card381_common_before.json",encoding="utf-8"))
L.LOW_IDS={str(i) for i in cb["overrides"].get("low_priority_senses",[])}
L.RARE.discard("childish")
def old(senses):
    ranked=quality.rank_senses([{"id":i,"native":zh,"labels":list(lab or []),"native_ai":ai} for i,zh,lab,ai,_ in senses], L.LOW_IDS)
    ss=[(r["id"],r["native"],r["labels"],r["native_ai"]) for r in ranked]
    usable=[s for s in ss if (s[1] or "").strip() and not any(l.lower() in L.RARE or l.startswith("etymology-") for l in s[2] or [])]
    dic=[s for s in usable if not s[3]]
    common=(dic or usable)[:2]; seen=set(); parts=[]
    for s in common:
        ws=[w.strip() for w in re.split(r"[、；;，,]", s[1]) if w.strip()]
        ws=[w for w in ws if w not in seen and not seen.add(w)]
        if ws: parts.append("、".join(ws))
    return "；".join(parts)
# monkeypatch rank_senses' first-sense exception off for "before"
src_rank=quality.rank_senses
by=L.load(["A1","A2"])
lines=[]
import inspect
for (l,p),ss in by.items():
    ss2=[(i,)+tr.get(i,(None,False))[:1]+(lab,tr.get(i,(None,False))[1],g) for i,zh,lab,ai,g in ss]
    if any(i in ords for i,*_ in ss2): ss2=sorted(ss2,key=lambda x: ords.get(x[0],999))
    lines.append(f"{l}\t{p}\t{old(ss2)}")
open("lexicon/tools/tmp381/learner_before.tsv","w",encoding="utf-8").write("\n".join(lines))
print(len(lines))
