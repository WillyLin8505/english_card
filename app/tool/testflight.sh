#!/bin/zsh
# M286 (owner 10/27): build a Release .ipa and upload it to TestFlight.
#
# Needs (once, see docs/testflight.md): the paid Apple Developer Program,
# an App Store Connect app record for com.willylinai.photoflashcard, and an
# App Store Connect API key in ~/.appstoreconnect/private_keys/AuthKey_<ID>.p8
# with ASC_KEY_ID and ASC_ISSUER_ID set in the environment (never in git).
#
# The build number is the git commit count, so every upload is higher than
# the last; the version name stays the pubspec one (1.0.0).
set -euo pipefail
export LANG=en_US.UTF-8
cd "${0:A:h}/.."
: "${ASC_KEY_ID:?set ASC_KEY_ID (App Store Connect API key id)}"
: "${ASC_ISSUER_ID:?set ASC_ISSUER_ID (App Store Connect issuer id)}"
# Card #1006 / issue #1528 (owner #265, #910): the store build recognizes photos
# on the device and shows no server fields. A define file with TAGGING_URL,
# TAGGING_API_KEY or DEV_TOOLS would send photos to /tag, which answers 401
# without a key (tested 11/08), and expose URL/key fields in 設定.
DEFINES=${TESTFLIGHT_DEFINES:-store.json}
if grep -Eq 'TAGGING_URL|TAGGING_API_KEY|DEV_TOOLS' "$DEFINES"; then
  echo "ABORT: $DEFINES contains TAGGING_URL/TAGGING_API_KEY/DEV_TOOLS; the store build must not (use store.json, not iphone.json)." >&2
  exit 1
fi
BUILD=$(git rev-list --count HEAD)
source tool/google_config.sh  # Google client IDs (google.local.json), see that file
# Card #1007 (App Review 4.8): a build with Google sign-in must also carry Sign in with Apple.
if [ ${#GOOGLE_DEFINES[@]} -gt 0 ]; then
  if ! grep -q 'com.apple.developer.applesignin' ios/Runner/Runner.entitlements 2>/dev/null      || [ "$(grep -c 'CODE_SIGN_ENTITLEMENTS = "$(APP_ENTITLEMENTS)"' ios/Runner.xcodeproj/project.pbxproj)" -lt 3 ]; then
    echo "ABORT: Google sign-in is configured but Sign in with Apple is not (ios/Runner/Runner.entitlements + CODE_SIGN_ENTITLEMENTS in all 3 configs)." >&2
    exit 1
  fi
fi
# Card #1020 / issue #1544: Signing.local.xcconfig may point APP_ENTITLEMENTS at RunnerFree (free account, no
# Sign in with Apple). Such a build must never be uploaded.
if grep -Eq '^[[:space:]]*APP_ENTITLEMENTS[[:space:]]*=' ios/Flutter/Signing.local.xcconfig 2>/dev/null; then
  echo "ABORT: ios/Flutter/Signing.local.xcconfig overrides APP_ENTITLEMENTS (free-account build). Delete it before uploading; the upload must carry Sign in with Apple." >&2
  exit 1
fi
# Card #1021 / issue #1545 (Mac M831): the store build never talks to a LAN server (no TAGGING_URL,
# on-device recognition, dictionary over https), so App Review should not see
# NSLocalNetworkUsageDescription. Dev builds (iphone.json) keep it in Info.plist; strip it here
# for this build only and put the file back afterwards.
PLIST=ios/Runner/Info.plist
cp "$PLIST" "$PLIST.store-bak"
trap 'mv -f "$PLIST.store-bak" "$PLIST"' EXIT
/usr/libexec/PlistBuddy -c "Delete :NSLocalNetworkUsageDescription" "$PLIST" || true
flutter build ipa --release --build-number="$BUILD" \
  --dart-define-from-file="$DEFINES" ${GOOGLE_DEFINES[@]+"${GOOGLE_DEFINES[@]}"} \
  --export-options-plist=ios/ExportOptions.plist
IPA=$(ls build/ios/ipa/*.ipa | head -1)
xcrun altool --upload-app --type ios --file "$IPA" \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
echo "uploaded build $BUILD: $IPA"
