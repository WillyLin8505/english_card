"""Copy the latest exported language pack into the Flutter app.

    python lexicon/tools/install_app_pack.py [--target en] [--native zh-TW] [--export]

--export builds a fresh export first. The pack lands in
app/assets/lexicon/{target}-{native}.json (+ manifest and audio).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app import db, exporter  # noqa: E402
from app import models as m  # noqa: E402
from app.app_pack import install  # noqa: E402
from app.config import EXPORTS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="en")
    ap.add_argument("--native", default="zh-TW")
    ap.add_argument("--export", action="store_true", help="export a fresh pack first")
    args = ap.parse_args()
    with db.session_scope() as s:
        if args.export:
            rel = exporter.export(s, args.target, args.native, include_audio=True)
            if rel.status != "ready":
                sys.exit(f"export failed: {rel.error}")
        rel = s.execute(select(m.DictionaryRelease).where(
            m.DictionaryRelease.target_language == args.target,
            m.DictionaryRelease.native_language == args.native,
            m.DictionaryRelease.status == "ready").order_by(m.DictionaryRelease.id.desc())).scalars().first()
        if rel is None:
            sys.exit("no ready export for this direction (use --export)")
        print(install(EXPORTS / rel.file_name, args.target, args.native))


if __name__ == "__main__":
    main()
