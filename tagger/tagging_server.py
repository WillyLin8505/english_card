"""Photo-tagging API for 拍照學英文 - spec-01 sections 2 and 3:

    運算環境   Predator 上 Ollama + Qwen3-VL-4B（Q4）
    本機 API   127.0.0.1:8765
    可選連線   Cloudflare Tunnel
    請求格式   Web: raw JPEG body + X-API-Key；原生: 可使用 multipart

This is stage 1 of the spec's two-stage recognition (第一階段 · 理解照片):
the model looks at the photo and proposes 8-10 labels - nouns, verbs,
adjectives, adverbs and phrases - each with its picture context.
Stage 2 (choosing at most 5 to learn, by level, personal vocabulary,
relevance, usefulness and part-of-speech mix) runs in the app, because
it needs the learner's own vocabulary state. "模型不得直接決定最後五個詞".

POST /tag?level=B1&lang=en&native=zh-TW[&focus=harder][&exclude=cup,mug]\n        POST /tag?mode=cefr&lang=en[&per_level=3][&exclude=...]  (>=3 labels per A1-C2)
    Header  X-API-Key: <key>
    Body    the image - raw (Content-Type: image/jpeg) or multipart/form-data
            with an "image" part.
    level   the learner's CEFR level; candidates centre on it.
    focus   harder | easier | actions | descriptions - a top-up call when
            the app's candidate pool runs short (候選不足才重新呼叫模型).
    exclude words already in the pool.
    Reply   {"candidates": [{"word": "mug", "lemma": "mug", "pos": "noun",
                             "evidence": "white mug on the table",
                             "point": [0.64, 0.41], "visualConfidence": 0.95,
                             "inferred": false}, ...],
             "model": "...", "elapsedMs": 9120}
            point = where the evidence is, as fractions (0-1) of the image.
            Meanings, CEFR, pronunciation, examples and relations come from
            the downloaded offline word database, never from this model.

GET /health  -> {"ok": true, "model": ..., "ollama": true, "keyOk": true|false|null,
                 "backend": "llamacpp", "backendUrl": ..., "backendError": null|"why"}
                (ok/ollama are false when llama-server/Ollama is down)

Standard library only; `wordfreq` (pip) and data/raw/cmudict.dict are
used when present. Run:  python tagger/tagging_server.py
The API key is read from TAGGER_API_KEY, else tagger/.api_key (created
with a random key on first run and printed at start-up).
"""

from __future__ import annotations

import argparse
import base64
import collections
import contextlib
import hashlib
import io
import json
import math
import os
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
from inference_control import PrioritySlots, is_background, is_qwen_paused
from repetition_guard import read_cefr_stream
import tagger_config
tagger_config.apply_defaults()  # card #70: bare start == start_tagger.bat

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KEY_FILE = os.path.join(HERE, '.api_key')
CMUDICT = os.path.join(ROOT, 'data', 'raw', 'cmudict.dict')
DEFAULT_MODEL = 'qwen3.5:4b'
MAX_BODY = 20 * 1024 * 1024
PROMPT_VERSION = 'photo-tags-context-v11-harder-level'
CACHE_DIR = os.path.join(HERE, 'cache')
MODEL_CONTEXT = int(os.environ.get('TAGGER_NUM_CTX', '4096'))
MODEL_MAX_TOKENS = int(os.environ.get('TAGGER_NUM_PREDICT', '1200'))
TRANSLATE_MAX_TOKENS = int(os.environ.get('TAGGER_TRANSLATE_NUM_PREDICT', '2400'))
# Model requests sent to Ollama at once. Match OLLAMA_NUM_PARALLEL: Ollama then
# decodes them together, which raises total throughput on one GPU. 1 = serial.
INFERENCE_PARALLEL = max(1, int(os.environ.get('TAGGER_PARALLEL', '1')))
# 'ollama' (default) or 'llamacpp'. Ollama 0.35 runs qwen3.5 one request at a
# time ("architecture does not currently support parallel requests"); the
# llama-server it ships, started with -np N (start_llm.bat), decodes N at once.
BACKEND = os.environ.get('TAGGER_BACKEND', 'ollama').strip().lower()
LLAMACPP_URL = os.environ.get('TAGGER_LLAMACPP_URL', 'http://127.0.0.1:8790').rstrip('/')
# Ollama's parameters for qwen3.5:4b (its params layer); without the presence
# penalty llama-server lets word lists repeat until the token cap.
LLAMACPP_SAMPLING = json.loads(os.environ.get(
    'TAGGER_LLAMACPP_SAMPLING', '{"presence_penalty": 1.5, "top_k": 20, "top_p": 0.95}'))
IMAGE_MAX_EDGE = int(os.environ.get('TAGGER_IMAGE_MAX_EDGE', '768'))
IMAGE_JPEG_QUALITY = int(os.environ.get('TAGGER_JPEG_QUALITY', '70'))
# -1 = keep model loaded (best for batch tagging on one GPU). Set TAGGER_KEEP_ALIVE=5m to unload.
KEEP_ALIVE = os.environ.get('TAGGER_KEEP_ALIVE', '-1')
try:
    KEEP_ALIVE = int(KEEP_ALIVE)
except ValueError:
    pass  # duration string like '10m' is valid for Ollama
# Prep fingerprint included in disk-cache keys so JPEG/edge tweaks invalidate stale vision replies.
IMAGE_PREP_VERSION = f'edge{IMAGE_MAX_EDGE}q{IMAGE_JPEG_QUALITY}'
LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
POS = ['noun', 'verb', 'adjective', 'adverb', 'phrase']
FOCUS = {
    'harder': 'This time prefer specific, precise labels instead of broad category names. '
              'Every label must be a more advanced word than the usual everyday ones '
              '(e.g. "ergonomic", "cluttered", "luminous", "peripheral"), not a synonym of a '
              'basic word. Include verbs and adjectives, not only nouns.',
    'easier': 'This time prefer common, broad everyday labels.',
    'actions': 'This time every label must be a verb or action phrase for something visibly '
               'happening or implied (e.g. "stroll", "queue up", "gaze"); no nouns.',
    'descriptions': 'This time every label must be an adjective or adverb describing what is seen.',
}

# Learning and native languages (spec section 7: 英文、法文、繁體中文).
LANGS = {
    'en': 'English',
    'fr': 'French',
    'zh-TW': 'Traditional Chinese (as used in Taiwan)',
}
NATIVE_RULE = {
    'zh-TW': '「meaning」必須是台灣使用的繁體中文詞彙（例如：麵包、蘋果、義大利麵、起司、奶油刀、'
             '馬克杯、優格、番茄、馬鈴薯、鳳梨、鮭魚、湯匙、影片、軟體、計程車、公車、機車、捷運、'
             '腳踏車、冷氣、飯店、便利商店），不可使用簡體字或中國大陸用語'
             '（不要寫：意大利麵、芝士、酸奶、西紅柿、土豆、菠蘿、三文魚、勺子、視頻、軟件、'
             '出租車、公交車、摩托車、地鐵、自行車、空調、酒店、便利店）。',
    'en': 'Write "meaning" as a short, simple English gloss.',
    'fr': 'Write "meaning" as a short French translation.',
}

CANDIDATE_SCHEMA = {
    'type': 'object',
    'properties': {
        'safe': {'type': 'boolean'},
        'candidates': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'word': {'type': 'string'},
                    'pos': {'type': 'string', 'enum': POS},
                    'evidence': {'type': 'string'},
                    'point': {'type': 'array', 'items': {'type': 'integer'}},
                    'box': {'type': 'array', 'items': {'type': 'integer'}},
                },
                'required': ['word', 'pos', 'evidence', 'point', 'box'],
            },
        }
    },
    'required': ['safe', 'candidates'],
}

ENRICH_SCHEMA = {
    'type': 'object',
    'properties': {
        'meaning': {'type': 'string'},
        'definition': {'type': 'string'},
        'ipa': {'type': 'string'},
        'examples': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'text': {'type': 'string'}, 'translation': {'type': 'string'}},
                'required': ['text', 'translation'],
            },
        },
        'translations': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['meaning', 'definition', 'ipa', 'examples', 'translations'],
}


def _shift(level: str, by: int) -> str:
    return LEVELS[min(max(LEVELS.index(level) + by, 0), len(LEVELS) - 1)]


def build_prompt(level: str, lang: str = 'en', native: str = 'zh-TW',
                 focus: str | None = None, exclude: list[str] | None = None) -> str:
    """Describe only visible labels and their photo context.

    ``level`` and ``native`` stay in the public API for compatibility. Difficulty,
    translations and full word data are resolved from the offline database.
    """
    lang_name = LANGS[lang]
    count = '4 to 6' if focus in ('harder', 'actions', 'descriptions') else '10 to 12'
    if focus == 'harder' and lang == 'en' and level in LEVELS:
        count = '8 to 10'  # the level filter in candidates() trims it back to 6
    lines = [
        f'Inspect this photo and return {count} useful {lang_name} labels.',
        'First check content safety. Set safe=false and return no candidates for pornography, '
        'sexual activity, exposed genitals, or explicit adult nudity. Otherwise set safe=true. '
        'Ordinary family photos, swimwear, breastfeeding, art and medical contexts are safe '
        'unless they are explicitly sexual.',
        'Only identify what the photo supports: objects, visible actions, visible qualities, '
        'spatial relations and short scene phrases. Do not translate, define, estimate CEFR, '
        'write example sentences, or provide pronunciation.',
        'Use concrete nouns, verbs, adjectives, adverbs and short phrases only when directly '
        'visible. There is no part-of-speech quota. Prefer one clear label for each distinct '
        'visual idea; do not pad with synonyms or descriptions of the photograph itself.',
        'Use ordinary vocabulary, not company, product, model or person names. Ignore words '
        'that are only read from logos, packaging, watermarks or signs.',
    ]
    if lang == 'en' and level in LEVELS and focus != 'easier':
        lines.append(
            f'The learner is at CEFR level {level}. Aim most labels at words a {level} learner '
            f'is about to learn, i.e. from {_shift(level, -1)} to {_shift(level, 1)}; do not '
            'fill the list with A1 words such as "man", "tree", "car", "building" unless they '
            'are all the photo offers. Include at least 2 verbs or adjectives and at least 2 '
            f'labels above {level} whenever the photo supports them.')
    if focus in FOCUS:
        lines.append(FOCUS[focus])
    if focus == 'harder' and lang == 'en' and level in LEVELS:
        lines.append(
            f'The learner is at CEFR {level}: every label must be rare, advanced vocabulary '
            f'at CEFR {_shift(level, -1)} to {_shift(level, 1)} or above (words most '
            'native speakers rarely use in daily talk, e.g. "iridescent", "dilapidated", '
            '"verdant"); never a word a B1 learner already knows.')
    lines += [
        'For each candidate give:',
        f'- word: dictionary form (singular noun, base verb), lowercase, in {lang_name}',
        '- pos: noun, verb, adjective, adverb or phrase',
        '- evidence: at most 8 English words describing its meaning in this photo',
        '- point: [x, y] of that evidence, relative coordinates from 0 to 1000',
        '- box: [x1, y1, x2, y2] around that evidence (the object, or the area of the action '
        'or quality), relative coordinates from 0 to 1000',
    ]
    if exclude:
        lines.append('Do not repeat these words: ' + ', '.join(exclude[:40]) + '.')
    lines.append('Reply with JSON only.')
    return '\n'.join(lines)


SCORE_PROMPT_VERSION = 'label-check-v2'
SCORE_MAX_LABELS = 24
CEFR_PROMPT_VERSION = 'photo-tags-visible-v14-no-quotas'
CEFR_TAGS_PER_LEVEL = 3
# A1/A2 may not exceed this many labels each (default = per_level) so beginners
# cannot consume TAGS_MAX (~18) and leave B2-C2 with no slots.
CEFR_BEGINNER_LEVELS = ('A1', 'A2')
CEFR_BEGINNER_MAX_PER_LEVEL = int(os.environ.get(
    'TAGGER_CEFR_BEGINNER_MAX', str(CEFR_TAGS_PER_LEVEL)))
CEFR_MAX_TOKENS = int(os.environ.get('TAGGER_CEFR_NUM_PREDICT', '820'))
# Experimental until the full golden-photo comparison passes (card44).
CEFR_REPEAT_GUARD = os.environ.get('TAGGER_CEFR_REPEAT_GUARD', '0') == '1'
CEFR_CANDIDATE_SCHEMA = {
    'type': 'object',
    'properties': {
        'safe': {'type': 'boolean'},
        'candidates': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'w': {'type': 'string'},
                    'p': {'type': 'string', 'enum': ['n', 'v', 'a', 'd', 'p']},
                    'x': {'type': 'integer'},
                    'y': {'type': 'integer'},
                },
                'required': ['w', 'p', 'x', 'y'],
            },
        }
    },
    'required': ['safe', 'candidates'],
}
SCORE_SCHEMA = {
    'type': 'object',
    'properties': {
        'checks': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'word': {'type': 'string'}, 'shown': {'type': 'boolean'}},
                'required': ['word', 'shown'],
            },
        }
    },
    'required': ['checks'],
}



def build_cefr_prompt(lang: str = 'en', exclude: list[str] | None = None,
                      per_level: int = CEFR_TAGS_PER_LEVEL,
                      beginner_max: int | None = None) -> str:
    """Ask for visible dictionary-form labels. Levels come from the lexicon
    later (decision 2 / P2); the model must not invent CEFR bands.
    ``per_level`` still sizes the list (~6 * per_level visible labels)."""
    lang_name = LANGS[lang]
    n = max(6, int(per_level) * 6)
    lines = [
        f'Inspect this photo and return English learning labels for a {lang_name} learner.',
        'First check content safety. Set safe=false and return candidates=[] for pornography, '
        'sexual activity, exposed genitals, or explicit adult nudity. Otherwise set safe=true. '
        'Ordinary family photos, swimwear, breastfeeding, art and medical contexts are safe '
        'unless explicitly sexual.',
        f'Return up to {n} distinct labels for things that are clearly visible '
        '(objects, parts, materials, actions, qualities). Do not invent CEFR levels; '
        'do not pad the list to fill difficulty bands. Cover the same visible regions with '
        'a useful vocabulary range: common everyday words plus precise, formal, literary or '
        'technical nouns, verbs and adjectives whose meanings are directly visible. Examples: '
        'wood / wooden / grain / rustic; glass / transparent / reflective. The lexicon assigns '
        'the real level later, so never guess a level.',
        'Mix parts of speech only when visible: nouns, verbs (visible actions), adjectives '
        '(visible qualities), adverbs and short phrases. There is no part-of-speech quota. '
        'Prefer a specific object or part to a generic category for the same region. '
        'Do not repeat synonyms for the same visual idea, and return fewer labels when needed. '
        'Avoid brand, product, model '
        'and person names. Ignore words only read from logos or watermarks. '
        'Do not invent objects that are not in the photo. Avoid meta labels that describe '
        'the photo itself (photo, image, background as "the picture", scene).',
        'For each candidate use these compact JSON keys:',
        f'- w: dictionary form (singular noun, base verb, adjective/adverb lemma), '
        f'lowercase, in {lang_name}',
        '- p: n noun, v verb, a adjective, d adverb, or p phrase',
        '- x and y: evidence point coordinates from 0 to 1000',
        '- b: optional [x1,y1,x2,y2] box from 0 to 1000 when the region is clear',
    ]
    if exclude:
        lines.append('Do not repeat these words: ' + ', '.join(exclude[:60]) + '.')
    lines.append('Reply with JSON only. Do not include an "l"/level field.')
    return "\n".join(lines)



def cefr_band_counts(items: list[dict]) -> dict[str, int]:
    """How many candidates currently sit in each CEFR band."""
    counts = {level: 0 for level in LEVELS}
    for item in items:
        level = str(item.get('cefr') or item.get('modelLevel') or '').strip().upper()
        if level in counts:
            counts[level] += 1
    return counts


def short_cefr_bands(items: list[dict], per_level: int,
                    beginner_max: int | None = None) -> list[str]:
    """CEFR bands that still have fewer than their target (beginners use beginner_max)."""
    if beginner_max is None:
        beginner_max = CEFR_BEGINNER_MAX_PER_LEVEL
    beginner_max = max(1, min(int(beginner_max), per_level))
    counts = cefr_band_counts(items)
    short = []
    for level in LEVELS:
        target = beginner_max if level in CEFR_BEGINNER_LEVELS else per_level
        # Beginners: fill up to min(per_level, beginner_max); never ask past beginner_max.
        if level in CEFR_BEGINNER_LEVELS:
            target = min(per_level, beginner_max)
        if counts[level] < target:
            short.append(level)
    return short


def build_cefr_topup_prompt(lang: str, short_levels: list[str], exclude: list[str],
                            per_level: int, counts: dict[str, int],
                            beginner_max: int | None = None) -> str:
    """Request new visible labels; only the caller's dictionary knows their bands."""
    return build_cefr_prompt(lang, exclude, per_level) + (
        '\nThis is an additional pass: return only new visible ideas not already listed. '
        'Return candidates=[] if no additional useful labels are visible. '
        'The dictionary will decide which difficulty bands these words belong to.')



def merge_cefr_topup(existing: list[dict], extra: list[dict], per_level: int,
                     beginner_max: int | None = None) -> list[dict]:
    """Append top-up labels only into bands that are still short. No padding with fakes.

    Beginner bands stop at ``beginner_max`` (default ``CEFR_BEGINNER_MAX_PER_LEVEL``);
    other bands stop at ``per_level``.
    """
    if beginner_max is None:
        beginner_max = CEFR_BEGINNER_MAX_PER_LEVEL
    beginner_max = max(1, min(int(beginner_max), per_level))
    items = list(existing)
    seen = {str(item.get('word', '')).strip().lower() for item in items}
    for item in extra:
        word = str(item.get('word', '')).strip().lower()
        level = str(item.get('cefr') or item.get('modelLevel') or '').strip().upper()
        if not word or word in seen or level not in LEVELS:
            continue
        cap = beginner_max if level in CEFR_BEGINNER_LEVELS else per_level
        if cefr_band_counts(items)[level] >= cap:
            continue
        seen.add(word)
        items.append(item)
    return items


def cap_cefr_beginner_bands(items: list[dict], beginner_max: int | None = None) -> list[dict]:
    """Drop excess A1/A2 labels (keep first-seen) so beginners cannot crowd higher bands."""
    if beginner_max is None:
        beginner_max = CEFR_BEGINNER_MAX_PER_LEVEL
    beginner_max = max(1, int(beginner_max))
    counts = {level: 0 for level in CEFR_BEGINNER_LEVELS}
    out: list[dict] = []
    for item in items:
        level = str(item.get('cefr') or item.get('modelLevel') or '').strip().upper()
        if level in counts:
            if counts[level] >= beginner_max:
                continue
            counts[level] += 1
        out.append(item)
    return out




def build_score_prompt(labels: list[dict], lang: str = 'en') -> str:
    lines = [
        f'Check each {LANGS[lang]} label against this photo.',
        'For every label answer shown = true only if the photo clearly shows it (the object, '
        'the action, the quality or the spatial relation); otherwise shown = false.',
        'Several different words may truthfully describe the same object or region. Judge each '
        'word independently and accept a visible quality even when it is not a separate object.',
        'Keep the labels in this order and copy each word exactly. Labels:',
    ]
    lines += [f'{i}. {l["word"]}' + (f' ({l["pos"]})' if l.get('pos') else '')
              for i, l in enumerate(labels, 1)]
    lines.append('Reply with JSON only.')
    return '\n'.join(lines)


def boolean_scores(logprobs: list[dict]) -> list[float]:
    """P(true) for each "shown" answer, in order, from the token logprobs:
    true against false among the top alternatives at that token."""
    out, text = [], ''
    for t in logprobs:
        token = t.get('token', '')
        word = token.strip()
        if word in ('true', 'false') and text.rstrip().endswith('"shown":'):
            alts = {word: t.get('logprob', 0.0)}
            for alt in t.get('top_logprobs') or []:
                alts.setdefault(alt.get('token', '').strip(), alt.get('logprob', -99.0))
            p_true = math.exp(alts['true']) if 'true' in alts else None
            p_false = math.exp(alts['false']) if 'false' in alts else None
            if p_true is not None and p_false is not None:
                out.append(p_true / (p_true + p_false))
            elif p_true is not None:
                out.append(p_true)
            else:
                out.append(1 - (p_false or 1.0))
        text += token
    return out


def _box(raw) -> list[float] | None:
    try:
        x1, y1, x2, y2 = (min(max(float(v) / 1000, 0.0), 1.0) for v in (raw or [])[:4])
    except (TypeError, ValueError):
        return None
    if x2 - x1 < 0.01 or y2 - y1 < 0.01:
        return None
    return [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)]


def _unit(v, default: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if v > 1:  # some replies use 0-100 or 0-10
        v = v / 100 if v > 10 else v / 10
    return round(min(max(v, 0.0), 1.0), 2)


_SPACE = re.compile(r'\s+')
_GENERIC_TEXT_LABELS = {'brand', 'label', 'logo', 'packaging', 'sign', 'text', 'watermark'}


def _looks_like_name_label(word: str, evidence: str) -> bool:
    """Reject a read brand/name without discarding the object carrying it.

    ``dell`` + ``Dell logo on the laptop`` is a name; ``cap`` + ``gray cap
    with logo`` is still a useful object label and must remain.
    """
    if word in _GENERIC_TEXT_LABELS:
        return False
    escaped = re.escape(word).replace(r'\ ', r'\s+')
    named_marker = rf'\b{escaped}\b\s+' \
                   r'(?:brand|company|logo|logotype|trademark|product|model)\b'
    generic_marker = r'\b(?:brand|company|product|model)\s+(?:logo|name)\b'
    return bool(re.search(named_marker, evidence, re.I)
                or (re.search(generic_marker, evidence, re.I)
                    and not re.search(rf'\b{escaped}\b', evidence, re.I)))


def to_candidates(raw: list[dict], lexicon: 'Lexicon | None' = None,
                  exclude: list[str] | None = None, lang: str = 'en') -> list[dict]:
    """Model output -> API candidates: cleaned, clamped, one per word."""
    seen = {w.strip().lower() for w in exclude or []}
    out: list[dict] = []
    for c in raw:
        word = _SPACE.sub(
            ' ', str(c.get('word') or c.get('w') or '').replace('_', ' ').strip().lower()
        ).strip(' .,"\'')
        if not word or word in seen or len(word) > 40:
            continue
        evidence = str(c.get('evidence') or c.get('e') or '').strip()[:120]
        # Reject descriptions of the photograph, not physical parts/materials.
        # Ambiguous words such as display, pattern and handle remain valid.
        if lang == 'en' and (word in {'close-up', 'close up', 'depict'} or
                (word in {'photo', 'photograph', 'image', 'scene', 'background'} and
                 (not evidence or re.search(r'\b(?:photo|picture|image) itself\b', evidence, re.I)))):
            continue
        if lang == 'en' and lexicon is not None and lexicon.is_foreign(word):
            continue
        lexical_phrase = getattr(lexicon, 'is_lexical_phrase', None) if lexicon else None
        if lang == 'en' and ' ' in word and callable(lexical_phrase) \
                and not lexical_phrase(word):
            continue
        if _looks_like_name_label(word, evidence):
            continue
        point = c.get('point') or (
            [c.get('x'), c.get('y')]
            if c.get('x') is not None and c.get('y') is not None else [])
        if len(point) < 2:
            continue
        seen.add(word)
        pos = str(c.get('pos') or c.get('p') or '').strip().lower()
        pos = {'n': 'noun', 'v': 'verb', 'a': 'adjective',
               'd': 'adverb', 'p': 'phrase'}.get(pos, pos)
        if pos not in POS:
            pos = 'phrase' if ' ' in word else 'noun'
        item = {
            'word': word,
            'lemma': word,
            'pos': pos,
            # Compatibility fields are intentionally empty. The Flutter app fills
            # them from its downloaded dictionary, never from the vision model.
            'meaning': '',
            'cefr': None,
            'modelLevel': None,
            'evidence': evidence,
            'point': [round(min(max(float(point[0]) / 1000, 0.0), 1.0), 4),
                      round(min(max(float(point[1]) / 1000, 0.0), 1.0), 4)],
            # The label's area (spec: 標籤座標／範圍), fractions x1, y1, x2, y2.
            'box': _box(c.get('box') or c.get('b')),
            'visualConfidence': 0.7,
            'usefulness': 0.5,
            'inferred': False,
        }
        # Card #631: the model answers (500,500) / (500,400) when it cannot place a scene word
        # (night, city); with no box that is a guess, not a location. Flag it for re-grounding.
        if not item['box'] and (round(float(point[0])), round(float(point[1]))) in ((500, 500), (500, 400)):
            item['pointUngrounded'] = True
        if lexicon is not None:
            item.update(lexicon.describe(word))
        out.append(item)
    return out


# What the model is doing right now, for the admin's 排程 page (GET /activity):
# every request from arrival to reply, with what the caller said it is for
# (X-Activity header: the word, field or picture) and when it started.
# Each entry also carries what went in (the sentences to translate, the
# labels to score), the picture it is about (X-Activity-Ref: image:<id>) and,
# once answered, what came out; the last finished ones stay in _RECENT.
_ACTIVITY: dict[int, dict] = {}
_ACTIVITY_LOCK = threading.Lock()
_ACTIVITY_SEQ = [0]
_RECENT: 'collections.deque[dict]' = collections.deque(maxlen=40)
_CURRENT = threading.local()
_STAGES = threading.local()


def stages_reset() -> dict:
    """Start this request's stage timings (問題回報 #229): where the seconds go."""
    _STAGES.data = {'queueMs': 0, 'prepMs': 0, 'modelMs': 0, 'modelCalls': 0, 'cacheHit': False}
    return _STAGES.data


def stage_add(name: str, value) -> None:
    data = getattr(_STAGES, 'data', None)
    if data is None:
        return
    if isinstance(value, bool):
        data[name] = data.get(name) or value
    else:
        data[name] = data.get(name, 0) + value


def note_llama_timings(timings) -> None:
    """llama-server's own split of the model time: prompt (image + text) vs decode."""
    if not isinstance(timings, dict):
        return
    for src, dst in (('prompt_ms', 'promptMs'), ('predicted_ms', 'decodeMs'),
                     ('prompt_n', 'promptTokens'), ('predicted_n', 'decodeTokens')):
        if isinstance(timings.get(src), (int, float)):
            stage_add(dst, round(timings[src]) if dst.endswith('Ms') else int(timings[src]))


@contextlib.contextmanager
def activity(kind: str, what: str, ref: str = '', inputs: list | None = None):
    with _ACTIVITY_LOCK:
        _ACTIVITY_SEQ[0] += 1
        key = _ACTIVITY_SEQ[0]
        entry = {'id': key, 'kind': kind, 'what': what[:200], 'ref': ref[:40] or None,
                 'input': inputs or [], 'output': None, 'started': time.time()}
        _ACTIVITY[key] = entry
    _CURRENT.entry = entry
    try:
        yield entry
    finally:
        _CURRENT.entry = None
        with _ACTIVITY_LOCK:
            _ACTIVITY.pop(key, None)
            entry['seconds'] = round(time.time() - entry['started'], 1)
            entry['finished'] = time.time()
            _RECENT.appendleft(entry)


def record_output(result: dict) -> None:
    """What the model answered, short, for the 排程 page."""
    entry = getattr(_CURRENT, 'entry', None)
    if entry is None or not isinstance(result, dict):
        return
    if isinstance(result.get('stages'), dict):
        entry['stages'] = result['stages']
    if entry['kind'] == 'translate':
        src = {str(i.get('id')): i.get('text') for i in entry.get('input') or []}
        entry['output'] = [{'text': src.get(str(i.get('id')), ''), 'out': str(i.get('text', ''))[:200]}
                           for i in (result.get('items') or [])[:12]]
    elif entry['kind'] == 'score':
        entry['output'] = [{'word': str(x.get('word', '')), 'score': x.get('score')}
                           for x in (result.get('scores') or [])[:30] if isinstance(x, dict)]
    elif entry['kind'] == 'tag':
        entry['output'] = [{'word': str(x.get('word', '')), 'cefr': x.get('cefr') or x.get('level'),
                            'pos': x.get('pos'), 'point': x.get('point'), 'box': x.get('box')}
                           for x in (result.get('candidates') or [])[:40] if isinstance(x, dict)]


def activity_snapshot() -> dict:
    now = time.time()
    with _ACTIVITY_LOCK:
        rows = [dict(r, seconds=round(now - r['started'], 1)) for r in _ACTIVITY.values()]
        recent = [dict(r) for r in list(_RECENT)[:20]]
    slots = None
    if BACKEND == 'llamacpp':
        try:
            with urllib.request.urlopen(f'{LLAMACPP_URL}/slots', timeout=2) as resp:
                got = json.loads(resp.read())
            slots = {'total': len(got), 'busy': sum(1 for x in got if x.get('is_processing'))}
        except (urllib.error.URLError, OSError, ValueError):
            slots = {'total': None, 'busy': None, 'error': '模型伺服器沒有回應'}
    return {'backend': BACKEND,
            'parallel': INFERENCE_PARALLEL, 'slots': slots,
            'requests': sorted(rows, key=lambda r: r['started']), 'recent': recent}


# llama-server's json_schema grammar lets the model pretty-print (one number
# per line): a CEFR label cost ~100 output tokens and replies were cut at the
# limit. The same JSON with no whitespace costs ~55-60 (A/B 2026-10-14).
COMPACT_JSON = os.environ.get('TAGGER_COMPACT_JSON', '1').strip().lower() in {
    '1', 'true', 'yes', 'on'}
_GBNF_BASE = (
    'string ::= "\\"" ( [^"\\\\\\x7F\\x00-\\x1F] | "\\\\" (["\\\\/bfnrt] | "u" [0-9a-fA-F]{4}) )* "\\""\n'
    'integer ::= "-"? [0-9]{1,7}\n'
    'number ::= "-"? [0-9]{1,7} ("." [0-9]{1,7})?\n')


def compact_grammar(schema: dict) -> str | None:
    """A GBNF grammar for ``schema`` that allows no whitespace in the JSON, or
    None for anything outside the subset these replies use (objects whose
    properties are all required, non-empty arrays, enums, strings, numbers,
    booleans)."""
    rules: list[str] = []

    def expr(node: dict, name: str) -> str | None:
        if 'enum' in node:
            return '(' + ' | '.join(json.dumps(json.dumps(v)) for v in node['enum']) + ')'
        kind = node.get('type')
        if kind in ('string', 'integer', 'number'):
            return kind
        if kind == 'boolean':
            return '("true" | "false")'
        if kind == 'array':
            item = expr(node.get('items') or {}, name + '-item')
            return item and f'("[" ({item} ("," {item})*)? "]")'
        if kind == 'object':
            props = node.get('properties') or {}
            if set(node.get('required', [])) != set(props):
                return None
            parts = []
            for i, (key, value) in enumerate(props.items()):
                part = expr(value, f'{name}-{re.sub(r"[^a-zA-Z0-9]", "-", key)}')
                if part is None:
                    return None
                parts.append(json.dumps(('{' if i == 0 else ',') + json.dumps(key) + ':') + ' ' + part)
            rules.append(f'{name} ::= ' + (' '.join(parts) + ' "}"' if parts else '"{}"'))
            return name
        return None

    top = expr(schema, 'reply')
    return top and f'root ::= {top}\n' + '\n'.join(rules) + '\n' + _GBNF_BASE


def loads_salvaging(text: str):
    """The model's JSON, or - when the reply was cut off at the output token
    limit - everything up to the last complete object in a list, closed
    properly. A cut-off reply used to fail the whole photo; its first
    complete candidates are still good."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    stack, in_str, esc, best = [], False, False, None
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in '[{':
            stack.append(ch)
        elif ch in ']}':
            if not stack:
                break
            stack.pop()
            if ch == '}' and stack and stack[-1] == '[':
                best = (i, list(stack))
    if best is None:
        raise json.JSONDecodeError('model reply cut off before any complete item', text, len(text))
    end, open_ = best
    return json.loads(text[:end + 1] + ''.join(']' if c == '[' else '}' for c in reversed(open_)))


def zipf_level(zipf: float) -> str:
    """Frequency estimate of a word's CEFR level (same cut-offs as the backend's
    frequency_profile), used only to steer top-up calls toward the asked level."""
    for floor, lv in ((5.0, 'A1'), (4.5, 'A2'), (4.0, 'B1'), (3.5, 'B2'), (3.0, 'C1')):
        if zipf >= floor:
            return lv
    return 'C2'


CEFR_LIST_FILE = os.path.join(ROOT, 'app', 'assets', 'cefr_en.json')
OXFORD_EXTRA_FILE = os.path.join(ROOT, 'lexicon', 'backend', 'app', 'oxford5000_extra.json')
_CEFR_LIST: dict[str, dict[str, str]] | None = None


def cefr_list_words() -> dict[str, dict[str, str]]:
    """CEFR-J + Oxford 5000 additions, word -> {pos: level} (same data as the backend's
    adapters/local.cefr_list, so the tagger and the App agree on a listed word)."""
    global _CEFR_LIST
    if _CEFR_LIST is None:
        words: dict[str, dict[str, str]] = {}
        try:
            with open(CEFR_LIST_FILE, encoding='utf-8') as f:
                words = {w: dict(v[1]) for w, v in json.load(f)['words'].items()}
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            pass
        try:
            with open(OXFORD_EXTRA_FILE, encoding='utf-8') as f:
                for w, pos in json.load(f)['words'].items():
                    words.setdefault(w, dict(pos))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        _CEFR_LIST = words
    return _CEFR_LIST


def _wordfreq_zipf(word: str) -> float | None:
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        return None
    return round(zipf_frequency(word, 'en'), 2)


def word_cefr(word: str, zipf: float | None) -> tuple[str | None, str | None]:
    """A label's CEFR band and where it came from: 'list' when CEFR-J/Oxford lists it
    (the easiest band over its parts of speech), else 'estimate' from its frequency
    (zipf). A phrase counts as its hardest word. (None, None) when neither is known."""
    w = _SPACE.sub(' ', str(word or '').strip().lower())
    hit = cefr_list_words().get(w)
    if hit:
        return min(hit.values(), key=LEVELS.index), 'list'
    parts = w.split()
    if len(parts) > 1:
        found = [word_cefr(p, None) for p in parts]
        if any(level for level, _ in found):
            return (max((lv for lv, _ in found if lv), key=LEVELS.index),
                    'list' if all(src == 'list' for _, src in found if src) else 'estimate')
    if zipf is None:
        # Card #685: cached labels and labels from a request without a Lexicon carry no
        # zipf; look it up here, else the level filter would keep every unlisted word.
        zipf = _wordfreq_zipf(w)
    if zipf is None:
        return None, None
    return zipf_level(zipf), 'estimate'


def attach_cefr(items: list[dict]) -> list[dict]:
    """Card #657: every English candidate carries its band (`cefr`) and `cefrSource`,
    so the App does not fall back to a guessed B1 when its own database misses a word."""
    for item in items:
        if item.get('cefr'):
            continue
        item['cefr'], item['cefrSource'] = word_cefr(item['word'], item.get('zipf'))
    return items


def filter_level(items: list[dict], level: str) -> list[dict]:
    """Keep labels no easier than one band below `level`. Card #657: no fill-up with
    easier words any more (the old fill-to-3 let B2 labels through for a C2 learner).
    A label whose band is unknown is kept."""
    floor = LEVELS.index(_shift(level, -1))
    return [i for i in items if not i.get('cefr') or LEVELS.index(i['cefr']) >= floor]


def finish_candidates(items: list[dict], level: str, lang: str,
                      focus: str | None) -> list[dict]:
    """The per-request part of a level-based answer, applied to cached raw labels too:
    CEFR band, the level filter (all focus modes but easier), and for focus=harder
    the rarest six first."""
    if lang != 'en':
        return items
    attach_cefr(items)
    if level not in LEVELS or focus == 'easier':
        return items
    items = filter_level(items, level)
    if focus == 'harder':
        items = sorted(items, key=lambda i: (
            -LEVELS.index(i['cefr']) if i.get('cefr') else 0,
            i.get('zipf') if i.get('zipf') is not None else 9.0))[:6]
    return items


class Lexicon:
    """Optional local word data: frequency, IPA and dictionary headwords."""

    def __init__(self, cmudict_path: str = CMUDICT):
        try:
            from wordfreq import zipf_frequency
            self._zipf = zipf_frequency
        except ImportError:
            self._zipf = None
        self._ipa: dict[str, str] = {}
        self._dictionary = None
        kaikki = os.environ.get(
            'TAGGER_KAIKKI_INDEX',
            os.path.join(ROOT, 'lexicon', 'raw-data', 'kaikki-index.sqlite3'))
        if os.path.isfile(kaikki):
            try:
                import sqlite3
                self._dictionary = sqlite3.connect(
                    f'file:{os.path.abspath(kaikki).replace(os.sep, "/")}?mode=ro',
                    uri=True, check_same_thread=False)
                self._dictionary.execute('PRAGMA query_only=ON')
            except (OSError, sqlite3.Error):
                self._dictionary = None
        if os.path.exists(cmudict_path):
            sys.path.insert(0, os.path.join(ROOT, 'pipeline'))
            try:
                from ipa import arpabet_to_ipa
            except ImportError:
                arpabet_to_ipa = None
            if arpabet_to_ipa:
                with open(cmudict_path, encoding='utf-8') as f:
                    for line in f:
                        parts = line.split('#')[0].split(None, 1)
                        if len(parts) == 2 and '(' not in parts[0]:
                            w = parts[0].lower()
                            if w not in self._ipa:
                                ipa = arpabet_to_ipa(parts[1].strip())
                                if ipa:
                                    self._ipa[w] = ipa

    def ipa(self, word: str) -> str | None:
        if word in self._ipa:
            return self._ipa[word]
        parts = [self._ipa.get(p) for p in word.split()]
        if len(parts) > 1 and all(parts):
            return '/' + ' '.join(p.strip('/') for p in parts) + '/'
        return None

    _OTHER_LANGS = ('fr', 'es', 'de', 'it', 'pt')

    def is_foreign(self, word: str) -> bool:
        """A single word that is rare in English but common in another
        language - calendrier, fenêtre, fenster - not an English loanword
        (croissant, espresso, tortilla stay). Spec: 第一階段只產生英文詞條."""
        if self._zipf is None or ' ' in word:
            return False
        en = self._zipf(word, 'en')
        other = max(self._zipf(word, lang) for lang in self._OTHER_LANGS)
        return en < 2.0 and other >= en + 2.0

    def is_lexical_phrase(self, phrase: str) -> bool:
        """Whether a multiword label is an attested dictionary headword.

        If the optional complete Kaikki index is unavailable, preserve the
        old permissive behaviour instead of discarding valid labels.
        """
        if ' ' not in phrase or self._dictionary is None:
            return True
        try:
            row = self._dictionary.execute(
                "SELECT 1 FROM entries WHERE language = 'en' AND normalized = ? LIMIT 1",
                (phrase.strip().lower(),)).fetchone()
            return row is not None
        except Exception:
            return True

    def describe(self, word: str, lang: str = 'en') -> dict:
        out = {}
        if self._zipf is not None:
            out['zipf'] = round(self._zipf(word, lang.split('-')[0]), 2)
        if lang == 'en' and (ipa := self.ipa(word)):
            out['ipa'] = ipa
        return out


def prepare_image(image: bytes) -> tuple[bytes, dict]:
    started = time.perf_counter()
    try:
        return _prepare_image(image)
    finally:
        stage_add('prepMs', round((time.perf_counter() - started) * 1000))


def _prepare_image(image: bytes) -> tuple[bytes, dict]:
    """Normalize orientation and cap image size before vision inference.

    Pillow is optional so the service still runs in a minimal environment. The
    original bytes are used if decoding fails.
    """
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(image)) as source:
            picture = ImageOps.exif_transpose(source).convert('RGB')
            original = picture.size
            picture.thumbnail((IMAGE_MAX_EDGE, IMAGE_MAX_EDGE), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            picture.save(output, 'JPEG', quality=IMAGE_JPEG_QUALITY, optimize=True)
            return output.getvalue(), {
                'original': list(original),
                'sent': list(picture.size),
                'bytes': len(output.getvalue()),
            }
    except (ImportError, OSError, ValueError):
        return image, {'original': None, 'sent': None, 'bytes': len(image)}


class UnsafeImage(ValueError):
    """The vision model identified content that must not enter the app."""


class Tagger:
    def __init__(self, ollama_url: str, model: str, lexicon: Lexicon | None = None):
        self.ollama_url = ollama_url.rstrip('/')
        self.model = model
        self.lexicon = lexicon
        self._admission = PrioritySlots(INFERENCE_PARALLEL)
        # Long import translations must not occupy every llama-server slot;
        # keep one available for a learner waiting on a photo.
        self._background_slots = threading.BoundedSemaphore(
            max(1, INFERENCE_PARALLEL - 2))
        self._key_locks: dict[str, list] = {}  # key -> [lock, users]
        self._key_locks_guard = threading.Lock()
        os.makedirs(CACHE_DIR, exist_ok=True)

    @contextlib.contextmanager
    def _inference(self, key: str | None = None):
        """One of the INFERENCE_PARALLEL model slots. Requests with the same
        cache ``key`` wait for each other, so the second reads the first's
        cached reply instead of running the model again."""
        waited = time.perf_counter()
        if key is None:
            with self._admission.slot():
                stage_add('queueMs', round((time.perf_counter() - waited) * 1000))
                yield
            return
        with self._key_locks_guard:
            entry = self._key_locks.setdefault(key, [threading.Lock(), 0])
            entry[1] += 1
        try:
            with entry[0], self._admission.slot():
                stage_add('queueMs', round((time.perf_counter() - waited) * 1000))
                yield
        finally:
            with self._key_locks_guard:
                entry[1] -= 1
                if not entry[1]:
                    self._key_locks.pop(key, None)

    @contextlib.contextmanager
    def _background_inference(self):
        """Lower-concurrency lane for database import translations."""
        waited = time.perf_counter()
        with self._admission.request(background=True), self._background_slots:
            stage_add('queueMs', round((time.perf_counter() - waited) * 1000))
            with self._inference():
                yield

    def backend_url(self) -> str:
        """Where the model actually runs (llama-server or Ollama)."""
        return LLAMACPP_URL if BACKEND == 'llamacpp' else self.ollama_url

    def backend_error(self) -> str | None:
        """None when the model backend answers its health check, else why not."""
        url = (f'{LLAMACPP_URL}/health' if BACKEND == 'llamacpp'
               else f'{self.ollama_url}/api/version')
        try:
            with urllib.request.urlopen(url, timeout=3):
                return None
        except urllib.error.HTTPError as e:  # llama-server answers 503 while loading
            return f'{BACKEND} at {self.backend_url()} answered HTTP {e.code}'
        except (urllib.error.URLError, OSError) as e:
            return (f'{BACKEND} not reachable at {self.backend_url()}: '
                    f'{getattr(e, "reason", e)}')

    def ollama_ok(self) -> bool:
        return self.backend_error() is None

    def _chat(self, prompt: str, schema: dict, image: bytes | None = None,
              temperature: float = 0, max_tokens: int | None = None,
              logprobs: bool = False, compact: bool = False):
        """The model's JSON reply; with logprobs, (reply, per-token logprobs).
        ``compact`` asks llama-server for JSON without whitespace."""
        started = time.perf_counter()
        try:
            return self._chat_backend(prompt, schema, image, temperature, max_tokens,
                                      logprobs, compact)
        finally:
            stage_add('modelMs', round((time.perf_counter() - started) * 1000))
            stage_add('modelCalls', 1)

    def _chat_backend(self, prompt, schema, image, temperature, max_tokens, logprobs, compact):
        if BACKEND == 'llamacpp':
            return self._chat_llamacpp(prompt, schema, image, temperature, max_tokens, logprobs,
                                       compact)
        message = {'role': 'user', 'content': prompt}
        if image is not None:
            message['images'] = [base64.b64encode(image).decode()]
        body = {
            'model': self.model,
            'messages': [message],
            'format': schema,
            'stream': False,
            # Qwen3.5 enables a hidden reasoning channel by default. It is not
            # useful for these tightly constrained extraction/translation calls
            # and can consume the output budget before the JSON is complete.
            'think': False,
            'keep_alive': KEEP_ALIVE,
            'options': {
                'temperature': temperature,
                'num_ctx': MODEL_CONTEXT,
                'num_predict': max_tokens or MODEL_MAX_TOKENS,
            },
        }
        if logprobs:
            body['logprobs'], body['top_logprobs'] = True, 5
        req = urllib.request.Request(
            f'{self.ollama_url}/api/chat',
            data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            reply = json.loads(resp.read())
        content = loads_salvaging(reply['message']['content'])
        return (content, reply.get('logprobs') or []) if logprobs else content

    def _chat_llamacpp(self, prompt, schema, image, temperature, max_tokens, logprobs,
                       compact=False):
        """The same request to llama-server's OpenAI-compatible chat API. The
        context size is the server's per-slot -c / -np; Ollama's own sampling
        defaults for the model are sent with every request."""
        content = [{'type': 'text', 'text': prompt}]
        if image is not None:
            content.insert(0, {'type': 'image_url', 'image_url': {
                'url': 'data:image/jpeg;base64,' + base64.b64encode(image).decode()}})
        body = {
            'messages': [{'role': 'user', 'content': content}],
            'temperature': temperature,
            'max_tokens': max_tokens or MODEL_MAX_TOKENS,
            'chat_template_kwargs': {'enable_thinking': False},  # as 'think': False
            **LLAMACPP_SAMPLING,
        }
        grammar = compact_grammar(schema) if compact else None
        if grammar:
            body['grammar'] = grammar
        else:
            body['response_format'] = {'type': 'json_schema',
                                       'json_schema': {'name': 'reply', 'schema': schema}}
        if logprobs:
            body['logprobs'], body['top_logprobs'] = True, 5
        stream_cefr = CEFR_REPEAT_GUARD and schema is CEFR_CANDIDATE_SCHEMA and not logprobs
        if stream_cefr:
            body['stream'] = True
        req = urllib.request.Request(
            f'{LLAMACPP_URL}/v1/chat/completions',
            data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            if stream_cefr:
                return loads_salvaging(read_cefr_stream(resp, on_timings=note_llama_timings))
            reply = json.loads(resp.read())
        note_llama_timings(reply.get('timings'))
        choice = reply['choices'][0]
        parsed = loads_salvaging(choice['message']['content'] or '')
        if not logprobs:
            return parsed
        return parsed, (choice.get('logprobs') or {}).get('content') or []

    def score(self, image: bytes, labels: list[dict], lang: str = 'en') -> list[dict]:
        """Each label's recognition score: the model looks at the photo again
        and answers, label by label, whether it is shown; the score is its
        probability of answering yes (0-1), read from the token logprobs."""
        labels = [{'word': str(l.get('word', '')).strip().lower(), 'pos': l.get('pos')}
                  for l in labels if str(l.get('word', '')).strip()][:SCORE_MAX_LABELS]
        if not labels:
            return []
        key_data = json.dumps({
            'image': hashlib.sha256(image).hexdigest(), 'model': self.model,
            'prompt': SCORE_PROMPT_VERSION, 'lang': lang, 'prep': IMAGE_PREP_VERSION,
            'labels': [[l['word'], l['pos']] for l in labels]}, sort_keys=True).encode()
        cache_file = os.path.join(CACHE_DIR, 'score-' + hashlib.sha256(key_data).hexdigest() + '.json')
        try:
            with open(cache_file, encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, OSError, ValueError):
            pass
        with self._inference(cache_file):
            try:
                with open(cache_file, encoding='utf-8') as f:
                    return json.load(f)
            except (FileNotFoundError, OSError, ValueError):
                pass
            prepared, _ = prepare_image(image)
            content, logprobs = self._chat(build_score_prompt(labels, lang), SCORE_SCHEMA,
                                           prepared, max_tokens=40 + 24 * len(labels),
                                           logprobs=True)
        checks = content.get('checks') or []
        probs = boolean_scores(logprobs)
        by_word = {}
        for i, c in enumerate(checks):
            if i < len(probs):
                by_word.setdefault(str(c.get('word', '')).strip().lower(), probs[i])
        out = []
        for i, l in enumerate(labels):
            p = by_word.get(l['word'])
            if p is None and i < len(checks) and i < len(probs) and len(checks) == len(labels):
                p = probs[i]  # same order, the word copied a little differently
            out.append({'word': l['word'], 'score': None if p is None else round(p, 3)})
        temporary = cache_file + f'.{os.getpid()}.tmp'
        try:
            with open(temporary, 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
            os.replace(temporary, cache_file)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        return out

    def candidates(self, image: bytes, level: str, lang: str = 'en', native: str = 'zh-TW',
                   focus: str | None = None, exclude: list[str] | None = None) -> list[dict]:
        # Native language does not alter recognition; level steers the prompt (card #625),
        # so it is part of the cache key.
        key_data = json.dumps({
            'image': hashlib.sha256(image).hexdigest(),
            'model': self.model,
            'prompt': PROMPT_VERSION,
            'output_policy': 'dictionary-level-visible-v1',
            'lang': lang,
            'level': level if level in LEVELS else None,
            'focus': focus,
            'exclude': sorted(w.strip().lower() for w in (exclude or []) if w.strip()),
            'prep': IMAGE_PREP_VERSION},
            sort_keys=True).encode()
        cache_file = os.path.join(CACHE_DIR, hashlib.sha256(key_data).hexdigest() + '.json')
        # The cache holds the model's labels; the level filter and CEFR bands are applied
        # on every return (card #657), so a rule change never serves a stale filtered list.
        try:
            with open(cache_file, encoding='utf-8') as f:
                cached = json.load(f)
            if isinstance(cached, list):
                return finish_candidates(cached, level, lang, focus)
        except (FileNotFoundError, OSError, ValueError, TypeError):
            pass

        # One inference at a time keeps the 8 GB GPU from allocating parallel KV
        # caches. Check the disk cache again after waiting for another request.
        with self._inference(cache_file):
            try:
                with open(cache_file, encoding='utf-8') as f:
                    cached = json.load(f)
                if isinstance(cached, list):
                    return finish_candidates(cached, level, lang, focus)
            except (FileNotFoundError, OSError, ValueError, TypeError):
                pass
            prepared, _ = prepare_image(image)
            # Card #657: compact JSON (no pretty-printing whitespace) cuts the decode time,
            # as it did for the CEFR path (A/B 2026-10-14).
            content = self._chat(build_prompt(level, lang, native, focus, exclude),
                                 CANDIDATE_SCHEMA, prepared, compact=COMPACT_JSON)
            if content.get('safe') is not True:
                raise UnsafeImage('explicit adult content')
            items = to_candidates(content.get('candidates', []), self.lexicon, exclude, lang)
            temporary = cache_file + f'.{os.getpid()}.tmp'
            try:
                with open(temporary, 'w', encoding='utf-8') as f:
                    json.dump(items, f, ensure_ascii=False, separators=(',', ':'))
                os.replace(temporary, cache_file)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
            return finish_candidates(items, level, lang, focus)

    def candidates_cefr(self, image: bytes, lang: str = 'en',
                        exclude: list[str] | None = None,
                        per_level: int = CEFR_TAGS_PER_LEVEL,
                        target_levels: list[str] | None = None,
                        existing_counts: dict[str, int] | None = None,
                        internal_topup: bool = False) -> list[dict]:
        """Return visible labels; the trusted backend assigns CEFR and requests retries."""
        target_levels = list(dict.fromkeys(
            level.upper() for level in (target_levels or []) if level.upper() in LEVELS))
        existing_counts = {level: min(max(int((existing_counts or {}).get(level, 0)), 0),
                                      per_level) for level in LEVELS}
        key_data = json.dumps({
            'image': hashlib.sha256(image).hexdigest(),
            'model': self.model,
            'prompt': CEFR_PROMPT_VERSION,
            'output_policy': 'dictionary-level-visible-v1',
            'lang': lang,
            'per_level': per_level,
            'target_levels': target_levels,
            'existing_counts': existing_counts,
            'internal_topup': internal_topup,
            'exclude': sorted(w.strip().lower() for w in (exclude or []) if w.strip()),
            'prep': IMAGE_PREP_VERSION},
            sort_keys=True).encode()
        cache_file = os.path.join(CACHE_DIR, hashlib.sha256(key_data).hexdigest() + '.json')
        try:
            with open(cache_file, encoding='utf-8') as f:
                cached = json.load(f)
            if isinstance(cached, list):
                return cached
        except (FileNotFoundError, OSError, ValueError, TypeError):
            pass

        with self._inference(cache_file):
            try:
                with open(cache_file, encoding='utf-8') as f:
                    cached = json.load(f)
                if isinstance(cached, list):
                    return cached
            except (FileNotFoundError, OSError, ValueError, TypeError):
                pass
            prepared, _ = prepare_image(image)
            prompt = (build_cefr_topup_prompt(
                lang, target_levels, exclude or [], per_level,
                existing_counts) if target_levels
                else build_cefr_prompt(lang, exclude, per_level))
            content = self._chat(prompt,
                                 CEFR_CANDIDATE_SCHEMA, prepared,
                                 max_tokens=CEFR_MAX_TOKENS, compact=COMPACT_JSON)
            if content.get('safe') is not True:
                raise UnsafeImage('explicit adult content')
            items = to_candidates(content.get('candidates', []), self.lexicon, exclude, lang)
            # Hard-cap A1/A2 so a noun-heavy first pass cannot fill TAGS_MAX alone.
            items = cap_cefr_beginner_bands(items)
            # Do not cache empty CEFR-band replies: a truncated or weak answer
            # would permanently block enrich retries for that photo.
            if items:
                temporary = cache_file + f'.{os.getpid()}.tmp'
                try:
                    with open(temporary, 'w', encoding='utf-8') as f:
                        json.dump(items, f, ensure_ascii=False, separators=(',', ':'))
                    os.replace(temporary, cache_file)
                finally:
                    if os.path.exists(temporary):
                        os.remove(temporary)
            return items

    def enrich(self, req: dict) -> dict:
        word = str(req.get('word', '')).strip().lower()
        lang = req.get('lang') if req.get('lang') in LANGS else 'en'
        native = req.get('native') if req.get('native') in LANGS else 'zh-TW'
        pos = str(req.get('pos') or '').strip()
        count = min(max(int(req.get('examples') or 0), 0), 10)
        translate = [str(t) for t in (req.get('translate') or [])][:10]
        lang_name, native_name = LANGS[lang], LANGS[native]
        known = f' (meaning: {req["meaning"]})' if req.get('meaning') else ''
        prompt = '\n'.join([
            f'You write dictionary entries for learners of {lang_name} whose native language '
            f'is {native_name}.',
            f'Word: "{word}"' + (f', part of speech: {pos}' if pos else '') + known + '.',
            f'- meaning: a short {native_name} translation of this sense',
            f'- definition: one simple sentence in {native_name} explaining it',
            '- ipa: its IPA pronunciation between slashes'
            + (', US English' if lang == 'en' else ''),
            f'- examples: exactly {count} natural, everyday {lang_name} sentences using the '
            f'word in this sense (5-15 words each), each with its {native_name} translation',
            f'- translations: translate each of these {lang_name} sentences into '
            f'{native_name}, in order: ' + json.dumps(translate, ensure_ascii=False),
            'Reply with JSON only.',
            NATIVE_RULE[native].replace('meaning', 'meaning、definition 與 translation')
            if native == 'zh-TW' else '',
        ])
        content = self._chat(prompt, ENRICH_SCHEMA, temperature=0.3)
        examples = [
            {'text': str(e.get('text', '')).strip(), 'translation': str(e.get('translation', '')).strip()}
            for e in content.get('examples', []) if str(e.get('text', '')).strip()
        ][:max(count, 0)]
        ipa = self.lexicon.ipa(word) if self.lexicon is not None and lang == 'en' else None
        model_ipa = str(content.get('ipa', '')).strip()
        if model_ipa and not model_ipa.startswith('/'):
            model_ipa = f'/{model_ipa.strip("/[]")}/'
        return {
            'word': word,
            'meaning': str(content.get('meaning', '')).strip(),
            'definition': str(content.get('definition', '')).strip(),
            'ipa': ipa or model_ipa or None,
            'ipaSource': 'cmudict' if ipa else ('ai' if model_ipa else None),
            'examples': examples,
            'translations': [str(t).strip() for t in content.get('translations', [])][:len(translate)],
        }


TRANSLATE_PROMPT_VERSION = 'translate-v5'
TRANSLATE_SCHEMA = {
    'type': 'object',
    'properties': {'items': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'id': {'type': 'string'}, 'text': {'type': 'string'}},
        'required': ['id', 'text']}}},
    'required': ['items'],
}
TRANSLATE_EXAMPLE = {
    'zh-TW': ' (e.g. {"id": "x", "text": "蘋果"} for the English word apple).',
    'fr': ' (e.g. {"id": "x", "text": "pomme"} for the English word apple).',
    'en': ' (e.g. {"id": "x", "text": "apple"} for the French word pomme).',
}
TRANSLATE_KIND = {
    'word': 'Each item is a single {lang} word; give its most common short {native} '
            'meaning (1-4 words), matching the context when one is given.',
    'gloss': 'Each item is a {lang} dictionary definition of one word sense; give a short '
             '{native} translation of the word in that sense (1-6 words), not of the '
             'definition sentence.',
    'sentence': 'Each item is a {lang} sentence; translate it naturally into {native}.',
    'etymology': 'Each item is an English etymology note; rewrite it as one or two plain '
                 '{native} sentences a learner can read. Keep word forms as written.',
    'define': 'Each item is a {lang} word; write one short, simple {lang} definition of '
              'its main sense for learners.',
    'part': 'Each item is one part of a {lang} word (a prefix, root or suffix; the context says '
            'which word and what it means); give its meaning in {native} in 1-6 words, the way '
            'word-root textbooks do (e.g. ex- 向外, -ness 性質、狀態).',
    # Written in the learning language: the dictionaries left these CEFR
    # levels short; the admin marks every result as AI.
    'example': 'Each item is a {lang} word with a CEFR level and its meaning. Write one natural '
               '{lang} example sentence that uses the word (or a form of it) in that meaning, '
               'pitched at that level, never longer than 20 words: A1 5-8 very common words; '
               'A2 8-12 words; B1 12-16 words; B2 16-20 words; C1 and C2 also at most 20 words, '
               'made advanced by their vocabulary (C1: less common words; C2: rare, formal or '
               'literary words). Items with the same level must differ.',
    'synonyms': 'Each item is a {lang} word with its meaning and the CEFR levels still needed. '
                'List 15 different {lang} synonyms or near-synonyms of the word in that meaning, '
                'comma-separated, spread over those levels: everyday words for A1-A2, and rarer, '
                'formal or literary words for C1-C2. Real dictionary words only, never the word '
                'itself or its forms.',
    'related': 'Each item is a {lang} word with its meaning and the CEFR levels still needed. '
               'List 15 different {lang} words closely related to the word in that meaning (same '
               'topic, parts, uses, kinds), comma-separated, spread over those levels: everyday '
               'words for A1-A2, and rarer, technical or literary words for C1-C2. Real '
               'dictionary words only, never the word itself or its forms.',
    'pick': 'Each item is an English sentence, the target word, and lettered meanings of that '
            'word (A, B, C...). Choose the letter of the meaning the word has in that sentence '
            '(same part of speech and sense). If none fits, answer X. "text" is only the letter.',
    'bundle': 'Each item has its own "task". Apply that task independently: gloss means return '
              'a short {native} translation of the defined word; sentence means translate the '
              'sentence naturally into {native}; word means return the short {native} meaning '
              'matching its context; etymology means rewrite the note as one or two plain '
              '{native} sentences; part means give the word-part meaning in {native} in 1-6 '
              'words. Never merge, omit, or reorder items.',
}
# Kinds whose results are in the learning language, not the native one.
TARGET_KINDS = {'define', 'example', 'synonyms', 'related'}
TARGET_EXAMPLE = {
    'example': ' (e.g. {"id": "A1:0", "text": "I drink coffee every morning."}).',
    'synonyms': ' (e.g. {"id": "w", "text": "mug, teacup, beaker, goblet, chalice"}).',
    'related': ' (e.g. {"id": "w", "text": "saucer, tea, kitchen, porcelain, handle"}).',
}
MORPH_SCHEMA = {
    'type': 'object',
    'properties': {'items': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'id': {'type': 'string'}, 'parts': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'part': {'type': 'string'},
                           'type': {'type': 'string', 'enum': ['prefix', 'root', 'suffix']},
                           'meaning': {'type': 'string'}},
            'required': ['part', 'type', 'meaning']}}},
        'required': ['id', 'parts']}}},
    'required': ['items'],
}
MORPH_PROMPT = (
    'Split each {lang} word into its meaningful parts, in order: prefixes, root(s), suffixes '
    '(e.g. exterior: ex / ter / ior; unhappiness: un / happy / ness; transportation: trans / '
    'port / ation). Write each part with the letters it has in the word, so the parts spell the '
    'word; mark each as prefix, root or suffix and give a short English meaning. A word that '
    'cannot be split is one root. The context may give its etymology.')


def translate(tagger: 'Tagger', req: dict) -> dict:
    lang = req.get('lang') if req.get('lang') in LANGS else 'en'
    native = req.get('native') if req.get('native') in LANGS else 'zh-TW'
    kind = req.get('kind') if req.get('kind') in TRANSLATE_KIND or req.get('kind') == 'morphemes' \
        else 'word'
    item_limit = 80 if kind == 'bundle' else 40
    items = [{'id': str(i.get('id', n)), 'text': str(i.get('text', ''))[:600],
              **({'context': str(i['context'])[:200]} if i.get('context') else {}),
              **({'task': str(i['task'])[:20]} if kind == 'bundle' and i.get('task') else {})}
             for n, i in enumerate(req.get('items') or [])
             if str(i.get('text', '')).strip()][:item_limit]
    if not items:
        return {'items': [], 'promptVersion': TRANSLATE_PROMPT_VERSION}
    if kind == 'morphemes':
        prompt = '\n'.join([MORPH_PROMPT.format(lang=LANGS[lang]),
                            'Return one result per item, with the same id, in JSON.',
                            'Items: ' + json.dumps(items, ensure_ascii=False)])
        content = tagger._chat(prompt, MORPH_SCHEMA, temperature=0,
                               max_tokens=TRANSLATE_MAX_TOKENS)
        wanted = {i['id'] for i in items}
        out = [{'id': str(r.get('id')), 'parts': [
            {'part': str(x.get('part', '')).strip(), 'type': x.get('type', 'root'),
             'meaning': str(x.get('meaning', '')).strip()} for x in r.get('parts', [])
            if str(x.get('part', '')).strip()]}
            for r in content.get('items', []) if str(r.get('id')) in wanted]
        return {'items': out, 'promptVersion': TRANSLATE_PROMPT_VERSION, 'kind': kind}
    in_target = kind in TARGET_KINDS
    out_lang = LANGS[lang] if in_target else LANGS[native]
    def ask(batch, *, retry=False):
        prompt = '\n'.join([
            TRANSLATE_KIND[kind].format(lang=LANGS[lang], native=LANGS[native]),
            # Without this the small model echoes the English input back.
            f'Return one result per item, with the same id, in JSON. "text" is the {out_lang} '
            'result, never a copy of the input'
            + (TARGET_EXAMPLE.get(kind, '.') if in_target else TRANSLATE_EXAMPLE.get(native, '.')),
            NATIVE_RULE[native].replace('「meaning」', '所有輸出')
            if native == 'zh-TW' and not in_target else '',
            ('The previous attempt was invalid because it copied the source language. '
             f'Write the answer only in {out_lang}.' if retry else ''),
            'Items: ' + json.dumps(batch, ensure_ascii=False),
        ])
        content = tagger._chat(prompt, TRANSLATE_SCHEMA, temperature=0,
                               max_tokens=TRANSLATE_MAX_TOKENS)
        wanted = {i['id'] for i in batch}
        return {str(r.get('id')): str(r.get('text', '')).strip()
                for r in content.get('items', []) if str(r.get('id')) in wanted
                and str(r.get('text', '')).strip()}

    def valid(item, text):
        if not text or text.casefold() == item['text'].strip().casefold():
            return False
        if not in_target and native == 'zh-TW' and not re.search(r'[\u3400-\u9fff]', text):
            return False
        return True

    got = ask(items)
    invalid = [item for item in items if not valid(item, got.get(item['id'], ''))]
    # qwen3.5 occasionally echoes an entire sentence batch in English.  A
    # focused one-item retry is much more reliable and only runs for failures.
    for item in invalid:
        retry = ask([item], retry=True)
        text = retry.get(item['id'], '')
        if valid(item, text):
            got[item['id']] = text
        else:
            got.pop(item['id'], None)
    out = [{'id': item['id'], 'text': got[item['id']]}
           for item in items if item['id'] in got]
    return {'items': out, 'promptVersion': TRANSLATE_PROMPT_VERSION, 'kind': kind}


def extract_image(content_type: str, body: bytes) -> bytes | None:
    """The image from a raw body, or from the "image" part of a multipart body."""
    if content_type.startswith('multipart/form-data'):
        msg = BytesParser(policy=email_policy).parsebytes(
            f'Content-Type: {content_type}\r\n\r\n'.encode() + body)
        for part in msg.iter_parts():
            if part.get_param('name', header='content-disposition') == 'image':
                return part.get_payload(decode=True)
        return None
    return body or None


def _param(query: dict, name: str, allowed, default):
    value = (query.get(name) or [default])[0]
    return value if value in allowed else default


def make_handler(tagger: Tagger, api_key: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'EnglishCardTagger/2.0'

        def _cors(self):
            self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin') or '*')
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'X-API-Key, Content-Type')
            self.send_header('Access-Control-Allow-Private-Network', 'true')

        def _json(self, status: int, payload: dict):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self._cors()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):  # CORS preflight from the web app
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if urlparse(self.path).path == '/activity':
                if not secrets.compare_digest(self.headers.get('X-API-Key', ''), api_key):
                    self._json(401, {'error': 'missing or wrong X-API-Key'})
                    return
                self._json(200, dict(activity_snapshot(), model=tagger.model))
                return
            if urlparse(self.path).path == '/health':
                sent = self.headers.get('X-API-Key')
                key_ok = None if sent is None else secrets.compare_digest(sent, api_key)
                # ok follows the model backend (card #451): the tagger alone
                # answering is not enough — every model call 502s without it.
                backend_error = tagger.backend_error()
                self._json(200, {'ok': backend_error is None, 'model': tagger.model,
                                 'ollama': backend_error is None, 'keyOk': key_ok,
                                 'backend': BACKEND, 'backendUrl': tagger.backend_url(),
                                 'backendError': backend_error,
                                 'prep': IMAGE_PREP_VERSION,
                                 'cefrNumPredict': CEFR_MAX_TOKENS,
                                 'keepAlive': KEEP_ALIVE,
                                 'paused': is_qwen_paused(),
                                 'config': tagger_config.effective_config()})
            else:
                self._json(404, {'error': 'not found'})

        def _body(self) -> bytes | None:
            length = int(self.headers.get('Content-Length') or 0)
            if length <= 0 or length > MAX_BODY:
                self._json(413 if length > MAX_BODY else 400, {'error': 'send a body up to 20 MB'})
                return None
            return self.rfile.read(length)

        def _model_call(self, fn):
            started = time.time()
            stages = stages_reset()
            try:
                result = fn()
            except UnsafeImage:
                self._json(451, {'error': 'explicit adult content is not allowed',
                                 'code': 'unsafe_image'})
                return
            except urllib.error.URLError as e:
                where = ('llama-server' if BACKEND == 'llamacpp' else 'Ollama')
                self._json(502, {'error': f'{where} not reachable at '
                                          f'{tagger.backend_url()}: {e.reason}',
                                 'code': 'backend_unreachable'})
                return
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
                # The service is up; this photo's reply was unusable. 422,
                # not 502, so the app fails this photo and tags the next one.
                self._json(422, {'error': f'unexpected model reply: {e}'})
                return
            stages['cacheHit'] = not stages['modelCalls']
            result.update({'model': tagger.model, 'elapsedMs': int((time.time() - started) * 1000),
                           'stages': dict(stages)})
            record_output(result)
            self._json(200, result)

        def do_POST(self):
            url = urlparse(self.path)
            if url.path not in ('/tag', '/enrich', '/translate', '/score'):
                self._json(404, {'error': 'not found'})
                return
            if not secrets.compare_digest(self.headers.get('X-API-Key', ''), api_key):
                self._json(401, {'error': 'missing or wrong X-API-Key'})
                return
            # New inference only: in-flight requests (already past this check) finish.
            # The board pause / Qwen schedule only holds back batch work: a learner's own
            # photo from the App is never refused (owner 10/21).
            if is_qwen_paused() and is_background(url.path, self.headers):
                self._json(503, {'error': 'Qwen 已暫停', 'code': 'qwen_paused'})
                return
            body = self._body()
            if body is None:
                return
            kind = url.path.strip('/')
            what = unquote(self.headers.get('X-Activity', ''))
            ref = unquote(self.headers.get('X-Activity-Ref', ''))
            inputs: list = []
            if kind == 'translate':
                try:
                    req = json.loads(body.decode('utf-8') or '{}')
                    inputs = [{'id': str(i.get('id', n)), 'text': str(i.get('text', ''))[:200]
                               + (f"（{str(i.get('context') or i.get('task'))[:80]}）"
                                  if i.get('context') or i.get('task') else '')}
                              for n, i in enumerate(req.get('items') or []) if isinstance(i, dict)][:40]
                    if not what:
                        what = f"{req.get('kind', '')}: " + '、'.join(i['text'][:30] for i in inputs[:3])
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                    pass
            elif kind == 'score':
                try:
                    labels = json.loads((parse_qs(url.query).get('labels') or ['[]'])[0])
                    inputs = [{'word': str(x.get('word', ''))} for x in labels if isinstance(x, dict)][:30]
                except (ValueError, AttributeError):
                    pass
            with activity(kind, what, ref, inputs), tagger._admission.request(
                    background=is_background(url.path, self.headers)):
                self._post(url, body)

        def _post(self, url, body):
            if url.path == '/enrich':
                self._json(410, {
                    'error': 'AI word enrichment is disabled; use the downloaded word database',
                })
                return
            if url.path == '/translate':
                # The word-database admin's AI fallback: fills the
                # translations its dictionaries lack, marked as AI there.
                try:
                    req = json.loads(body.decode('utf-8') or '{}')
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json(400, {'error': 'body must be JSON'})
                    return
                # At most TAGGER_PARALLEL requests reach Ollama; the rest
                # queue here so import workers' waits stay within their timeout.
                with tagger._background_inference():
                    self._model_call(lambda: translate(tagger, req))
                return
            image = extract_image(self.headers.get('Content-Type', ''), body)
            if not image:
                self._json(400, {'error': 'no image in request (raw body or multipart "image")'})
                return
            query = parse_qs(url.query)
            if url.path == '/score':
                # Each label's recognition score (labels: JSON [{"word", "pos"}]).
                try:
                    labels = json.loads((query.get('labels') or ['[]'])[0])
                    assert isinstance(labels, list)
                except (ValueError, AssertionError):
                    self._json(400, {'error': 'labels must be a JSON list'})
                    return
                lang = _param(query, 'lang', LANGS, 'en')
                self._model_call(lambda: {'scores': tagger.score(image, labels, lang),
                                          'prompt': SCORE_PROMPT_VERSION, 'model': tagger.model})
                return
            level = (query.get('level') or ['A1'])[0].upper()
            level = level if level in LEVELS else 'A1'
            lang = _param(query, 'lang', LANGS, 'en')
            native = _param(query, 'native', LANGS, 'zh-TW')
            focus = _param(query, 'focus', FOCUS, None)
            exclude = [w for w in (query.get('exclude') or [''])[0].split(',') if w.strip()]
            mode = (query.get('mode') or [''])[0].strip().lower()
            if mode in ('cefr', 'bands', 'cefr-bands'):
                per_level = CEFR_TAGS_PER_LEVEL
                try:
                    per_level = min(max(int((query.get('per_level') or [per_level])[0]), 1), 5)
                except ValueError:
                    pass
                target_levels = [level.strip().upper() for level in
                                 (query.get('levels') or [''])[0].split(',')
                                 if level.strip().upper() in LEVELS]
                existing_counts = {level: 0 for level in LEVELS}
                for part in (query.get('counts') or [''])[0].split(','):
                    key, _, value = part.partition(':')
                    key = key.strip().upper()
                    if key in LEVELS:
                        try:
                            existing_counts[key] = int(value)
                        except ValueError:
                            pass
                internal_topup = (query.get('topup') or ['0'])[0].strip().lower() not in {
                    '0', 'false', 'no', 'off'}
                self._model_call(lambda: {
                    'candidates': tagger.candidates_cefr(
                        image, lang, exclude, per_level, target_levels,
                        existing_counts, internal_topup),
                    'level': level, 'lang': lang, 'native': native,
                    'mode': 'cefr', 'perLevel': per_level,
                    'targetLevels': target_levels,
                    'existingCounts': existing_counts,
                    'internalTopup': internal_topup,
                    'prompt': CEFR_PROMPT_VERSION,
                })
                return
            self._model_call(lambda: {
                'candidates': tagger.candidates(image, level, lang, native, focus, exclude),
                'level': level, 'lang': lang, 'native': native,
            })

        def log_message(self, fmt, *args):
            sys.stdout.write(f'{self.log_date_time_string()} {fmt % args}\n')

    return Handler


def load_api_key() -> str:
    key = os.environ.get('TAGGER_API_KEY', '').strip()
    if key:
        return key
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding='utf-8') as f:
            key = f.read().strip()
        if key:
            return key
    key = secrets.token_urlsafe(24)
    with open(KEY_FILE, 'w', encoding='utf-8') as f:
        f.write(key)
    return key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--ollama', default=os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434'))
    parser.add_argument('--model', default=os.environ.get('TAGGER_MODEL', DEFAULT_MODEL))
    args = parser.parse_args()
    tagger_config.check_backend()
    print('Effective config:', tagger_config.effective_config(), flush=True)

    api_key = load_api_key()
    tagger = Tagger(args.ollama, args.model)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(tagger, api_key))
    print(f'Tagging API on http://{args.host}:{args.port}/tag  (model {args.model})')
    where = LLAMACPP_URL + ' (llama-server)' if BACKEND == 'llamacpp' else args.ollama
    print(f'Model server {"reachable" if tagger.ollama_ok() else "NOT reachable"} at {where}')
    print(f'Vision input: max {IMAGE_MAX_EDGE}px JPEG quality {IMAGE_JPEG_QUALITY} ({IMAGE_PREP_VERSION}); '
          f'context {MODEL_CONTEXT}; max output {MODEL_MAX_TOKENS} tokens; '
          f'cefr max {CEFR_MAX_TOKENS}; keep_alive {KEEP_ALIVE!r}')
    print(f'Cache: {CACHE_DIR}; prompt {PROMPT_VERSION}; cefr {CEFR_PROMPT_VERSION}')
    print(f'Model slots: {INFERENCE_PARALLEL} (match llama-server -np; Ollama runs qwen3.5 one at a time).')
    print('Model left as configured (no auto-swap); prefer TAGGER_* / OLLAMA_* tweaks for speed.')
    print(f'X-API-Key: {api_key}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
