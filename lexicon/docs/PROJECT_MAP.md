# Project map (read this instead of exploring; card #158)

Line counts as of 2026-10-17. **Big files: search first, then read a range** (see "Reading big files").

## Services and ports
| What | Where | Port |
|---|---|---|
| Admin UI (React/Vite, hot reload) | `lexicon/frontend/` | 5173 (`/ui/`, `/api` → proxy to 8770) |
| Lexicon API (FastAPI) | `lexicon/backend/app/` (`main.py` registers routers) | 8770 — agents use **5173/api** only |
| Workers (text / images / tags lanes) | `lexicon/worker/worker.py` | — |
| Tagger (Qwen via llama-server) | `tagger/tagging_server.py`, config `tagger/tagger_config.py` | 8765 / 8790 |
| Learner app (Flutter) | `app/` | web build on 8123 (`serve_app.py`) |
| Card studio | `card_preview/` | 8772 |
| DB | PostgreSQL 17, `lexicon` + `lexicon_test`; migrations `lexicon/migrations/versions/00NN_*.py` | 5432 |

## Backend (`lexicon/backend/app/`)
- `images.py` **2151 lines** — picture fetch, tagging queue (`tag_pending`, `_tag_asset`), CEFR tag levels. Never read whole.
- `models.py` 877 — all SQLAlchemy tables (`AgentTask`, `IssueReport`, `ImageAsset`, `Lexeme`, `Sense`…).
- `pipeline.py` 805, `exporter.py` 700 (app pack export), `materialize.py` 460, `jobs.py` 577 (import jobs).
- `tasks.py` 649 — 排程 board API (`/tasks`, `/schedule/*`, difficulty, agents-info). `agent_usage.py` — AI usage panel.
- `issues.py` — 問題回報 API. `quality.py` 495, `qc.py`, `qc_fix.py` — quality rules. `policies.py` 428.
- `adapters/` — dictionary sources (kaikki 810, local 792, ai 311, tatoeba, ecdict, cmudict, oewn, commons…).

## Tools (`lexicon/tools/`)
- Board: `task.py` (local, key from env), `launch_agent.py` (dispatch), `pick_card.py`, `grade_cards.py`,
  `card_difficulty.py`, `agent_capabilities.json`, `agent_preamble.md`.
- Quality: `qc.py` (loads .env itself — run it, never open .env), `qc_golden.py` (`--out`, `--force`), `qc_snapshot.py`,
  `quality_ai.py`, `apply_quality_decisions.py`, `recompute_photo_tag_cefr.py`, `enrich_cefr_tags.py`.
- Photo labelling fallback (#327/#330): `tag_fallback.py` (status / ask / apply / golden / run, config
  `tag_fallback_config.json`) → backend `app/vision_fallback.py`; Codex/Cursor CLI look at the photo when Qwen
  is paused or the queue is long; cost log `lexicon/logs/tag_fallback/cost.jsonl`.
- Files starting with `_` and `cardNN_*.py` are one-off scripts from earlier cards — reuse them for the same check.

## Flutter app (`app/`)
- `lib/services/word_database_repository.dart` **1371**, `lexicon_pack.dart` 711, `flashcard_session.dart` 675, `photo_word_session.dart` 412.
- `lib/screens/` (photo_detail 605, word_detail 562, camera 550, word_database 529…), `lib/widgets/` (flashcard_back 409…), `lib/models/` (word_entry 648).
- Tests `app/test/` (64 files; screens_test 622, session_test 523). Simulations `app/test/simulation/` + `run_round.py` → `app/build/rounds/<n>/summary.json`.

## French lexicon (fr→en, card #325)
- Same schema and field catalog as English; rows split by `target_language='fr'` / `native_language='en'`.
  Sources, licences and the design decision: `docs/french_sources.md`. Admin UI: sidebar 「法文詞庫」 or `#/lang/fr`.
- Trial / rerun on a few words: `python lexicon/tools/card325_fr_trial.py run <words>` (foreground, fresh code);
  QC for the French pack: `python lexicon/tools/qc.py check --live --target fr --native en --out <file>` (golden `fr_v1`).

## Data you should NOT read whole
- `lexicon/logs/agents/` is ~700 MB: `*pack*.json` are 100+ MB app-pack dumps, `*.jsonl` up to 18 MB. Use Python/jq to
  count or extract; read only `card<ID>.result.md` and the latest `card<ID>.prompt.txt` of a card.
- `lexicon/quality/entry_flags.json` (4.4k lines), `decisions.json` (1.7k) — query with Python.
- `lexicon/raw-data/`, `lexicon/media/` — data files, never open in the editor.
- Secrets — never open: `lexicon/.env`, `tagger/.api_key`, `app/tagging.local.json`.

## Reading big files (token budget)
- Find first: `rg -n "def _tag_asset" lexicon/backend/app/images.py` → read ~60 lines around the hit
  (`Get-Content f | Select-Object -Skip 1180 -First 60`, or your Read tool with offset/limit).
- Board state: `GET /api/tasks/<id>` or `python lexicon/tools/pick_card.py --agent X --all`. **Don't dump**
  `/api/schedule/board` (50 KB+ of JSON) into your context.
- Cap output: `| Select-Object -First 80`, `pytest -q`, `flutter test --reporter compact 2>&1 | Select-Object -Last 40`.

## Standing cards: reuse, don't rewrite
| Card | Check | Reuse |
|---|---|---|
| #3 缺圖 | `GET /api/schedule/board` metric `pictures_missing` | `lexicon/tools/_imgstat.py`, `lexicon/backend/app/image_fetch_audit.py` |
| #4 標籤佇列 | metric `labels_pending` | `lexicon/tools/_qstats.py` |
| #5 標籤分級 | metric `label_levels` | `lexicon/tools/_card97_cefr_audit.py`, `recompute_photo_tag_cefr.py` |
| #12 模擬使用者 | `python app/test/simulation/run_round.py` | `lexicon/docs/agents/simulation_usability.md` |
| #38 相似詞只從已有字 | live audit | `lexicon/logs/agents/card38_cursor_audit.py`, `card38_live_audit.py` |
