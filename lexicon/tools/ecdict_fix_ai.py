"""Owner decision #171 C: relation / derived-word meanings the AI got wrong
(or never filled) are replaced by ECDICT's, when ECDICT has the word. No AI
call. Settled words are otherwise untouched.

A meaning counts as a problem when it is
  missing   - the relation word has no meaning at all (the AI's answer was
              rejected: English echoed, Simplified, empty);
  sentence  - reads like a sentence or explanation (。 inside, ；, more than 8
              characters; a trailing 。 alone is dropped at export instead);
  latin     - has Latin letters outside a （…） note.
(A part-of-speech mismatch check was tried and dropped: relation words' parts
of speech are too unreliable - ECDICT gave doctor 授以博士學位, case 情形.)

    python tools/ecdict_fix_ai.py scan                 # counts + samples, writes nothing
    python tools/ecdict_fix_ai.py apply WORD [WORD...] # those headwords only
    python tools/ecdict_fix_ai.py apply --all          # every headword with a problem
apply first saves the touched field values under raw-data/.
"""
import collections
import json
import random
import re
import sys

sys.path.insert(0, "backend")
sys.stdout.reconfigure(encoding="utf-8")
from sqlalchemy import text  # noqa: E402

from app import adapters, catalog, db, pipeline  # noqa: E402
from app.adapters import ADAPTERS  # noqa: E402

FIELDS = {**catalog.RELATION_NATIVE, "derived_native_meaning": "derived_terms"}
CJK = re.compile(r"[㐀-鿿]")
E = ADAPTERS["ecdict"]


def problem(item_text, word, pos, ec):
    if item_text is None:
        return "missing"
    t = item_text.strip()
    # English inside （…） is a note (生菜（cos lettuce）): the meaning is fine.
    if re.search(r"[A-Za-z]", re.sub(r"[（(][^）)]*[）)]", "", t)):
        return "latin"
    # A trailing 。 alone isn't a problem: the export drops it (clean_native).
    t = t.rstrip(" 。")
    if "。" in t or "；" in t or ";" in t or len(CJK.findall(t)) > 8:
        return "sentence"
    return None


def scan(session, only=None):
    """{(lemma, field): {word_lower: (kind, ai_text, ecdict_text, word)}}"""
    q = """SELECT fv.lemma, fv.items, rel.items FROM field_values fv
           JOIN field_values rel ON rel.target_language = fv.target_language AND rel.lemma = fv.lemma
            AND rel.native_language = fv.native_language AND rel.field = :rel
           WHERE fv.target_language = 'en' AND fv.native_language = 'zh-TW' AND fv.field = :f"""
    out = {}
    for f, rel in FIELDS.items():
        for lemma, items, rels in session.execute(text(q), {"f": f, "rel": rel}).all():
            if only and lemma not in only:
                continue
            have = {(i.get("word") or i.get("key") or "").lower(): i for i in items or []}
            for r in rels or []:
                w = r.get("word") or ""
                if not w:
                    continue
                cur = have.get(w.lower())
                if cur is not None and cur.get("source") != "ai_translate":
                    continue  # a dictionary meaning: keep
                ec = E.meaning(w, r.get("pos")) if r.get("pos") else E.meaning(w, None, loose=True)
                if not ec:
                    continue
                kind = problem(cur.get("text") if cur else None, w, r.get("pos"), ec)
                if kind:
                    out.setdefault((lemma, f), {})[w.lower()] = (
                        kind, cur.get("text") if cur else None, ec, w)
    return out


def main():
    cmd = sys.argv[1]
    if cmd == "revert":  # undo an apply for these headwords: drop ECDICT's stored lookups
        words = sys.argv[2:]
        ADAPTERS["ai_translate"].lookup = lambda field_key, ctx: []
        ADAPTERS["ai_translate"].prefetch = lambda ctx, fields: 0
        E.lookup = lambda field_key, ctx: []
        for w in words:
            with db.session_scope() as s:
                for table in ("field_candidates", "source_lookups"):
                    s.execute(text(f"DELETE FROM {table} WHERE target_language = 'en' AND lemma = :l "
                                   "AND source = 'ecdict' AND field = ANY(:f)"), {"l": w, "f": list(FIELDS)})
            with db.session_scope() as s:
                adapters.configure(s)
                pipeline.process_word(s, "en", "zh-TW", w, list(FIELDS), "reresolve")
            print("reverted", w)
        return
    only = None if cmd == "scan" or "--all" in sys.argv else set(sys.argv[2:])
    with db.session_scope() as s:
        adapters.configure(s)
        found = scan(s, only)
    kinds = collections.Counter(v[0] for d in found.values() for v in d.values())
    print("problems ECDICT can fix:", dict(kinds), "in", len({lemma for lemma, _ in found}),
          "headwords")
    if cmd == "scan":
        random.seed(3)
        rows = [(lemma, f, *v) for (lemma, f), d in found.items() for v in d.values()]
        for kind in kinds:
            for r in random.sample([r for r in rows if r[2] == kind], min(8, kinds[kind])):
                print(f"  {kind:8s} {r[0]} / {r[5]} [{r[1]}]: AI={r[3]!r} -> ECDICT={r[4]!r}")
        return
    by_lemma = collections.defaultdict(dict)
    for (lemma, field), d in found.items():
        by_lemma[lemma][field] = d
    path = f"raw-data/ecdict_fix_ai_snapshot_{'all' if only is None else 'some'}.json"
    with db.session_scope() as s:
        rows = s.execute(text("""SELECT lemma, field, status, items, missing, policy_version
            FROM field_values WHERE target_language = 'en' AND native_language = 'zh-TW'
            AND lemma = ANY(:l) AND field = ANY(:f)"""),
            {"l": list(by_lemma), "f": list(FIELDS)}).all()
    with open(path, "w", encoding="utf-8") as out:
        json.dump([dict(r._mapping) for r in rows], out, ensure_ascii=False, default=str)
    print("snapshot", path, len(rows), "field values")
    real_lookup = E.lookup
    ADAPTERS["ai_translate"].lookup = lambda field_key, ctx: []
    ADAPTERS["ai_translate"].prefetch = lambda ctx, fields: 0  # never a batch AI call
    for lemma, fields in sorted(by_lemma.items()):
        def only_problems(field_key, ctx, fields=fields):
            keep = fields.get(field_key, {})
            return [c for c in real_lookup(field_key, ctx) if c.slot in keep]
        E.lookup = only_problems
        with db.session_scope() as s:
            adapters.configure(s)
            display = s.execute(text("SELECT lemma FROM lexemes WHERE language = 'en' "
                                     "AND normalized = :n LIMIT 1"), {"n": lemma}).scalar() or lemma
            pipeline.process_word(s, "en", "zh-TW", display, list(fields), "reresolve")
        print(lemma, {f: len(d) for f, d in fields.items()})
    E.lookup = real_lookup
    print("headwords", len(by_lemma))


if __name__ == "__main__":
    main()
