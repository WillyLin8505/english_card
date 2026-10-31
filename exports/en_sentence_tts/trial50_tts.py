"""Card 868: Kokoro US/UK mp3 for picked50.json; run with the ttsenv python from inside trial50/."""
import json, sys, time
from pathlib import Path
import soundfile as sf
from kokoro_onnx import Kokoro
M = Path(sys.argv[1])
import onnxruntime as ort
so = ort.SessionOptions(); so.intra_op_num_threads = 4
k = Kokoro.from_session(ort.InferenceSession(str(M / 'kokoro-v1.0.onnx'), sess_options=so, providers=['CPUExecutionProvider']), str(M / 'voices-v1.0.bin'))
P = json.load(open('picked50.json', encoding='utf-8'))
T = {}
for d, voice, lang in (('kokoro_us', 'af_heart', 'en-us'), ('kokoro_uk', 'bf_emma', 'en-gb')):
    t0 = time.time()
    for p in P:
        if Path(f"{d}/{p['n']:02d}.mp3").exists() and p['n'] != P[-1]['n']: continue
        s, sr = k.create(p['text'], voice=voice, speed=1.0, lang=lang)
        sf.write(f"{d}/{p['n']:02d}.mp3", s, sr, format='MP3')
    T[d] = round(time.time() - t0, 1)
    print(d, T[d], flush=True)
json.dump(T, open('kokoro_time.json', 'w'))
