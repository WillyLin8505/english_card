"""Card 224: run pin_simulation slices a..b (foreground, < 10 min per call). Usage: round a b"""
import json, os, subprocess, sys, time
from pathlib import Path
APP = Path(__file__).resolve().parents[2]
rnd, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
out = APP / "build" / "rounds" / rnd
cache = APP.parent / "tagger" / "cache"
manifest = out / "pin_files.json"
if not manifest.exists():
    files = sorted(str(f.resolve()) for f in cache.iterdir() if f.is_file() and not f.name.startswith("score-"))
    manifest.write_text(json.dumps(files), encoding="utf-8")
total = len(json.loads(manifest.read_text(encoding="utf-8")))
t0 = time.time()
for i in range(a, min(b, (total + 999) // 1000)):
    if time.time() - t0 > 480:
        print("stop before slice", i); break
    env = {**os.environ, "SIM_PACK": str(out / "pack.json"), "SIM_SEED": rnd, "SIM_TARGET": "en",
           "SIM_DECKS": str(out / "decks.json"), "SIM_OUT": str(out / f"pins.{i}.json"),
           "SIM_EVENTS": str(out / "pins.events.jsonl"), "SIM_PIN_FILES": str(manifest),
           "SIM_PIN_START": str(i * 1000), "SIM_PIN_COUNT": "1000"}
    log = out / f"pins.{i}.log"
    with open(log, "w", encoding="utf-8") as f:
        c = subprocess.call(["flutter.bat", "test", "test/simulation/pin_simulation.dart"], cwd=APP, env=env,
                            stdout=f, stderr=subprocess.STDOUT, timeout=540)
    print(i, "ok" if c == 0 else f"FAIL {c}", flush=True)
print("total slices", (total + 999) // 1000)
