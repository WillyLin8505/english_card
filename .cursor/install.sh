#!/usr/bin/env bash
# Repository bootstrap for the 拍照學英文 (english_card) Flutter app.
# The Flutter SDK and system toolchain live in the base snapshot; this script
# only performs the repo-dependent dependency refresh after checkout. It must
# stay idempotent and terminate (no long-running processes here).
set -euo pipefail

export PATH="/opt/flutter-sdk/bin:${PATH}"

# Enable the Linux desktop target so the app can be run/tested as a GUI app.
flutter config --enable-linux-desktop --no-analytics >/dev/null 2>&1 || true

# Resolve Dart/Flutter package dependencies from the committed pubspec.lock.
flutter pub get
