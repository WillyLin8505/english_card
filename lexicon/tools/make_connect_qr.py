"""Make the first-run connection QR code for the Flutter app (card #272, issue #280).

The app's 設定 → 進階設定：照片辨識連線 → 掃描 QR code reads this code and fills
in the tagging service URL and API key. The key is read from an environment
variable so it never appears in shell history or in a file of this repo:

    set TAGGING_API_KEY=...            (PowerShell: $env:TAGGING_API_KEY = "...")
    python lexicon/tools/make_connect_qr.py --url https://api.willylinai.com/tag --out C:/Users/USER/Desktop/connect.png

The PNG contains the key: keep it off shared drives. Needs `pip install qrcode[pil]`.
"""

import argparse
import json
import os
import sys

PAYLOAD_VERSION = 1  # must match ConnectionQr.version in app/lib/services/connection_qr.dart


def build_payload(url: str, api_key: str) -> str:
    return json.dumps({"v": PAYLOAD_VERSION, "taggingUrl": url, "apiKey": api_key},
                      ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="tagging service endpoint, e.g. https://api.willylinai.com/tag")
    parser.add_argument("--out", required=True, help="PNG file to write")
    parser.add_argument("--key-env", default="TAGGING_API_KEY", help="env var holding the API key")
    args = parser.parse_args()

    api_key = os.environ.get(args.key_env, "").strip()
    if not api_key:
        print(f"環境變數 {args.key_env} 沒有設定，沒有產生 QR code。", file=sys.stderr)
        return 2
    if not args.url.startswith(("http://", "https://")):
        print("--url 必須以 http:// 或 https:// 開頭。", file=sys.stderr)
        return 2

    try:
        import qrcode
    except ImportError:
        print("缺少 qrcode 套件：pip install \"qrcode[pil]\"", file=sys.stderr)
        return 3

    image = qrcode.make(build_payload(args.url, api_key))
    image.save(args.out)
    print(f"已寫入 {args.out}（內含金鑰，請勿外流）。網址：{args.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
