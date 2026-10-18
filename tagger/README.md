# AI 辨識標籤服務 (tagging API)

Spec-01 section 2 on this PC ("Predator"): **Ollama + Qwen3.5-4B (Q4)**
behind a small API at **`http://127.0.0.1:8765/tag`** with an
`X-API-Key`. Pillow is used to resize photos before inference.

## Start

1. Ollama installed, with the model pulled once:
   `ollama pull qwen3.5:4b`
2. Start the API — double-click `start_tagger.bat`. It first opens
   `start_llm.py`: llama-server (the engine Ollama ships) on
   `127.0.0.1:8790` with **four parallel slots**, using Ollama's model file.
   Ollama 0.35 serves qwen3.5 one request at a time ("model architecture
   does not currently support parallel requests"); four slots give about
   1.7× the text throughput on the RTX 5060 with identical translations
   (A/B 2026-10-06). `start_llm.py` asks Ollama to unload the model first:
   two copies do not fit in 8 GB. To run on Ollama instead:

   ```bash
   python tagger/tagging_server.py        # TAGGER_BACKEND=ollama, TAGGER_PARALLEL=1 (defaults)
   ```

   `TAGGER_BACKEND=llamacpp` sends the same requests to llama-server's
   OpenAI-compatible API (with Ollama's sampling parameters for qwen3.5:
   presence penalty 1.5, top_k 20, top_p 0.95); `TAGGER_PARALLEL` is how many
   run at once — match `start_llm.py --slots`. Identical requests still wait
   for each other, so the second reads the first one's cached reply.

   It prints the URL and the API key. The key lives in `tagger/.api_key`
   (made on first run; override with `TAGGER_API_KEY`).

## Point the app at it

Either type the URL and key in the app's 設定 → AI 辨識服務 and press
測試連線, or build them in (handy for `flutter run -d chrome`, which
starts with an empty browser profile each time):

```bash
cd app
flutter run -d chrome --dart-define-from-file=tagging.local.json
```

`app/tagging.local.json` holds `TAGGING_URL` and `TAGGING_API_KEY`; it's
git-ignored. Anything typed in 設定 overrides it.

## API

`POST /tag?level=B1&lang=en&native=zh-TW` — body: the image, raw
(`Content-Type: image/jpeg`, what the web app sends) or
`multipart/form-data` with an `image` part (native apps). This is stage 1
of spec section 3's recognition: 6–8 candidates of mixed parts of
speech, each with its picture context. The model only identifies labels;
all dictionary data is loaded from the downloaded offline database. Reply:

```json
{"candidates": [{"word": "mug", "lemma": "mug", "pos": "noun",
                 "evidence": "ceramic cup with coffee",
                 "point": [0.72, 0.35]}],
 "level": "B1", "lang": "en", "native": "zh-TW",
 "model": "qwen3.5:4b", "elapsedMs": 26000}
```

`point` is where the evidence is, as fractions of the image. Optional `focus=harder|easier|
actions|descriptions` and `exclude=word,word` ask for more candidates
when the app's pool runs short.

Stage 2 — choosing at most five words for the learner — runs in the app,
which knows the learner's vocabulary and resolves CEFR, meaning, IPA,
examples and relations from its downloaded word database ("模型不得直接決定最後五個詞").
`POST /enrich` returns HTTP 410 so the app never asks the local model for
dictionary content.

`POST /translate` is the word-database admin's AI fallback (lexicon
source `ai_translate`): it fills translations the dictionaries lack —
`{"lang", "native", "kind": word|gloss|sentence|etymology|define|part|morphemes,
"items": [{"id", "text", "context"?}]}` → `{"items": [{"id", "text"}]}`.
The admin marks every such value as AI. Chinese is written the Taiwan way
(義大利麵, not 意大利麵); the admin also converts Mainland words it receives
from any source.

For imports, `kind: "bundle"` accepts up to 80 mixed `gloss`, `sentence`,
`word`, `etymology`, and `part` tasks in one constrained-JSON inference.
The lexicon uses it only after dictionary sources fill everything they can,
and automatically falls back to individual requests if a bundle fails.

`GET /health` — `{"ok", "model", "ollama", "keyOk"}`; `keyOk` checks the
`X-API-Key` you send (null if none).

## Speed and quality

Before inference the service rotates the photo correctly, resizes its
long edge to **512 px** and encodes JPEG quality **65** (env:
`TAGGER_IMAGE_MAX_EDGE`, `TAGGER_JPEG_QUALITY`; was 768/70). Ollama uses a
4096-token context, disables thinking for constrained JSON calls, caps default output at 1200 tokens. CEFR replies
use compact keys, one anchor point instead of a box, and `TAGGER_CEFR_NUM_PREDICT` **820**; this cuts repeated JSON
and coordinate tokens while preserving the 18-label target. The same pass blocks explicit adult content before a
photo becomes visible. Database-import translations use at most two of four model slots,
reserving GPU capacity for a learner waiting on a photo. The model stays
loaded (`TAGGER_KEEP_ALIVE=-1`). Disk cache keys include a prep fingerprint
(`edge{N}q{Q}`) so changing JPEG/edge invalidates stale vision replies.
Results are cached in `tagger/cache` by photo hash, model, prompt version,
prep, language and focus. Lexicon import tagging defaults to
`mode=cefr` (`LEXICON_TAG_MODE=cefr`, prompt `photo-tags-cefr-bands-v3`): at least 3 labels per CEFR band A1–C2, with one top-up pass for short bands; set `legacy` to restore multi-focus looks. Enrich (`lexicon/tools/enrich_cefr_tags.py`) keeps `--skip-enriched`
and **defers** the second `/score` pass by default (provisional 0.8 for
grounded CEFR labels); pass `--score` to force the vision check. Parallel
requests go to llama-server (above); Ollama itself stays serial. Model
defaults to `qwen3.5:4b`; pass `--model` to compare or temporarily use another local model.
The app tags in the background, and labels remain editable (spec: 可改).

### Revert speed tweaks

```bat
set TAGGER_IMAGE_MAX_EDGE=1024
set TAGGER_JPEG_QUALITY=82
set TAGGER_CEFR_NUM_PREDICT=1400
set LEXICON_TAG_MODE=legacy
```

Then restart `start_tagger.bat`. For enrich, pass `--score` to restore the
second scoring pass. Do not lower `per_level` or drop CEFR bands A1–C2.

Recommended Ollama user environment on the RTX 5060 Laptop GPU (used
only with `TAGGER_BACKEND=ollama`; four llama-server slots measured best —
eight were slower):

```text
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1
```

## Other devices

The API listens on 127.0.0.1 only, so only this PC can reach it. For a
phone, the spec's option is a Cloudflare Tunnel
(`cloudflared tunnel --url http://127.0.0.1:8765`), which makes it
reachable from the internet — the API key is then the only protection.

## Tests

```bash
python -m pytest tests/test_tagging_server.py
```
