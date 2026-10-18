"""Claim the local GPU for quality work (decision 5).

The tags worker yields while `.runtime/qc_gpu_claim` is fresher than 10 min.

hold() also evicts any Ollama model left resident by an ad-hoc tool (#43):
a stray copy (e.g. qwen3-vl:4b-instruct-q4_K_M, kept forever because this
machine sets OLLAMA_KEEP_ALIVE=-1) competes with the tagger's llama-server
and with the quality work's own GPU calls for the same 8 GB card.
"""
from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
CLAIM = Path(__file__).resolve().parents[3] / ".runtime" / "qc_gpu_claim"
UNLOAD_LOG = CLAIM.parent / "ollama_unloads.log"


def _resident_ollama_models() -> list[str]:
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/ps"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return [m.get("name") or m.get("model") for m in data.get("models", []) if m.get("name") or m.get("model")]


def _unload_ollama(name: str) -> None:
    body = json.dumps({"model": name, "keep_alive": 0}).encode()
    req = urllib.request.Request(
        os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except (urllib.error.URLError, OSError):
        pass  # Ollama not running: nothing to unload


def unload_stray_ollama_models() -> list[str]:
    """Evict whatever Ollama has resident and log it. No-op if Ollama is
    down or empty (the common case once #43's callers stopped loading it)."""
    names = _resident_ollama_models()
    for name in names:
        _unload_ollama(name)
    if names:
        CLAIM.parent.mkdir(parents=True, exist_ok=True)
        with UNLOAD_LOG.open("a", encoding="utf-8") as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} unloaded: {", ".join(names)}\n')
    return names


def hold():
    CLAIM.parent.mkdir(parents=True, exist_ok=True)
    CLAIM.write_text(str(time.time()), encoding="utf-8")
    unload_stray_ollama_models()

def release():
    try: CLAIM.unlink()
    except OSError: pass
