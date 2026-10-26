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
    python app/test/simulation/run_round.py --lang fr  # English speaker learning French (#363)

--lang fr uses the fr→en pack, its own rounds folder (app/build/rounds_fr/<N>/)
and the French simulations (FR_SIMS), and adds pack_checks.json: what a French
learner needs from the pack (noun gender, verb conjugation, English meanings,
audio, French picture labels).

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
# Through the 5173 proxy (read-only /app-pack entry, lexicon/frontend/vite.config.ts):
# dispatched agents may not call the app server's port directly (問題回報 #758).
PACK_URL = "http://127.0.0.1:5173/app-pack/lexicon?target={target}&native={native}"
LANGS = {"en": ("en", "zh-TW"), "fr": ("fr", "en")}
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


# An English speaker learning French (問題回報 #363): onboarding, review,
# word details and every tab with the English interface, at two levels.
FR_SIMS = {
    "fr_learner_a1": ("fr_learner_simulation.dart", {"SIM_WORDS": "40", "SIM_LEVEL": "A1", "SIM_CAPTURE": "1"}),
    "fr_learner_b1": ("fr_learner_simulation.dart", {"SIM_WORDS": "60", "SIM_LEVEL": "B1"}),
    "card_draw": ("card_draw_simulation.dart", {}),
    "fr_media": ("fr_media_simulation.dart", {}),
}

# These call the local Qwen tagger.
AI_SIMS = {"photo": ("photo_simulation.dart", {})}


def next_round(rounds=ROUNDS) -> int:
    """The next free round, claimed by creating its folder: several cards
    (one per app tab) may start rounds at the same time."""
    ROUNDS = rounds
    ROUNDS.mkdir(parents=True, exist_ok=True)
    n = max((int(p.name) for p in ROUNDS.glob("*") if p.name.isdigit()), default=0) + 1
    while True:
        try:
            (ROUNDS / str(n)).mkdir()
            return n
        except FileExistsError:
            n += 1


def fetch_pack(dest: Path, lang="en") -> int:
    target, native = LANGS[lang]
    url = PACK_URL.format(target=target, native=native)
    request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=300) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    dest.write_bytes(body)
    return len(json.loads(body).get("lexemes", []))


def fr_pack_checks(pack: Path) -> dict:
    """What an English speaker learning French needs from the pack."""
    d = json.loads(pack.read_text(encoding="utf-8"))
    lex = d["lexemes"]
    nouns = [l for l in lex if l["pos"] == "noun"]
    verbs = [l for l in lex if l["pos"] == "verb"]
    lemma = {l["id"]: l["lemma"] for l in lex}
    labels = [lb for i in d.get("catalog_images", []) for lb in i.get("labels", [])]
    gender = sum(1 for l in nouns if l.get("gender") or any(
        f.get("field") in ("fr_gender", "gender") for f in l["forms"]))
    return {
        "lexemes": len(lex),
        "nouns_with_gender": f"{gender}/{len(nouns)}",
        "verbs_with_present_forms": f"{sum(1 for l in verbs if any(f['field'].startswith('fr_present') for f in l['forms']))}/{len(verbs)}",
        "with_english_meaning": f"{sum(1 for l in lex if any(s.get('native') for s in l['senses']))}/{len(lex)}",
        "with_audio": f"{sum(1 for l in lex if any(p['kind'] == 'audio' and p.get('audio') for p in l['pronunciations']))}/{len(lex)}",
        "examples_without_translation": sum(1 for l in lex for e in l["examples"] if not e.get("translation")),
        "picture_labels_not_french_lemma": sum(1 for lb in labels if lemma.get(lb.get("lexeme_id")) != lb["word"]),
        "picture_labels": len(labels),
    }


def event_stats(out: Path, names) -> dict:
    """Summarize local events even when uploading is disabled."""
    stats = {}
    for name in names:
        path = out / f"{name}.events.jsonl"
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                  if line.strip()] if path.exists() else []
        reviews = [e.get("properties", {}) for e in events if e.get("event") == "card_reviewed"]
        ratings = {}
        for review in reviews:
            rating = str(review.get("rating", "unknown"))
            ratings[rating] = ratings.get(rating, 0) + 1
        times = [r["duration_ms"] for r in reviews if isinstance(r.get("duration_ms"), (int, float))]
        stats[name] = {"events": len(events), "card_reviewed": len(reviews),
                       "ratings": ratings, "mean_answer_ms": round(sum(times) / len(times), 2) if times else None}
    return stats


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
            e["distinct_id"] = f"sim-r{n}-{name}"  # n is "fr<N>" for French rounds
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
    ap.add_argument("--lang", choices=sorted(LANGS), default="en", help="learning language (fr: English speaker learning French)")
    a = ap.parse_args()
    rounds = ROUNDS if a.lang == "en" else APP / "build" / f"rounds_{a.lang}"
    sims = SIMS if a.lang == "en" else FR_SIMS
    n = a.round or next_round(rounds)
    out = rounds / str(n)
    out.mkdir(parents=True, exist_ok=True)
    pack = out / "pack.json"
    # Re-running part of a round keeps that round's pack (same data as its
    # other results) and merges into its summary.
    if pack.exists() and a.round:
        words = len(json.loads(pack.read_text(encoding="utf-8")).get("lexemes", []))
        print(f"round {n}: reusing its pack ({words} lexemes)")
    else:
        words = fetch_pack(pack, a.lang)
        print(f"round {n}: pack {words} lexemes → {pack}")
    if a.lang == "fr" and (not a.only or "fr_media" in a.only.split(",")):
        # Replay the live deck list in a widget test without network calls or AI.
        deck_file = out / "decks.json"
        if not deck_file.exists():
            # The app asks with its languages (問題回報 #501), so the replay must too;
            # the bare list is every deck of every language.
            target, native = LANGS[a.lang]
            with urllib.request.urlopen(f"http://127.0.0.1:5173/app-pack/decks?target={target}&native={native}",
                                        timeout=60) as response:
                deck_file.write_bytes(response.read())
    previous = out / "summary.json"
    results = (json.loads(previous.read_text(encoding="utf-8")).get("results", {})
               if previous.exists() and a.round else {})
    flutter = "flutter.bat" if os.name == "nt" else "flutter"
    for name, (file, extra) in {**sims, **(AI_SIMS if a.with_ai and a.lang == "en" else {})}.items():
        if a.only and name not in a.only.split(","):
            continue
        env = {**os.environ, "SIM_PACK": str(pack), "SIM_SEED": str(n),
               "SIM_TARGET": a.lang, "SIM_DECKS": str(out / "decks.json"),
               "SIM_OUT": str(out / f"{name}.json"),
               "SIM_EVENTS": str(out / f"{name}.events.jsonl"), **extra}
        started = time.time()
        with open(out / f"{name}.log", "w", encoding="utf-8") as log:
            try:
                code = subprocess.call([flutter, "test", f"test/simulation/{file}"], cwd=APP, env=env,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=540)
            except subprocess.TimeoutExpired:
                code = 124
                log.write("\nSimulation exceeded the 9-minute foreground limit.\n")
        tail = (out / f"{name}.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:]
        results[name] = {"ok": code == 0, "seconds": round(time.time() - started), "last": tail[0] if tail else ""}
        print(f"  {'通過' if code == 0 else '失敗'} {name} ({results[name]['seconds']} 秒) {results[name]['last'][:120]}")
    failed = [k for k, v in results.items() if not v["ok"]]
    if not a.no_posthog:
        print(upload_events(out, n if a.lang == "en" else f"{a.lang}{n}", results))
    summary = {"round": n, "lang": a.lang, "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
               "pack_lexemes": words, "results": results, "failed": failed}
    summary["events"] = event_stats(out, results)
    if a.lang == "fr":
        summary["pack_checks"] = fr_pack_checks(pack)
        print("pack:", json.dumps(summary["pack_checks"], ensure_ascii=False))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"round {n}: {len(results) - len(failed)}/{len(results)} 通過" + (f"，失敗：{'、'.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
