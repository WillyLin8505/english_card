"""Single source of truth for tagger runtime defaults (card #70).

Both tagging_server.py and start_llm.py call apply_defaults() at import, so a
bare `python tagging_server.py` gets the same config start_tagger.bat used to
set. An explicit environment variable still overrides a default.
"""
from __future__ import annotations
import os

DEFAULTS = {
    'TAGGER_BACKEND': 'llamacpp',
    'TAGGER_PARALLEL': '4',
    'TAGGER_NUM_CTX': '4096',
    'TAGGER_NUM_PREDICT': '1200',
    # 512px preserves label quality in the live CEFR trial while reducing vision input.
    'TAGGER_IMAGE_MAX_EDGE': '512',
    'TAGGER_JPEG_QUALITY': '65',
    'TAGGER_CEFR_NUM_PREDICT': '820',
    # #44: stop on 3 repeated identical objects.
    'TAGGER_CEFR_REPEAT_GUARD': '1',
    'TAGGER_KEEP_ALIVE': '-1',
}


def apply_defaults(env=None):
    env = os.environ if env is None else env
    for k, v in DEFAULTS.items():
        env.setdefault(k, v)
    return env


def effective_config(env=None):
    env = os.environ if env is None else env
    return {k: env.get(k) for k in DEFAULTS}


def check_backend(env=None):
    """Refuse the slow single-slot Ollama path unless explicitly allowed."""
    env = os.environ if env is None else env
    if env.get('TAGGER_BACKEND', '').strip().lower() == 'ollama' and env.get('TAGGER_ALLOW_OLLAMA') != '1':
        raise SystemExit('TAGGER_BACKEND=ollama is the slow single-slot path; '
                         'set TAGGER_ALLOW_OLLAMA=1 to use it on purpose.')
