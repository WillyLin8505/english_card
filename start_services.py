"""Start the local App and card studio; reuse services already running."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
# The internet name served through the Cloudflare tunnel (serve_app --public-host).
# Restarts must carry it, or every request on that name gets 403 (card #473).
PUBLIC_HOST = 'api.willylinai.com'


def ready(port, title):
    try:
        with urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
            return response.status == 200 and title in response.read(100_000).decode('utf-8')
    except (OSError, UnicodeError):
        return False


def ensure_service(script, port, title, extra_args=()):
    if ready(port, title):
        return 'already running'
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'Port {port} is occupied by another or unresponsive service; nothing was stopped.')
    logs = ROOT / '.runtime'
    logs.mkdir(exist_ok=True)
    log_path = logs / f'{port}.log'
    with log_path.open('ab') as log:
        process = subprocess.Popen(
            [sys.executable, str(ROOT / script), '--port', str(port), *extra_args],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt',
        )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if ready(port, title):
            return 'started'
        if process.poll() is not None:
            raise RuntimeError(f'Service on {port} exited. See {log_path}')
        time.sleep(0.25)
    raise RuntimeError(f'Service on {port} is not ready yet. See {log_path}')


def ensure_studio():
    return ensure_service('card_preview/server.py', 8772, '字卡工作室')


def main():
    print(f'Studio: {ensure_studio()} - http://127.0.0.1:8772/')
    print(f'App: {ensure_service("serve_app.py", 8123, "拍照學單字", ["--public-host", PUBLIC_HOST])} - http://127.0.0.1:8123/')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
