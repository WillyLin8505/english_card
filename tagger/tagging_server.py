"""Photo-tagging API for 拍照學英文 — spec-01 sections 2 and 3:

    運算環境   Predator 上 Ollama + Qwen3-VL-4B（Q4）
    本機 API   127.0.0.1:8765
    可選連線   Cloudflare Tunnel
    請求格式   Web: raw JPEG body + X-API-Key；原生: 可使用 multipart

This is stage 1 of the spec's two-stage recognition (第一階段 · 理解照片):
the model looks at the photo and proposes 8-10 labels — nouns, verbs,
adjectives, adverbs and phrases — each with its picture context.
Stage 2 (choosing at most 5 to learn, by level, personal vocabulary,
relevance, usefulness and part-of-speech mix) runs in the app, because
it needs the learner's own vocabulary state. "模型不得直接決定最後五個詞".

POST /tag?level=B1&lang=en&native=zh-TW[&focus=harder][&exclude=cup,mug]\n        POST /tag?mode=cefr&lang=en[&per_level=3][&exclude=...]  (>=3 labels per A1-C2)
    Header  X-API-Key: <key>
    Body    the image — raw (Content-Type: image/jpeg) or multipart/form-data
            with an "image" part.
    level   the learner's CEFR level; candidates centre on it.
    focus   harder | easier | actions | descriptions — a top-up call when
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

GET /health  -> {"ok": true, "model": ..., "ollama": true, "keyOk": true|false|null}

Standard library only; `wordfreq` (pip) and data/raw/cmudict.dict are
used when present. Run:  python tagger/tagging_server.py
The API key is read from TAGGER_API_KEY, else tagger/.api_key (created
with a random key on first run and printed at start-up).
"""

from __future__ import annotations

import argparse
import base64
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
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KEY_FILE = os.path.join(HERE, '.api_key')
CMUDICT = os.path.join(ROOT, 'data', 'raw', 'cmudict.dict')
DEFAULT_MODEL = 'qwen3-vl:4b-instruct-q4_K_M'
MAX_BODY = 20 * 1024 * 1024
PROMPT_VERSION = 'photo-tags-context-v5'
CACHE_DIR = os.path.join(HERE, 'cache')
MODEL_CONTEXT = int(os.environ.get('TAGGER_NUM_CTX', '4096'))
MODEL_MAX_TOKENS = int(os.environ.get('TAGGER_NUM_PREDICT', '600'))
TRANSLATE_MAX_TOKENS = int(os.environ.get('TAGGER_TRANSLATE_NUM_PREDICT', '2400'))
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
    'harder': 'This time prefer specific, precise labels instead of broad category names.',
    'easier': 'This time prefer common, broad everyday labels.',
    'actions': 'This time prefer verbs and action phrases.',
    'descriptions': 'This time prefer adjectives and adverbs describing what is seen.',
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
    'required': ['candidates'],
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
    lines = [
        f'Inspect this photo and return 6 to 8 useful {lang_name} labels.',
        'Only identify what the photo supports: objects, visible actions, visible qualities, '
        'spatial relations and short scene phrases. Do not translate, define, estimate CEFR, '
        'write example sentences, or provide pronunciation.',
        'Mix concrete nouns, verbs, adjectives, adverbs and short phrases. At most half may '
        'be nouns. Prefer one clear label for each distinct visual idea.',
        'Use ordinary vocabulary, not company, product, model or person names. Ignore words '
        'that are only read from logos, packaging, watermarks or signs.',
    ]
    if focus in FOCUS:
        lines.append(FOCUS[focus])
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


SCORE_PROMPT_VERSION = 'label-check-v1'
SCORE_MAX_LABELS = 24
CEFR_PROMPT_VERSION = 'photo-tags-cefr-bands-v3'
CEFR_TAGS_PER_LEVEL = 3
CEFR_MAX_TOKENS = int(os.environ.get('TAGGER_CEFR_NUM_PREDICT', '1000'))
CEFR_CANDIDATE_SCHEMA = {
    'type': 'object',
    'properties': {
        'candidates': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'word': {'type': 'string'},
                    'pos': {'type': 'string', 'enum': POS},
                    'cefr': {'type': 'string', 'enum': LEVELS},
                    'evidence': {'type': 'string'},
                    'point': {'type': 'array', 'items': {'type': 'integer'}},
                    'box': {'type': 'array', 'items': {'type': 'integer'}},
                },
                'required': ['word', 'pos', 'cefr', 'evidence', 'point', 'box'],
            },
        }
    },
    'required': ['candidates'],
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
                      per_level: int = CEFR_TAGS_PER_LEVEL) -> str:
    """Ask for at least ``per_level`` concrete visible labels in each CEFR band."""
    lang_name = LANGS[lang]
    lines = [
        f'Inspect this photo and return English learning labels for a {lang_name} learner.',
        f'Return AT LEAST {per_level} distinct concrete noun or short noun-phrase labels for EACH '
        f'CEFR band A1, A2, B1, B2, C1 and C2 (at least {per_level * 6} total, at most '
        f'{per_level * 6 + 4}). Every band must meet the minimum.',
        'Only name what is clearly visible. Prefer concrete vocabulary a learner can point to '
        '(objects, parts, materials, tools, foods, clothing, plants, animals). Avoid brand, '
        'product, model and person names. Ignore words only read from logos or watermarks.',
        'Do not repeat the same idea with synonyms across bands; each word once. Spread difficulty: '
        'A1 very common everyday words; A2 still common; B1 intermediate; B2 more precise; '
        'C1 advanced but still visible; C2 rare or technical but still visible in the photo.',
        'For harder bands that feel thin, dig for precise visible detail (parts, materials, '
        'textures, tools, spatial nouns) rather than leaving a band short. Never invent objects '
        'that are not in the photo.',
        'For each candidate give:',
        f'- word: dictionary form (singular noun), lowercase, in {lang_name}',
        '- pos: prefer noun; phrase only for short visible compounds',
        '- cefr: one of A1 A2 B1 B2 C1 C2 for that label',
        '- evidence: at most 8 English words describing its meaning in this photo',
        '- point: [x, y] of that evidence, relative coordinates from 0 to 1000',
        '- box: [x1, y1, x2, y2] around that evidence, relative coordinates from 0 to 1000',
    ]
    if exclude:
        lines.append('Do not repeat these words: ' + ', '.join(exclude[:60]) + '.')
    lines.append('Reply with JSON only.')
    return '\n'.join(lines)


def cefr_band_counts(items: list[dict]) -> dict[str, int]:
    """How many candidates currently sit in each CEFR band."""
    counts = {level: 0 for level in LEVELS}
    for item in items:
        level = str(item.get('cefr') or item.get('modelLevel') or '').strip().upper()
        if level in counts:
            counts[level] += 1
    return counts


def short_cefr_bands(items: list[dict], per_level: int) -> list[str]:
    """CEFR bands that still have fewer than ``per_level`` distinct labels."""
    counts = cefr_band_counts(items)
    return [level for level in LEVELS if counts[level] < per_level]


def build_cefr_topup_prompt(lang: str, short_levels: list[str], exclude: list[str],
                            per_level: int, counts: dict[str, int]) -> str:
    """Ask only for the missing labels in short CEFR bands — no invented objects."""
    lang_name = LANGS[lang]
    needs = [
        f'{level}: need at least {per_level - counts.get(level, 0)} more'
        for level in short_levels
    ]
    lines = [
        f'Inspect this photo again. Some CEFR bands still need more {lang_name} labels.',
        'Return ONLY new concrete noun or short noun-phrase labels for these short bands:',
        '; '.join(needs) + '.',
        'Only name what is clearly visible. Never invent objects that are not in the photo.',
        'Do not repeat any word already listed. Prefer vocabulary that honestly matches each band.',
        'For each candidate give:',
        f'- word: dictionary form (singular noun), lowercase, in {lang_name}',
        '- pos: prefer noun; phrase only for short visible compounds',
        '- cefr: one of ' + ', '.join(short_levels) + ' for that label',
        '- evidence: at most 8 English words describing its meaning in this photo',
        '- point: [x, y] of that evidence, relative coordinates from 0 to 1000',
        '- box: [x1, y1, x2, y2] around that evidence, relative coordinates from 0 to 1000',
    ]
    if exclude:
        lines.append('Do not repeat these words: ' + ', '.join(exclude[:80]) + '.')
    lines.append('Reply with JSON only.')
    return '\n'.join(lines)


def merge_cefr_topup(existing: list[dict], extra: list[dict], per_level: int) -> list[dict]:
    """Append top-up labels only into bands that are still short. No padding with fakes."""
    items = list(existing)
    seen = {str(item.get('word', '')).strip().lower() for item in items}
    for item in extra:
        word = str(item.get('word', '')).strip().lower()
        level = str(item.get('cefr') or item.get('modelLevel') or '').strip().upper()
        if not word or word in seen or level not in LEVELS:
            continue
        if cefr_band_counts(items)[level] >= per_level:
            continue
        seen.add(word)
        items.append(item)
    return items



def build_score_prompt(labels: list[dict], lang: str = 'en') -> str:
    lines = [
        f'Check each {LANGS[lang]} label against this photo.',
        'For every label answer shown = true only if the photo clearly shows it (the object, '
        'the action, the quality or the spatial relation); otherwise shown = false.',
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
        word = _SPACE.sub(' ', str(c.get('word', '')).strip().lower()).strip(' .,"\'')
        if not word or word in seen or len(word) > 40:
            continue
        evidence = str(c.get('evidence', '')).strip()[:120]
        if lang == 'en' and lexicon is not None and lexicon.is_foreign(word):
            continue
        if _looks_like_name_label(word, evidence):
            continue
        point = c.get('point') or []
        if len(point) < 2:
            continue
        seen.add(word)
        pos = str(c.get('pos', '')).strip().lower()
        if pos not in POS:
            pos = 'phrase' if ' ' in word else 'noun'
        model_cefr = str(c.get('cefr') or '').strip().upper()
        if model_cefr not in LEVELS:
            model_cefr = None
        item = {
            'word': word,
            'lemma': word,
            'pos': pos,
            # Compatibility fields are intentionally empty. The Flutter app fills
            # them from its downloaded dictionary, never from the vision model.
            'meaning': '',
            'cefr': model_cefr,
            'modelLevel': model_cefr,
            'evidence': evidence,
            'point': [round(min(max(float(point[0]) / 1000, 0.0), 1.0), 4),
                      round(min(max(float(point[1]) / 1000, 0.0), 1.0), 4)],
            # The label's area (spec: 標籤座標／範圍), fractions x1, y1, x2, y2.
            'box': _box(c.get('box')),
            'visualConfidence': 0.7,
            'usefulness': 0.5,
            'inferred': False,
        }
        if lexicon is not None:
            item.update(lexicon.describe(word))
        out.append(item)
    return out


def loads_salvaging(text: str):
    """The model's JSON, or — when the reply was cut off at the output token
    limit — everything up to the last complete object in a list, closed
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


class Lexicon:
    """Optional local word data: frequency (wordfreq) and US IPA (CMUdict)."""

    def __init__(self, cmudict_path: str = CMUDICT):
        try:
            from wordfreq import zipf_frequency
            self._zipf = zipf_frequency
        except ImportError:
            self._zipf = None
        self._ipa: dict[str, str] = {}
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
        language — calendrier, fenêtre, fenster — not an English loanword
        (croissant, espresso, tortilla stay). Spec: 第一階段只產生英文詞條."""
        if self._zipf is None or ' ' in word:
            return False
        en = self._zipf(word, 'en')
        other = max(self._zipf(word, lang) for lang in self._OTHER_LANGS)
        return en < 2.0 and other >= en + 2.0

    def describe(self, word: str, lang: str = 'en') -> dict:
        out = {}
        if self._zipf is not None:
            out['zipf'] = round(self._zipf(word, lang.split('-')[0]), 2)
        if lang == 'en' and (ipa := self.ipa(word)):
            out['ipa'] = ipa
        return out


def prepare_image(image: bytes) -> tuple[bytes, dict]:
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


class Tagger:
    def __init__(self, ollama_url: str, model: str, lexicon: Lexicon | None = None):
        self.ollama_url = ollama_url.rstrip('/')
        self.model = model
        self.lexicon = lexicon
        self._inference_lock = threading.Lock()
        os.makedirs(CACHE_DIR, exist_ok=True)

    def ollama_ok(self) -> bool:
        try:
            with urllib.request.urlopen(f'{self.ollama_url}/api/version', timeout=3):
                return True
        except (urllib.error.URLError, OSError):
            return False

    def _chat(self, prompt: str, schema: dict, image: bytes | None = None,
              temperature: float = 0, max_tokens: int | None = None,
              logprobs: bool = False):
        """The model's JSON reply; with logprobs, (reply, per-token logprobs)."""
        message = {'role': 'user', 'content': prompt}
        if image is not None:
            message['images'] = [base64.b64encode(image).decode()]
        body = {
            'model': self.model,
            'messages': [message],
            'format': schema,
            'stream': False,
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

    def score(self, image: bytes, labels: list[dict], lang: str = 'en') -> list[dict]:
        """Each label's recognition score: the model looks at the photo again
        and answers, label by label, whether it is shown; the score is its
        probability of answering yes (0–1), read from the token logprobs."""
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
        with self._inference_lock:
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
        # Difficulty and native language do not alter visual recognition. They are
        # applied later from the learner profile and downloaded word database.
        key_data = json.dumps({
            'image': hashlib.sha256(image).hexdigest(),
            'model': self.model,
            'prompt': PROMPT_VERSION,
            'lang': lang,
            'focus': focus,
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

        # One inference at a time keeps the 8 GB GPU from allocating parallel KV
        # caches. Check the disk cache again after waiting for another request.
        with self._inference_lock:
            try:
                with open(cache_file, encoding='utf-8') as f:
                    cached = json.load(f)
                if isinstance(cached, list):
                    return cached
            except (FileNotFoundError, OSError, ValueError, TypeError):
                pass
            prepared, _ = prepare_image(image)
            content = self._chat(build_prompt(level, lang, native, focus, exclude),
                                 CANDIDATE_SCHEMA, prepared)
            items = to_candidates(content.get('candidates', []), self.lexicon, exclude, lang)
            temporary = cache_file + f'.{os.getpid()}.tmp'
            try:
                with open(temporary, 'w', encoding='utf-8') as f:
                    json.dump(items, f, ensure_ascii=False, separators=(',', ':'))
                os.replace(temporary, cache_file)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
            return items

    def candidates_cefr(self, image: bytes, lang: str = 'en',
                        exclude: list[str] | None = None,
                        per_level: int = CEFR_TAGS_PER_LEVEL) -> list[dict]:
        """At least ``per_level`` visible noun/phrase labels for each CEFR band."""
        key_data = json.dumps({
            'image': hashlib.sha256(image).hexdigest(),
            'model': self.model,
            'prompt': CEFR_PROMPT_VERSION,
            'lang': lang,
            'per_level': per_level,
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

        with self._inference_lock:
            try:
                with open(cache_file, encoding='utf-8') as f:
                    cached = json.load(f)
                if isinstance(cached, list):
                    return cached
            except (FileNotFoundError, OSError, ValueError, TypeError):
                pass
            prepared, _ = prepare_image(image)
            content = self._chat(build_cefr_prompt(lang, exclude, per_level),
                                 CEFR_CANDIDATE_SCHEMA, prepared,
                                 max_tokens=CEFR_MAX_TOKENS)
            items = to_candidates(content.get('candidates', []), self.lexicon, exclude, lang)
            # One top-up pass for bands still below per_level. Never invent filler words.
            short = short_cefr_bands(items, per_level)
            if short:
                counts = cefr_band_counts(items)
                known = list(dict.fromkeys(
                    [*(exclude or []), *[str(i.get('word', '')) for i in items]]
                ))
                topup = self._chat(
                    build_cefr_topup_prompt(lang, short, known, per_level, counts),
                    CEFR_CANDIDATE_SCHEMA, prepared, max_tokens=CEFR_MAX_TOKENS)
                extra = to_candidates(topup.get('candidates', []), self.lexicon, known, lang)
                items = merge_cefr_topup(items, extra, per_level)
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


TRANSLATE_PROMPT_VERSION = 'translate-v4'
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
    items = [{'id': str(i.get('id', n)), 'text': str(i.get('text', ''))[:600],
              **({'context': str(i['context'])[:200]} if i.get('context') else {})}
             for n, i in enumerate(req.get('items') or []) if str(i.get('text', '')).strip()][:40]
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
    prompt = '\n'.join([
        TRANSLATE_KIND[kind].format(lang=LANGS[lang], native=LANGS[native]),
        # Without this the small model echoes the English input back.
        f'Return one result per item, with the same id, in JSON. "text" is the {out_lang} '
        'result, never a copy of the input'
        + (TARGET_EXAMPLE.get(kind, '.') if in_target else TRANSLATE_EXAMPLE.get(native, '.')),
        NATIVE_RULE[native].replace('「meaning」', '所有輸出') if native == 'zh-TW' and not in_target else '',
        'Items: ' + json.dumps(items, ensure_ascii=False),
    ])
    # Many sentences in one call run past the photo tagging's output cap.
    content = tagger._chat(prompt, TRANSLATE_SCHEMA, temperature=0,
                           max_tokens=TRANSLATE_MAX_TOKENS)
    wanted = {i['id'] for i in items}
    out = [{'id': str(r.get('id')), 'text': str(r.get('text', '')).strip()}
           for r in content.get('items', []) if str(r.get('id')) in wanted
           and str(r.get('text', '')).strip()]
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
            if urlparse(self.path).path == '/health':
                sent = self.headers.get('X-API-Key')
                key_ok = None if sent is None else secrets.compare_digest(sent, api_key)
                self._json(200, {'ok': True, 'model': tagger.model,
                                 'ollama': tagger.ollama_ok(), 'keyOk': key_ok,
                                 'prep': IMAGE_PREP_VERSION,
                                 'cefrNumPredict': CEFR_MAX_TOKENS,
                                 'keepAlive': KEEP_ALIVE})
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
            try:
                result = fn()
            except urllib.error.URLError as e:
                self._json(502, {'error': f'Ollama not reachable at {tagger.ollama_url}: {e.reason}'})
                return
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
                # The service is up; this photo's reply was unusable. 422,
                # not 502, so the app fails this photo and tags the next one.
                self._json(422, {'error': f'unexpected model reply: {e}'})
                return
            result.update({'model': tagger.model, 'elapsedMs': int((time.time() - started) * 1000)})
            self._json(200, result)

        def do_POST(self):
            url = urlparse(self.path)
            if url.path not in ('/tag', '/enrich', '/translate', '/score'):
                self._json(404, {'error': 'not found'})
                return
            if not secrets.compare_digest(self.headers.get('X-API-Key', ''), api_key):
                self._json(401, {'error': 'missing or wrong X-API-Key'})
                return
            body = self._body()
            if body is None:
                return
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
                # A single 8 GB GPU has one Ollama slot. Queue here so four
                # import workers do not create overlapping Ollama requests
                # whose client-side waits exceed the import timeout.
                with tagger._inference_lock:
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
                self._model_call(lambda: {
                    'candidates': tagger.candidates_cefr(image, lang, exclude, per_level),
                    'level': level, 'lang': lang, 'native': native,
                    'mode': 'cefr', 'perLevel': per_level,
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

    api_key = load_api_key()
    tagger = Tagger(args.ollama, args.model)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(tagger, api_key))
    print(f'Tagging API on http://{args.host}:{args.port}/tag  (model {args.model})')
    print(f'Ollama {"reachable" if tagger.ollama_ok() else "NOT reachable"} at {args.ollama}')
    print(f'Vision input: max {IMAGE_MAX_EDGE}px JPEG quality {IMAGE_JPEG_QUALITY} ({IMAGE_PREP_VERSION}); '
          f'context {MODEL_CONTEXT}; max output {MODEL_MAX_TOKENS} tokens; '
          f'cefr max {CEFR_MAX_TOKENS}; keep_alive {KEEP_ALIVE!r}')
    print(f'Cache: {CACHE_DIR}; prompt {PROMPT_VERSION}; cefr {CEFR_PROMPT_VERSION}')
    print('Serial inference lock on; OLLAMA_NUM_PARALLEL should stay 1 on one GPU.')
    print('Model left as configured (no auto-swap); prefer TAGGER_* / OLLAMA_* tweaks for speed.')
    print(f'X-API-Key: {api_key}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
