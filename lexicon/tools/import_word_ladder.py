"""Import word-ladder groups into ladder_groups / ladder_members (card #1451).

  python lexicon/tools/import_word_ladder.py FILE [FILE...] [--batch NAME] [--dry-run] [--no-backup]

FILE is a checked_batch_NN.json from word_ladder.py: {"words":[{word,pos,senses:[{ssid,senseId,group,zh,members:[{w,pos,zh}]}]}]}
(a bare list also works; senses[].words is read as an alias of members), or a prototype sample (sample_round12.json:
senses[].candidates[{w,level}], no Chinese; no ssid, kept as legacy groups).
Card #1468: a sense with an `ssid` (WordNet synset) is one group, keyed by (language, pos, ssid): rerun = same group,
members upserted, never merged by member overlap, so different meanings stay apart. Only sense-less prototype
entries still use the old overlap match. Every sense is validated first; a bad file aborts before any write.
Backup of both tables first: lexicon/logs/agents/card1468_backup_<time>.json.
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
    """Yield (gloss_en, zh, [member dicts]) in the checked format, converting prototype candidates.
    Reference-only senses (a key but no members: the group is defined under another word) yield no members."""
    for sn in entry.get("senses", []):
        if "members" in sn or "words" in sn:
            ws = sn.get("members") or sn.get("words") or []
        else:
            ws = [{"w": c["w"], "pos": entry.get("pos"), "cefr": c.get("level"), "zh": "", "added_by": "qwen"}
                  for c in sn.get("candidates", [])]
        yield sn.get("gloss_en") or sn.get("gloss") or "", sn.get("zh", ""), ws


def sense_key(sn):
    """Stable identity of a checked sense: WordNet ssid, else the hand-made group name, else the App senseId."""
    return sn.get("ssid") or sn.get("group") or (f"sense-{sn['senseId']}" if sn.get("senseId") else "")


def validate_entries(entries):
    """Return a list of problems; empty = importable. Checked format needs word, ssid, a non-empty members list per sense."""
    bad = []
    for i, e in enumerate(entries):
        w = (e.get("word") or "").strip() if isinstance(e, dict) else ""
        if not w:
            bad.append(f"entry {i}: no word")
            continue
        senses = e.get("senses")
        if not isinstance(senses, list):
            bad.append(f"{w}: senses is not a list")
            continue
        for j, sn in enumerate(senses):
            tag = f"{w}#{j}"
            checked = "members" in sn or "words" in sn
            if not checked and "candidates" not in sn and not sense_key(sn):
                bad.append(f"{tag}: no members/words/candidates")
                continue
            ws = sn.get("members") if "members" in sn else sn.get("words")
            if ws is not None and not all(isinstance(x, dict) and (x.get("w") or "").strip() for x in ws):
                bad.append(f"{tag}: member without w")
            if checked and not sense_key(sn):
                bad.append(f"{tag}: checked sense without ssid/group/senseId")
    return bad


def backup(s):
    rows = {"groups": [{c.name: str(getattr(g, c.name)) for c in g.__table__.columns} for g in s.execute(select(m.LadderGroup)).scalars()],
            "members": [{c.name: getattr(x, c.name) for c in x.__table__.columns} for x in s.execute(select(m.LadderMember)).scalars()]}
    p = ROOT / "lexicon" / "logs" / "agents" / f"card1468_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
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
    sense_meta = entry.get("senses", [])
    for idx, (gloss, zh, ws) in enumerate(senses_of(entry)):
        if not ws:
            stats["refs_skipped"] = stats.get("refs_skipped", 0) + 1
            continue
        meta = sense_meta[idx] if idx < len(sense_meta) else {}
        ssid = sense_key(meta)  # senseId is the source word's own sense, not a group property
        names = {x["w"].strip().lower() for x in ws} | {word}
        target = None
        if ssid:  # explicit sense identity: exact key, never overlap
            target = s.execute(select(m.LadderGroup).where(m.LadderGroup.language == "en", m.LadderGroup.pos == pos,
                                                           m.LadderGroup.ssid == ssid)).scalar_one_or_none()
            if target is not None:
                stats["merged"] += 1
                target.zh = target.zh or zh
                target.gloss_en = target.gloss_en or gloss
        for g in ([] if ssid else s.execute(select(m.LadderGroup).join(m.LadderMember, m.LadderMember.group_id == m.LadderGroup.id)
                           .where(m.LadderGroup.pos == pos, m.LadderGroup.ssid == "", m.LadderMember.word == word).distinct()).scalars()):
            have = {x for x in s.execute(select(m.LadderMember.word).where(m.LadderMember.group_id == g.id)).scalars()}
            if len(have & names) * 2 >= min(len(have), len(names)) and (g.zh == zh or not zh or not g.zh or len(have & names) > 1):
                target = g
                break
        if target is None:
            target = m.LadderGroup(language="en", pos=pos, zh=zh, gloss_en=gloss, head_word=word, batch=batch,
                                   ssid=ssid)
            s.add(target)
            s.flush()
            stats["groups"] += 1
        elif not ssid:
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
    loaded = []
    for f in a.files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        entries = d if isinstance(d, list) else d.get("words", [])
        problems = validate_entries(entries)
        if problems:
            print(f"{Path(f).name}: {len(problems)} problems, nothing imported:\n  " + "\n  ".join(problems[:20]))
            sys.exit(2)
        loaded.append((Path(f), entries))
    with db.SessionLocal() as s:
        if not a.no_backup and not a.dry_run:
            backup(s)
        for f, entries in loaded:
            batch = a.batch or f.stem
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
