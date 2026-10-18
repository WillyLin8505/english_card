#!/usr/bin/env bash
# Runs the app in the iOS Simulator on a Mac (an iPhone, with the same
# local key files as run_web.bat: tagging.local.json, posthog.local.json).
#   cd app && ./run_ios_sim.sh
set -euo pipefail
cd "$(dirname "$0")"

command -v flutter >/dev/null || { echo "缺 Flutter：brew install --cask flutter"; exit 1; }
command -v pod >/dev/null || { echo "缺 CocoaPods：brew install cocoapods"; exit 1; }
xcrun simctl help >/dev/null 2>&1 || {
  echo "缺 Xcode：從 App Store 安裝後執行 sudo xcodebuild -runFirstLaunch"; exit 1; }

open -a Simulator
for _ in $(seq 1 30); do
  xcrun simctl list devices booted | grep -q iPhone && break
  sleep 2
done
DEVICE=$(xcrun simctl list devices booted | grep -m1 iPhone | sed -E 's/.*\(([0-9A-F-]{36})\).*/\1/')
[ -n "$DEVICE" ] || { echo "沒有開機中的 iPhone 模擬器：在 Simulator 選單 File → Open Simulator 選一台"; exit 1; }

flutter pub get
DEFINES=()
[ -f tagging.local.json ] && DEFINES+=(--dart-define-from-file=tagging.local.json)
[ -f posthog.local.json ] && DEFINES+=(--dart-define-from-file=posthog.local.json)
flutter run -d "$DEVICE" ${DEFINES[@]+"${DEFINES[@]}"} "$@"
