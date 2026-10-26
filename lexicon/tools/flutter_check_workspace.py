"""Isolate Flutter checks from other agents' build/native_assets and .dart_tool.

Copy only check inputs, never local credentials or build caches. The few tests
using repo-relative fixtures keep the same layout and skip behavior.
"""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def check_workspace(root: Path):
    with tempfile.TemporaryDirectory(prefix="english-card-flutter-") as temp:
        checkout = Path(temp)
        app = checkout / "app"
        app.mkdir()
        for name in ("pubspec.yaml", "pubspec.lock", "analysis_options.yaml",
                     "dart_test.yaml", "build.yaml"):
            source = root / "app" / name
            if source.is_file():
                shutil.copy2(source, app / name)
        for name in ("lib", "test", "integration_test", "assets", "tool", "tools",
                     "bin", "card23-backup"):
            source = root / "app" / name
            if source.is_dir():
                shutil.copytree(source, app / name)
        for source in (root / "app").glob("*.dart"):
            shutil.copy2(source, app / source.name)
        for relative in ("pack_sqlite.py",
                         "lexicon/logs/agents/card123.resume.pack.json"):
            source = root / relative
            if source.is_file():
                target = checkout / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        yield app
