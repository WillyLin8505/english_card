"""Open Images (Google, dump): sense images, read from a local snapshot.

Only the validation split: class-descriptions-boxable.csv (which of the
~600 boxable classes is "cat", "chair", ...), validation-images-with-rotation.csv
(each image's own URL, licence and author -- Flickr, individually checked)
and validation-annotations-human-imagelabels-boxable.csv (which images a
human verified show which class). ~24 MB total; the full dataset's billions
of rows are not needed for a word's one or two representative pictures.

Pictures bind to sense ids, so -- like wikimedia_commons -- the field
pipeline asks nothing here; app.images reads the snapshot directly
(search_open_images / ingest_open_images).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from .. import config
from .base import Context, SourceAdapter

_BASE = "https://storage.googleapis.com/openimages"
CLASS_DESCRIPTIONS_URL = f"{_BASE}/v5/class-descriptions-boxable.csv"
IMAGES_URL = f"{_BASE}/2018_04/validation/validation-images-with-rotation.csv"
LABELS_URL = f"{_BASE}/2018_04/validation/validation-annotations-human-imagelabels-boxable.csv"


def _download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, open(dest, "wb") as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)


class OpenImages(SourceAdapter):
    key = "open_images"

    def download_snapshot(self, language, snapshot_dir) -> dict:
        if language and language != "en":
            raise ValueError("Open Images 只有英文類別名稱")
        snapshot_dir = Path(snapshot_dir)
        files = {
            "class-descriptions-boxable.csv": CLASS_DESCRIPTIONS_URL,
            "validation-images-with-rotation.csv": IMAGES_URL,
            "validation-annotations-human-imagelabels-boxable.csv": LABELS_URL,
        }
        paths = []
        for name, url in files.items():
            dest = snapshot_dir / name
            _download(url, dest)
            paths.append(dest)
        return {"version": "2018_04-validation", "url": IMAGES_URL, "path": str(snapshot_dir),
                "files": [str(p) for p in paths]}

    def import_snapshot(self, session, snapshot_id: int, files: list[Path]) -> int:
        from .. import images
        return images.build_open_images_index(files)

    def lookup(self, field_key: str, ctx: Context):
        return []
