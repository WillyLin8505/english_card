#!/usr/bin/env bash
# Card #1001 / issue #1523: Google sign-in build settings, shared by
# run_ios_sim.sh and tool/testflight.sh (source it, then use $GOOGLE_DEFINES).
#
# Reads app/google.local.json (git-ignored, *.local.json):
#   {"GOOGLE_IOS_CLIENT_ID": "<n>-<x>.apps.googleusercontent.com",
#    "GOOGLE_SERVER_CLIENT_ID": "<n>-<y>.apps.googleusercontent.com",
#    "GOOGLE_WEB_CLIENT_ID": "<n>-<z>.apps.googleusercontent.com"}
# (card #1271) GOOGLE_WEB_CLIENT_ID = the web client for `flutter build web
# --dart-define-from-file=google.local.json`; authorised JavaScript origins
# https://api.willylinai.com and http://127.0.0.1:8123. The backend needs ALL
# the IDs (iOS, server, web) in LEXICON_GOOGLE_CLIENT_IDS (comma list).
# Client IDs are not secrets but stay out of git. Passes the file as a
# --dart-define-from-file and writes ios/Flutter/Google.local.xcconfig
# (git-ignored) with the reversed iOS client ID, which Info.plist uses as a
# URL scheme (CFBundleURLTypes). Without the file nothing changes: no Google
# button, and a harmless placeholder scheme from Google.defaults.xcconfig.
# Never touches TAGGING_URL / TAGGING_API_KEY / DEV_TOOLS.
GOOGLE_DEFINES=()
_xc="ios/Flutter/Google.local.xcconfig"
rm -f "$_xc"
if [ -f google.local.json ]; then
  _ios=$(python3 -c "import json;print(json.load(open('google.local.json')).get('GOOGLE_IOS_CLIENT_ID',''))")
  GOOGLE_DEFINES=(--dart-define-from-file=google.local.json)
  if [ -n "$_ios" ]; then
    _rev="com.googleusercontent.apps.${_ios%.apps.googleusercontent.com}"
    echo "GOOGLE_REVERSED_CLIENT_ID=$_rev" > "$_xc"
  fi
fi
