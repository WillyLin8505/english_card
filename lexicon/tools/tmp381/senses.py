import sys
sys.path.insert(0,"lexicon/backend"); sys.stdout.reconfigure(encoding="utf-8")
from sqlalchemy import text
from app import db
pairs=[a.split("/") for a in sys.argv[1:]]
with db.SessionLocal() as s:
    for w,p in pairs:
        rows=s.execute(text("""select sn.ordinal, sn.labels, (select d.text from definitions d where d.sense_id=sn.id and d.language='en' order by d.id limit 1), t.text, t.is_ai
          from lexemes l join senses sn on sn.lexeme_id=l.id left join sense_translations t on t.sense_id=sn.id and t.native_language='zh-TW'
          where l.language='en' and l.lemma=:w and l.pos=:p order by sn.ordinal"""),{"w":w,"p":p}).all()
        print("==",w,p,len(rows))
        for o,l,g,zh,ai in rows[:int(sys.argv[0:1] and 40)]:
            lab=",".join(x for x in (l or []) if x not in ('countable','uncountable','transitive','intransitive'))
            if o<int(__import__("os").environ.get("MAXO","11")) or "etym" in lab: print(f" {o} [{lab[:25]}] {(g or '')[:58]} => {(zh or '')[:14]}{'*' if ai else ''}")
