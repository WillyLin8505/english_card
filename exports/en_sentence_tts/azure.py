"""Azure samples (US Aria, UK Sonia) for the picked sentences; usage is counted by synth()."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'lexicon' / 'tools'))
import card695_tts_audio as t  # noqa: E402

for acc in ('us', 'uk'):
    (HERE / f'azure_{acc}').mkdir(exist_ok=True)
for p in json.load(open(HERE / 'picked.json', encoding='utf-8')):
    for acc in ('us', 'uk'):
        data = t.synth(p['text'], t.VOICES[acc][1])
        (HERE / f'azure_{acc}' / f"{p['word']}.mp3").write_bytes(data)
        print(acc, p['word'], len(data))
