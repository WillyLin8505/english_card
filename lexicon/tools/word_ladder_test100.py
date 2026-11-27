"""Owner 11/27: run the first 100 words now (day) to measure Qwen speed; written as batch 00 so the
nightly 75-word batches 01..14 keep their numbering. Then opens the Codex check card for batch 00."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import word_ladder as wl

START, BATCH = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (0, 0)  # 100 200... / 91
words = wl.pick_words()[START:START + 100]
st = wl.load_state()
stats = {'qwen': 0, 'to_claude': 0, 'merged': 0, 'qwen_seconds': 0.0}
t = time.time()
entries = wl.run_words([(w, p) for w, ps in words for p in ps], st, stats)
doc = {'batch': BATCH, 'words': [w for w, _ in words], 'stats': stats, 'seconds': round(time.time() - t, 1),
       'entries': [wl.compact(e) for e in entries]}
path = os.path.join(wl.OUT, f'qwen_batch_{BATCH:02d}.json')
json.dump(doc, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
wl.save_state(st)
print(f'batch {BATCH:02d}: {len(words)} words, {len(entries)} word+pos, {stats}, {doc["seconds"]}s', flush=True)
