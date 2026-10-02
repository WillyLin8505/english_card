"""Settings from environment variables (lexicon/.env is loaded if present).

Secrets only ever come from the environment — never from code or the
database (spec section 08).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

HOME = Path(__file__).resolve().parents[2]  # lexicon/
REPO = HOME.parent
load_dotenv(HOME / ".env")

RAW_DATA = Path(os.environ.get("LEXICON_RAW_DATA", HOME / "raw-data"))
MEDIA = Path(os.environ.get("LEXICON_MEDIA", HOME / "media"))
EXPORTS = Path(os.environ.get("LEXICON_EXPORTS", HOME / "exports"))
KAIKKI_INDEX = Path(os.environ.get("LEXICON_KAIKKI_INDEX",
                                   RAW_DATA / "kaikki-index.sqlite3"))

API_HOST = os.environ.get("LEXICON_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("LEXICON_API_PORT", "8770"))
API_KEY = os.environ.get("LEXICON_API_KEY", "")

# Legacy AI adapter settings. The adapter is disabled: Qwen3-VL is reserved
# for photo labels and context, never dictionary data.
AI_URL = os.environ.get("LEXICON_AI_URL", "http://127.0.0.1:8765")
AI_KEY = os.environ.get("LEXICON_AI_KEY", "")

USER_AGENT = "EnglishCardLexicon/1.0 (personal vocabulary database)"


def database_url(test: bool = False) -> str:
    explicit = os.environ.get("LEXICON_TEST_DATABASE_URL" if test else "LEXICON_DATABASE_URL")
    if explicit:
        return explicit
    user = os.environ.get("LEXICON_DB_USER", "lexicon")
    password = os.environ.get("LEXICON_DB_PASSWORD", "")
    host = os.environ.get("LEXICON_DB_HOST", "127.0.0.1")
    port = os.environ.get("LEXICON_DB_PORT", "5432")
    name = os.environ.get("LEXICON_DB_NAME", "lexicon") + ("_test" if test else "")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"
