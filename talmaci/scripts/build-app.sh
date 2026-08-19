#!/usr/bin/env bash
# Builds the SwiftUI app and assembles Talmaci.app (macOS only).
# Prereq: scripts/build-native.sh has produced libtalmaci_native.dylib.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ "$(uname)" != "Darwin" ]]; then
  echo "build-app.sh only works on macOS" >&2
  exit 1
fi

DYLIB="native/build/libtalmaci_native.dylib"
if [[ ! -f "$DYLIB" ]]; then
  echo "missing $DYLIB — run scripts/build-native.sh first" >&2
  exit 1
fi

swift build -c release

APP="build/Talmaci.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Frameworks" "$APP/Contents/Resources"
cp .build/release/Talmaci "$APP/Contents/MacOS/Talmaci"
cp "$DYLIB" "$APP/Contents/Frameworks/"
cp Resources/Info.plist "$APP/Contents/Info.plist"

# Ad-hoc signature is enough for the TCC permission prompts (mic, system
# audio) on your own machine.
codesign --force --deep --sign - "$APP"

echo
echo "Built $APP"
echo "Run it with:  open $APP"
