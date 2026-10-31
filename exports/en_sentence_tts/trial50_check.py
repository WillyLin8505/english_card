import json, sys, time, soundfile as sf
from pathlib import Path
import onnxruntime as ort
from kokoro_onnx import Kokoro
bad = []
for d in ('human', 'kokoro_us', 'kokoro_uk'):
    for i in range(1, 51):
        try:
            x, sr = sf.read(f'{d}/{i:02d}.mp3'); assert len(x) / sr > 0.4
        except Exception as e: bad.append((d, i, str(e)[:40]))
print('bad', bad)
M = Path(sys.argv[1]); so = ort.SessionOptions(); so.intra_op_num_threads = 4
k = Kokoro.from_session(ort.InferenceSession(str(M / 'kokoro-v1.0.onnx'), sess_options=so, providers=['CPUExecutionProvider']), str(M / 'voices-v1.0.bin'))
P = json.load(open('picked50.json', encoding='utf-8'))[:8]
k.create('warm up', voice='af_heart', lang='en-us')
T = {}
for d, v, l in (('kokoro_us', 'af_heart', 'en-us'), ('kokoro_uk', 'bf_emma', 'en-gb')):
    t = time.time()
    for p in P: k.create(p['text'], voice=v, lang=l)
    T[d] = round((time.time() - t) / len(P), 1)
print(T); json.dump(T, open('timing.json', 'w'))
