import os, sys, json, random, time
__file__ = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'ladder29.py')
_src = open(__file__, encoding='utf-8').read()
exec(_src[:_src.index('\nby = {p:')])
by = {p: [w for w in CEFR if w.isalpha() and info(w).get(p) in ('A1', 'A2', 'B1')
          and any(W.synsets(w, pos=x) for x in WNPOS[p])] for p in ALLOW}
random.seed(time.time())
picks = [(random.choice(by[p]), p) for p in ('noun', 'noun', 'verb', 'verb', 'adjective')]
out = []
for word, pos in picks:
    ss = all_senses(word, pos)
    out.append({'word': word, 'pos': pos, 'senses': [{'gloss': s['gloss'], 'example': s['example'], 'src': s['src']} for s in ss]})
    print(f'## {word} ({pos})')
    for i, s in enumerate(ss):
        print(f'  {i + 1}. [{s["src"]}] {s["gloss"][:110]}')
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'senses_dump.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
