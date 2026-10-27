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
BUILD=$(git rev-list --count HEAD)
flutter build ipa --release --build-number="$BUILD" \
  --dart-define-from-file=iphone.json \
  --export-options-plist=ios/ExportOptions.plist
IPA=$(ls build/ios/ipa/*.ipa | head -1)
xcrun altool --upload-app --type ios --file "$IPA" \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
echo "uploaded build $BUILD: $IPA"
