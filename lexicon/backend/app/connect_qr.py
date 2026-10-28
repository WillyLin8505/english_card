"""連線 QR code (card #758): 後台產生給 iPad 掃的 App 連線 QR code（網址＋辨識金鑰）。

The key is read on the server the same way the tagger reads it (TAGGER_API_KEY, else
tagger/.api_key) and only ever leaves as pixels inside the PNG. Local requests only: a
request that came through a tunnel or proxy from outside (X-Forwarded-For / Cf-* headers
naming a non-loopback address) gets 403.
"""

from __future__ import annotations

import io
import ipaddress
import os
import socket
import sys
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import Response

REPO = Path(__file__).resolve().parents[3]
DEFAULT_URL = "https://api.willylinai.com/tag"
LAN_PORT = 8765  # tagger's default port
# Headers a reverse proxy / tunnel adds with the real client; cloudflared always sets Cf-*.
FORWARD_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip", "cf-connecting-ip", "true-client-ip")


def _is_loopback(host: str | None) -> bool:
    try:
        return ipaddress.ip_address((host or "").strip().strip("[]")).is_loopback
    except ValueError:
        return False


def require_local(request: Request) -> None:
    if not _is_loopback(request.client.host if request.client else None):
        raise HTTPException(403, "連線 QR code 只能在這台電腦上開啟")
    headers = request.headers
    if any(k.startswith("cf-") for k in headers.keys()):
        raise HTTPException(403, "連線 QR code 只能在這台電腦上開啟")
    for name in FORWARD_HEADERS:
        value = headers.get(name)
        if not value:
            continue
        for part in value.replace(";", ",").split(","):
            part = part.split("=")[-1].strip().strip('"')
            if part and not _is_loopback(part):
                raise HTTPException(403, "連線 QR code 只能在這台電腦上開啟")


def read_tagger_key() -> str:
    """Same lookup as tagger/tagging_server.load_api_key, but never creates the file."""
    key = os.environ.get("TAGGER_API_KEY", "").strip()
    if key:
        return key
    path = REPO / "tagger" / ".api_key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def lan_url() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no packet sent; picks the LAN interface
            ip = s.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else f"http://{ip}:{LAN_PORT}/tag"


def make_png(url: str, api_key: str) -> bytes:
    import qrcode

    sys.path.insert(0, str(REPO / "lexicon" / "tools"))
    from make_connect_qr import build_payload

    buf = io.BytesIO()
    qrcode.make(build_payload(url, api_key)).save(buf, format="PNG")
    return buf.getvalue()


def register(app, auth):
    @app.get("/admin/connect-qr/info", dependencies=[auth])
    def connect_qr_info(request: Request):
        require_local(request)
        return {"default_url": DEFAULT_URL, "lan_url": lan_url(), "has_key": bool(read_tagger_key())}

    @app.get("/admin/connect-qr.png", dependencies=[auth])
    def connect_qr_png(request: Request, url: str = DEFAULT_URL):
        require_local(request)
        if not url.startswith(("http://", "https://")):
            raise HTTPException(400, "網址必須以 http:// 或 https:// 開頭")
        key = read_tagger_key()
        if not key:
            raise HTTPException(503, "找不到辨識金鑰（tagger/.api_key 或 TAGGER_API_KEY）")
        return Response(make_png(url, key), media_type="image/png",
                        headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
