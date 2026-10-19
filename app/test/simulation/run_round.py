"""One round of user-behaviour simulation, for the 排程 standing card 「模擬使用者」.

Downloads the live lexicon pack the app uses (serve_app.py, 127.0.0.1:8123),
then runs every simulation in this folder against it with the round number as
seed, and writes everything to app/build/rounds/<N>/ (pack.json, <name>.json,
<name>.log, summary.json). By default no AI model is called; the photo
simulation sends real pictures to the Qwen tagger, so it runs only with
--with-ai (ask the owner first).

Besides catching bugs, each #12 round must also judge UX from a learner's
perspective (convenience, necessity, glanceability, clutter / meaningless
info such as source·license·id on the card back, taps, clarity) and propose
concrete improvements as issue reports — not only failures.

    python app/test/simulation/run_round.py            # next round number
    python app/test/simulation/run_round.py 47 --only learner,database
    python app/test/simulation/run_round.py --with-ai  # also the photo simulation
    python app/test/simulation/run_round.py --no-posthog  # keep the events local

The app's analytics events of every simulation (<name>.events.jsonl) are
uploaded to PostHog when app/posthog.local.json exists, as one simulated
learner per simulation (distinct_id sim-r<N>-<name>, property simulated=true;
filter it out of real-user reports). Timestamps keep their spacing but are
shifted to end now.

Prints one line per simulation and the summary; exit code 1 when any failed.
"""
import argparse
import gzip
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
ROUNDS = APP / "build" / "rounds"
POSTHOG_FILE = APP / "posthog.local.json"
PACK_URL = "http://127.0.0.1:8123/api/lexicon?target=en&native=zh-TW"
# name: (file, extra environment). Timing probes are left out: they measure,
# they don't check behaviour.
SIMS = {
    "learner": ("learner_simulation.dart", {"SIM_DAYS": "30", "SIM_NEW": "8"}),
    "restart": ("restart_simulation.dart", {}),
    "database": ("database_simulation.dart", {}),
    "detail": ("detail_simulation.dart", {}),
    "photo_ui": ("photo_ui_simulation.dart", {}),
    "album": ("album_simulation.dart", {}),
    "pins": ("pin_simulation.dart", {}),
    "pack_update": ("pack_update_simulation.dart", {}),
    "fuzz": ("fuzz_simulation.dart", {}),
    # What a learner actually reads on each screen (≥ 50 words), for the
    # usability review: lexicon/docs/agents/simulation_usability.md.
    "learner_view": ("learner_view_simulation.dart", {"SIM_WORDS": "60", "SIM_LEVEL": "B1"}),
    "settings": ("settings_simulation.dart", {}),
    "card_draw": ("card_draw_simulation.dart", {}),
}


# These call the local Qwen tagger.
AI_SIMS = {"photo": ("photo_simulation.dart", {})}


def next_round() -> int:
    """The next free round, claimed by creating its folder: several cards
    (one per app tab) may start rounds at the same time."""
    ROUNDS.mkdir(parents=True, exist_ok=True)
    n = max((int(p.name) for p in ROUNDS.glob("*") if p.name.isdigit()), default=0) + 1
    while True:
        try:
            (ROUNDS / str(n)).mkdir()
            return n
        except FileExistsError:
            n += 1


def fetch_pack(dest: Path) -> int:
    request = urllib.request.Request(PACK_URL, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=300) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    dest.write_bytes(body)
    return len(json.loads(body).get("lexemes", []))


def upload_events(out: Path, n: int, names) -> str:
    """Sends each simulation's recorded events to PostHog as a simulated learner."""
    if not POSTHOG_FILE.exists():
        return "PostHog：沒有 posthog.local.json，略過"
    cfg = json.loads(POSTHOG_FILE.read_text(encoding="utf-8"))
    key, host = cfg.get("POSTHOG_API_KEY"), cfg.get("POSTHOG_HOST", "https://us.i.posthog.com")
    sent = 0
    for name in names:
        f = out / f"{name}.events.jsonl"
        if not f.exists():
            continue
        events = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not events:
            continue
        stamps = [datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) for e in events]
        shift = datetime.now(timezone.utc) - max(stamps)
        for e, t in zip(events, stamps):
            e["distinct_id"] = f"sim-r{n}-{name}"
            e["timestamp"] = (t + shift).isoformat()
            e["properties"].update(simulated=True, sim_round=n, sim_name=name)
        for i in range(0, len(events), 500):
            body = json.dumps({"api_key": key, "batch": events[i:i + 500]}).encode("utf-8")
            req = urllib.request.Request(f"{host}/batch/", body, {"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=30).read()
                sent += len(events[i:i + 500])
            except OSError as e:
                return f"PostHog：上傳失敗（{e}），已送 {sent} 筆"
    return f"PostHog：已上傳 {sent} 筆模擬事件（sim-r{n}-*）"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("round", nargs="?", type=int)
    ap.add_argument("--only", help="comma-separated simulation names")
    ap.add_argument("--with-ai", action="store_true", help="also simulations that call the Qwen tagger")
    ap.add_argument("--no-posthog", action="store_true", help="do not upload the analytics events")
    a = ap.parse_args()
    n = a.round or next_round()
    out = ROUNDS / str(n)
    out.mkdir(parents=True, exist_ok=True)
    pack = out / "pack.json"
    # Re-running part of a round keeps that round's pack (same data as its
    # other results) and merges into its summary.
    if pack.exists() and a.round:
        words = len(json.loads(pack.read_text(encoding="utf-8")).get("lexemes", []))
        print(f"round {n}: reusing its pack ({words} lexemes)")
    else:
        words = fetch_pack(pack)
        print(f"round {n}: pack {words} lexemes → {pack}")
    previous = out / "summary.json"
    results = (json.loads(previous.read_text(encoding="utf-8")).get("results", {})
               if previous.exists() and a.round else {})
    flutter = "flutter.bat" if os.name == "nt" else "flutter"
    for name, (file, extra) in {**SIMS, **(AI_SIMS if a.with_ai else {})}.items():
        if a.only and name not in a.only.split(","):
            continue
        env = {**os.environ, "SIM_PACK": str(pack), "SIM_SEED": str(n),
               "SIM_OUT": str(out / f"{name}.json"),
               "SIM_EVENTS": str(out / f"{name}.events.jsonl"), **extra}
        started = time.time()
        with open(out / f"{name}.log", "w", encoding="utf-8") as log:
            code = subprocess.call([flutter, "test", f"test/simulation/{file}"], cwd=APP, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        tail = (out / f"{name}.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:]
        results[name] = {"ok": code == 0, "seconds": round(time.time() - started), "last": tail[0] if tail else ""}
        print(f"  {'通過' if code == 0 else '失敗'} {name} ({results[name]['seconds']} 秒) {results[name]['last'][:120]}")
    failed = [k for k, v in results.items() if not v["ok"]]
    if not a.no_posthog:
        print(upload_events(out, n, results))
    summary = {"round": n, "finished": time.strftime("%Y-%m-%d %H:%M:%S"), "pack_lexemes": words,
               "results": results, "failed": failed}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"round {n}: {len(results) - len(failed)}/{len(results)} 通過" + (f"，失敗：{'、'.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
