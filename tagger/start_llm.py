"""Start llama-server (the engine Ollama ships) with several parallel slots.

Ollama 0.35 serves qwen3.5 one request at a time ("model architecture does
not currently support parallel requests"). The same binary and model file,
started directly with -np, decode several requests together: on the 8 GB
RTX 5060 four slots gave ~1.7x the text throughput of one, with the same
translations (A/B 2026-10-06). tagging_server.py talks to it when
TAGGER_BACKEND=llamacpp (see start_tagger.bat).

    python start_llm.py                # qwen3.5:4b, 4 slots, port 8790
    python start_llm.py --slots 2 --port 8791

Ollama must not keep any model loaded at the same time as llama-server (two
copies do not fit in 8 GB). This script evicts whatever Ollama holds before
it starts (#43) - not just TAGGER_MODEL - because an ad-hoc tool can load a
different tag (e.g. qwen3-vl:4b-instruct-q4_K_M) and, with this machine's
OLLAMA_KEEP_ALIVE=-1, Ollama keeps it resident forever otherwise.
"""
from __future__ import annotations

import tagger_config
tagger_config.apply_defaults()  # card #70
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_LIB = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'lib' / 'ollama'
MODELS = Path(os.environ.get('OLLAMA_MODELS', Path.home() / '.ollama' / 'models'))


def model_blob(name: str) -> Path:
    """The GGUF file of an Ollama model ("qwen3.5:4b"), from its manifest."""
    repo, _, tag = name.partition(':')
    if '/' not in repo:
        repo = f'library/{repo}'
    manifest = MODELS / 'manifests' / 'registry.ollama.ai' / repo / (tag or 'latest')
    layers = json.loads(manifest.read_text(encoding='utf-8'))['layers']
    digest = next(l['digest'] for l in layers if l['mediaType'].endswith('.model'))
    return MODELS / 'blobs' / digest.replace(':', '-')


def cuda_dir() -> Path:
    """cuda_v13 needs a CUDA 13 driver; older drivers (12.x) fail to initialise it."""
    try:
        out = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=10).stdout
        major = int(re.search(r'CUDA Version:\s*(\d+)', out).group(1))
    except (OSError, AttributeError, ValueError, subprocess.SubprocessError):
        major = 12
    preferred = OLLAMA_LIB / ('cuda_v13' if major >= 13 else 'cuda_v12')
    return preferred if preferred.is_dir() else OLLAMA_LIB / 'cuda_v12'


def resident_ollama_models() -> list[str]:
    """Models Ollama currently keeps loaded in VRAM (what ``ollama ps`` shows)."""
    url = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434') + '/api/ps'
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return [m.get('name') or m.get('model') for m in data.get('models', []) if m.get('name') or m.get('model')]


def unload_from_ollama(name: str) -> None:
    """Free the GPU memory of a copy Ollama still keeps loaded (keep_alive -1)."""
    body = json.dumps({'model': name, 'keep_alive': 0}).encode()
    request = urllib.request.Request(
        os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434') + '/api/generate', data=body,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except (urllib.error.URLError, OSError):
        pass  # Ollama not running: nothing to unload


def unload_all_from_ollama() -> list[str]:
    """Evict every model Ollama holds, whatever its name.

    #43: an ad-hoc tool (lexicon/tools/quality_ai.py, fix_photo_senses.py used
    to) can load a *different* Ollama tag, e.g. qwen3-vl:4b-instruct-q4_K_M,
    that unload_from_ollama(args.model) would never touch because the name
    does not match. OLLAMA_KEEP_ALIVE=-1 on this machine then keeps it
    resident forever, overflowing the 8 GB card once llama-server starts too.
    """
    names = resident_ollama_models()
    for name in names:
        unload_from_ollama(name)
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--model', default=os.environ.get('TAGGER_MODEL', 'qwen3.5:4b'))
    ap.add_argument('--slots', type=int, default=int(os.environ.get('TAGGER_PARALLEL', '4')))
    ap.add_argument('--ctx', type=int, default=int(os.environ.get('TAGGER_NUM_CTX', '4096')),
                    help='context per slot (the tagger asks for 4096)')
    ap.add_argument('--port', type=int, default=8790)
    args = ap.parse_args()
    try:  # card #70: never start a second llama-server on the same port
        with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/health', timeout=3) as r:
            if r.status == 200:
                print(f'llama-server already running on :{args.port}; not starting another.', flush=True)
                return
    except Exception:
        pass

    evicted = unload_all_from_ollama()
    if evicted:
        print(f'Ollama had {", ".join(evicted)} resident; unloaded before starting llama-server.',
              flush=True)
    blob, cuda = model_blob(args.model), cuda_dir()
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join([str(cuda), str(OLLAMA_LIB), env.get('PATH', '')])
    env['GGML_BACKEND_PATH'] = str(cuda / 'ggml-cuda.dll')
    command = [str(OLLAMA_LIB / 'llama-server.exe'),
               '--model', str(blob), '--mmproj', str(blob),  # vision projector is in the same file
               '--host', '127.0.0.1', '--port', str(args.port),
               '-c', str(args.ctx * args.slots), '-np', str(args.slots), '-ngl', '999',
               # As Ollama runs it: flash attention, 8-bit KV cache.
               '--flash-attn', 'on', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
               '--jinja', '--no-webui']
    print(f'llama-server: {args.model} ({blob.name[:19]}…), {args.slots} slots × {args.ctx} ctx, '
          f'{cuda.name}, http://127.0.0.1:{args.port}', flush=True)
    return subprocess.call(command, env=env)


if __name__ == '__main__':
    sys.exit(main())
