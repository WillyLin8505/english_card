"""Fallback photo labelling when Qwen is paused or its queue is too long (問題回報 #327).

Codex CLI (ChatGPT, ``codex exec -i <photo>``) or Cursor CLI looks at the photo and
returns the same label shape as the Qwen tagger (word, part of speech, box/point,
visual confidence). The labels then go through the normal pipeline: made-up phrases
split, CEFR level from the dictionary (classify_tag_cefr, never the model), the 80%
rule, 3-4 per band, sense binding and auto-accept (images._settle). Model names are
stored as ``cefr+codex_vision`` / ``cefr+cursor_vision`` and every label carries
``source``.

Asking (slow, parallel, no database) and applying (one picture per transaction, under
the same advisory lock the Qwen workers use) are separate steps: a photo Qwen labelled
in the meantime is skipped. Tool: ``lexicon/tools/tag_fallback.py``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from . import agent_pause, config, images, models as m

ROOT = Path(__file__).resolve().parents[3]
STATE_DIR = ROOT / 'lexicon' / 'state'
DISPATCH_STATE = STATE_DIR / 'dispatch_state.json'
FALLBACK_STATE = STATE_DIR / 'tag_fallback_state.json'
CODEX = os.environ.get('CODEX_CMD', r'C:\Users\USER\AppData\Roaming\npm\codex.cmd')
CURSOR_PS1 = str(Path(os.environ.get('LOCALAPPDATA', r'C:\Users\USER\AppData\Local'))
                 / 'cursor-agent' / 'cursor-agent.ps1')
POWERSHELL = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'

BACKENDS = {'codex': 'codex_vision', 'cursor': 'cursor_vision'}
# dispatch_tick's rest-until-reset entries (lexicon/state/dispatch_state.json "limits").
QUOTA_AGENT = {'codex': 'Codex', 'cursor': 'Cursor CLI'}
LIMIT_RE = re.compile(r'usage limit|hit your (usage )?limit|limit reached|weekly limit|'
                      r'out of (usage|credits|requests)|spend(ing)? limit|you\'ve reached your|'
                      r'you have reached your|upgrade to (pro|ultra|a higher)', re.I)
POS = {'noun', 'verb', 'adjective', 'adverb', 'phrase'}

PROMPT = """Look at the attached photo. You are a vision tagger for an English vocabulary app. \
Do not run any commands, browse or edit files; answer from the image only.
Return ONLY one JSON object, no prose:
{{"adult": false, "candidates": [{{"word": "...", "pos": "noun|verb|adjective|adverb|phrase", \
"box": [x0, y0, x1, y1], "visualConfidence": 0.0}}]}}
- {count} English words or dictionary phrases (lowercase, base form) that are clearly visible or \
clearly true of this photo: objects, parts, colours, materials, actions, qualities. No brand or \
proper names, no made-up multi-word descriptions.
- Spread them over CEFR difficulty {levels} (about 3-4 each); a harder word only if it truly \
describes what is visible.
- box: normalized 0-1 coordinates of the region showing it (whole photo = [0, 0, 1, 1]).
- visualConfidence: 0-1, how sure you are the word is visibly correct for this photo; be strict.
- "adult": true only if the photo shows explicit sexual content or nudity.{exclude}"""


# ---------------------------------------------------------------- queue / quota

def pending_count(s) -> int:
    return s.scalar(select(func.count()).select_from(m.ImageAsset).where(
        m.ImageAsset.status == 'ready', *images._tag_eligible())) or 0


def qwen_busy(s, threshold: int) -> str | None:
    """Why the fallback should run now, or None (Qwen keeps the queue)."""
    if agent_pause.is_paused('Qwen'):
        return 'Qwen 暫停'
    n = pending_count(s)
    return f'待打標 {n} 張 ≥ 門檻 {threshold}' if n >= threshold else None


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _until(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def limited(backend: str, now: datetime | None = None) -> str | None:
    """'…到 HH:MM' while the backend's quota is used up (dispatch_state limits or our own)."""
    now = now or datetime.now(timezone.utc)
    for src, until in (('dispatch_state', _read_json(DISPATCH_STATE).get('limits', {}).get(QUOTA_AGENT[backend])),
                       ('tag_fallback', _read_json(FALLBACK_STATE).get('limits', {}).get(backend))):
        dt = _until(until)
        if dt and dt > now:
            return f'{QUOTA_AGENT[backend]} 額度用完（{src}），到 {dt.isoformat(timespec="minutes")}'
    return None


def reset_after(text: str) -> timedelta:
    """'resets in 6 days' → 6 days; unknown → 5 hours (dispatch_tick's default rest)."""
    hit = re.search(r'resets? in (\d+)\s*(day|hour|minute)', text or '', re.I)
    if not hit:
        return timedelta(hours=5)
    n, unit = int(hit.group(1)), hit.group(2).lower()
    return timedelta(**{f'{unit}s': n})


def mark_limited(backend: str, text: str) -> datetime:
    until = datetime.now(timezone.utc) + reset_after(text)
    state = _read_json(FALLBACK_STATE)
    state.setdefault('limits', {})[backend] = until.isoformat(timespec='seconds')
    FALLBACK_STATE.parent.mkdir(parents=True, exist_ok=True)
    FALLBACK_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    return until


class QuotaExhausted(RuntimeError):
    """The CLI reported a usage limit: stop the batch, don't fail the picture."""


# ---------------------------------------------------------------- asking

def build_prompt(levels=images.CEFR_LEVELS, exclude=(), count: str = '18-24') -> str:
    ex = ''
    if exclude:
        ex = '\n- Do not repeat these words: ' + ', '.join(list(exclude)[:60]) + '.'
    return PROMPT.format(count=count, levels=', '.join(levels), exclude=ex)


def parse_answer(text: str) -> dict:
    """The JSON object in the model's last message (tolerates ``` fences / prose)."""
    text = (text or '').strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError(f'備援回覆不是 JSON：{text[:200]}')
    payload = json.loads(text[start:end + 1])
    if not isinstance(payload, dict) or not isinstance(payload.get('candidates'), list):
        raise ValueError('備援回覆缺少 candidates 清單')
    return payload


def _usage_codex(events: str) -> dict:
    usage = {}
    for line in events.splitlines():
        if '"usage"' not in line:
            continue
        try:
            got = json.loads(line).get('usage')
        except ValueError:
            continue
        if isinstance(got, dict):
            for k, v in got.items():
                if isinstance(v, (int, float)):
                    usage[k] = usage.get(k, 0) + v
    return usage


def ask(backend: str, image_path: Path, prompt: str, *, model: str | None = None,
        effort: str = 'low', timeout: int = 300) -> dict:
    """One look at one photo → {'payload', 'seconds', 'usage', 'model'}.

    Runs in its own empty temp folder (the CLI sees only the photo copy) and never
    gets write access. Raises QuotaExhausted on a usage-limit message.
    """
    if backend not in BACKENDS:
        raise ValueError(f'unknown backend {backend}')
    work = Path(tempfile.mkdtemp(prefix=f'tagfb_{backend}_'))
    try:
        photo = work / ('photo' + (image_path.suffix.lower() or '.jpg'))
        shutil.copyfile(image_path, photo)
        started = time.perf_counter()
        if backend == 'codex':
            cmd = [CODEX, 'exec', '-s', 'read-only', '--skip-git-repo-check', '--ephemeral',
                   '--ignore-user-config', '-c', f'model_reasoning_effort={effort}',
                   '-i', str(photo), '--json', '-o', str(work / 'answer.txt')]
            if model:
                cmd += ['-m', model]
            r = subprocess.run(cmd + ['-'], cwd=work, input=prompt.encode('utf-8'),
                               capture_output=True, timeout=timeout, creationflags=0x08000000)
            log = (r.stdout + r.stderr).decode('utf-8', 'replace')
            answer = (work / 'answer.txt').read_text(encoding='utf-8', errors='replace') \
                if (work / 'answer.txt').is_file() else ''
            usage = _usage_codex(log)
        else:
            cmd = [POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', CURSOR_PS1,
                   '-p', '--trust', '--mode', 'ask', '--output-format', 'json']
            if model:
                cmd += ['--model', model]
            pointer = (f'The photo is the file {photo.name} in the current folder; open it with your '
                       f'file read tool to see it. ' + ' '.join(prompt.split()))
            r = subprocess.run(cmd + [pointer], cwd=work, stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=timeout, creationflags=0x08000000)
            log = (r.stdout + r.stderr).decode('utf-8', 'replace')
            answer, usage = log, {}
            try:
                out = json.loads(r.stdout.decode('utf-8', 'replace'))
                answer = str(out.get('result') or '')
                usage = out.get('usage') if isinstance(out.get('usage'), dict) else {}
            except ValueError:
                pass
        seconds = round(time.perf_counter() - started, 1)
        if LIMIT_RE.search(log[-4000:]) and not answer.strip().startswith('{'):
            raise QuotaExhausted(next((ln.strip() for ln in log.splitlines() if LIMIT_RE.search(ln)),
                                      'usage limit')[:300])
        if r.returncode != 0 and not answer.strip():
            raise ValueError(f'{backend} 結束碼 {r.returncode}：{log.strip()[-300:]}')
        return {'payload': parse_answer(answer), 'seconds': seconds, 'usage': usage,
                'model': model or 'default'}
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- applying

def _clamp(v) -> float:
    return round(min(1.0, max(0.0, float(v))), 3)


def to_tag(candidate: dict, source: str) -> dict | None:
    """A model candidate in the Qwen tagger's stored shape (point from the box centre)."""
    word = ' '.join(str(candidate.get('word') or '').strip().lower().split())
    if not word or len(word) > 40 or len(word.split()) > 3:
        return None
    pos = str(candidate.get('pos') or 'noun').strip().lower()
    pos = {'adj': 'adjective', 'adv': 'adverb'}.get(pos, pos)
    tag = {'word': word, 'pos': pos if pos in POS else 'noun', 'point': None, 'box': None,
           'source': source}
    box = candidate.get('box')
    try:
        if isinstance(box, (list, tuple)) and len(box) == 4:
            x0, y0, x1, y1 = (_clamp(v) for v in box)
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            if x1 > x0 and y1 > y0:
                tag['box'] = [x0, y0, x1, y1]
                tag['point'] = [round((x0 + x1) / 2, 3), round((y0 + y1) / 2, 3)]
        point = candidate.get('point')
        if tag['point'] is None and isinstance(point, (list, tuple)) and len(point) == 2:
            tag['point'] = [_clamp(point[0]), _clamp(point[1])]
        conf = candidate.get('visualConfidence')
        if conf is not None:
            tag['visualConfidence'] = _clamp(conf)
    except (TypeError, ValueError):
        return None
    return tag


def label(s, asset, answers: list[dict], backend: str) -> dict:
    """Run the normal label pipeline on the CLI's answers and settle the picture.

    The visual confidence is the label's score (the CLI has no yes-token
    probability); the 80% rule, dictionary CEFR, band caps and sense binding are
    unchanged. Existing scored labels of a safe picture are kept, as in _tag_asset.
    """
    source = BACKENDS[backend]
    if any(a['payload'].get('adult') is True for a in answers):
        images._block_unsafe(s, asset)
        return {'blocked': True, 'passed': 0}
    keep = images.own_words(s, asset)
    if asset.safety_status == 'safe':
        existing = [images.classify_tag_cefr(s, t) for t in (asset.tags or [])]
        passed = [t for t in existing if images.tag_level(t) and (t.get('score') or 0) >= images.TAG_PASS
                  and not t.get('scoreDeferred')]
        passed, dropped = images._select_cefr_tags(passed, keep)
        dropped = list(dropped)
    else:
        passed, dropped = [], []
    seen = [str(t.get('word', '')) for t in passed]
    for answer in answers:
        known = {w.lower() for w in seen}
        new = []
        for c in answer['payload'].get('candidates') or []:
            tag = to_tag(c, source) if isinstance(c, dict) else None
            if tag and tag['word'] not in known:
                known.add(tag['word'])
                seen.append(tag['word'])
                new.append(images.classify_tag_cefr(s, tag))
        new, aside = images.split_made_up(s, new, seen)
        dropped.extend(aside)
        seen.extend(t['word'] for t in new if t.get('splitFrom'))
        for tag in new:
            if tag.get('score') is None:
                tag['score'] = tag.get('visualConfidence')
            if tag.get('splitFrom') and tag.get('score') is None:
                tag['score'] = next((x.get('visualConfidence') for x in aside
                                     if x.get('word') == tag['splitFrom']), None)
            if images.tag_level(tag) and (tag.get('score') or 0) >= images.TAG_PASS:
                passed.append(tag)
            else:
                tag.setdefault('dropReason', '缺少 CEFR 等級' if not images.tag_level(tag)
                               else '圖片辨識信心低於 80%')
                dropped.append(tag)
        passed, overflow = images._select_cefr_tags(passed, keep)
        for tag in overflow:
            tag.setdefault('dropReason', '該等級已滿 4 個')
        dropped.extend(overflow)
    model = f'cefr+{source}:{answers[0].get("model", "default")}' if answers else f'cefr+{source}'
    images._settle(s, asset, passed, dropped, model, done=True)
    asset.tag_attempts, asset.tag_error, asset.tag_retry_at = 0, None, None
    return {'blocked': False, 'passed': len(asset.tags or []),
            'bands': images.cefr_counts(asset.tags or [])}


def still_eligible(s, asset_id: int) -> bool:
    return s.scalar(select(func.count()).select_from(m.ImageAsset).where(
        m.ImageAsset.id == asset_id, m.ImageAsset.status == 'ready', *images._tag_eligible())) > 0


def pick_batch(s, size: int, exclude: set[int] = frozenset()) -> list[int]:
    """Newest eligible pictures first — the Qwen workers take the oldest (id ASC)."""
    rows = s.scalars(select(m.ImageAsset.id).where(
        m.ImageAsset.status == 'ready', *images._tag_eligible())
        .order_by(m.ImageAsset.id.desc()).limit(size + len(exclude))).all()
    return [i for i in rows if i not in exclude][:size]


def media_path(asset) -> Path:
    return config.MEDIA / asset.path
