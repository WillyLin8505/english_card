import sys
sys.path.insert(0,"lexicon/backend"); sys.stdout.reconfigure(encoding="utf-8")
from app.adapters import ecdict
from app.text import opencc
E=ecdict.ECDict()
for a in sys.argv[1:]:
    w,p=a.split("/")
    t=E.translation(w) or ""
    ms=[(pp,ws) for pp,ws in ecdict.meanings(t) if pp==p]
    print(a, [[opencc("s2twp",x) or x for x in ws] for pp,ws in ms])
