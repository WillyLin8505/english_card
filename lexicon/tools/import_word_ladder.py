"""Import word-ladder groups into ladder_groups / ladder_members (card #1451).

  python lexicon/tools/import_word_ladder.py FILE [FILE...] [--batch NAME] [--dry-run] [--no-backup]

FILE is a checked_batch_NN.json (#1875: {"words":[{word,pos,senses:[{gloss_en,zh,words:[{w,pos,cefr,zh,added_by}]}]}]},
a bare list also works) or a prototype sample (sample_round12.json: senses[].candidates[{w,level}], no Chinese).
Rerunnable: members are upserted, nothing is deleted. A sense whose words overlap >= half of an existing
group of the same pos that already holds the source word is merged into that group (shared meaning).
Backup of both tables first: lexicon/logs/agents/card1451_backup_<time>.json.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from app import db, models as m  # noqa: E402

POS = {"n": "noun", "v": "verb", "a": "adj", "adj.": "adj", "adj": "adj", "adv.": "adv", "adv": "adv", "noun": "noun", "verb": "verb"}


def norm_pos(p):
    return POS.get((p or "").lower(), (p or "").lower())


def senses_of(entry):
    """Yield (gloss_en, zh, [member dicts]) in the checked format, converting prototype candidates."""
    for sn in entry.get("senses", []):
        if "words" in sn:
            ws = sn["words"]
        else:
            ws = [{"w": c["w"], "pos": entry.get("pos"), "cefr": c.get("level"), "zh": "", "added_by": "qwen"}
                  for c in sn.get("candidates", [])]
        yield sn.get("gloss_en") or sn.get("gloss") or "", sn.get("zh", ""), ws


def backup(s):
    rows = {"groups": [{c.name: str(getattr(g, c.name)) for c in g.__table__.columns} for g in s.execute(select(m.LadderGroup)).scalars()],
            "members": [{c.name: getattr(x, c.name) for c in x.__table__.columns} for x in s.execute(select(m.LadderMember)).scalars()]}
    p = ROOT / "lexicon" / "logs" / "agents" / f"card1451_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"backup {p.name}: {len(rows['groups'])} groups, {len(rows['members'])} members")


def upsert_member(s, gid, w, ordinal):
    word, pos = w["w"].strip().lower(), norm_pos(w.get("pos"))
    x = s.execute(select(m.LadderMember).where(m.LadderMember.group_id == gid, m.LadderMember.word == word,
                                              m.LadderMember.pos == pos)).scalar_one_or_none()
    new = x is None
    if new:
        x = m.LadderMember(group_id=gid, word=word, pos=pos)
        s.add(x)
    x.cefr = w.get("cefr") or x.cefr
    if w.get("zh"):
        x.zh, x.zh_ai = w["zh"], w.get("zh_ai", True)
    x.added_by = w.get("added_by") or x.added_by or "qwen"
    x.ordinal = ordinal
    return new


def import_entry(s, entry, batch, stats):
    word, pos = entry["word"].strip().lower(), norm_pos(entry.get("pos"))
    for gloss, zh, ws in senses_of(entry):
        if not ws:
            continue
        names = {x["w"].strip().lower() for x in ws} | {word}
        target = None
        for g in s.execute(select(m.LadderGroup).join(m.LadderMember, m.LadderMember.group_id == m.LadderGroup.id)
                           .where(m.LadderGroup.pos == pos, m.LadderMember.word == word).distinct()).scalars():
            have = {x for x in s.execute(select(m.LadderMember.word).where(m.LadderMember.group_id == g.id)).scalars()}
            if len(have & names) * 2 >= min(len(have), len(names)) and (g.zh == zh or not zh or not g.zh or len(have & names) > 1):
                target = g
                break
        if target is None:
            target = m.LadderGroup(language="en", pos=pos, zh=zh, gloss_en=gloss, head_word=word, batch=batch)
            s.add(target)
            s.flush()
            stats["groups"] += 1
        else:
            stats["merged"] += 1
            target.zh = target.zh or zh
            target.gloss_en = target.gloss_en or gloss
        order = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "C1": 4, "C2": 5}
        members = list(ws)
        if word not in {x["w"].strip().lower() for x in ws}:
            members.append({"w": word, "pos": pos, "cefr": entry.get("level") or entry.get("cefr"), "zh": zh if False else "", "added_by": "qwen"})
        members.sort(key=lambda x: order.get(x.get("cefr") or "", 9))
        for i, w in enumerate(members):
            stats["members_new" if upsert_member(s, target.id, w, i) else "members_upd"] += 1
        s.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--batch", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()
    stats = {"words": 0, "groups": 0, "merged": 0, "members_new": 0, "members_upd": 0}
    with db.SessionLocal() as s:
        if not a.no_backup and not a.dry_run:
            backup(s)
        for f in a.files:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            entries = d if isinstance(d, list) else d.get("words", [])
            batch = a.batch or Path(f).stem
            for e in entries:
                import_entry(s, e, batch, stats)
                stats["words"] += 1
        if a.dry_run:
            s.rollback()
        else:
            s.commit()
    print(("dry-run " if a.dry_run else "") + json.dumps(stats))


if __name__ == "__main__":
    main()
