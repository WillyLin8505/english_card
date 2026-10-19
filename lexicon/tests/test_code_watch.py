import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app import code_watch


def test_changed_file_detects_newer_code():
    assert code_watch.changed_file(loaded_at=time.time() + 3600) is None  # future load: nothing newer
    assert code_watch.changed_file(loaded_at=0) is not None


def test_status_keys():
    assert {"loadedAt", "codeStale", "staleFile"} <= set(code_watch.status())


def test_start_noop_without_env(monkeypatch):
    monkeypatch.delenv("LEXICON_API_AUTORESTART", raising=False)
    code_watch.start()
