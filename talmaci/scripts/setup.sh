#!/usr/bin/env bash
# One-shot setup on a Mac: downloads models, builds the native library and the
# app bundle. Needs: Xcode command line tools, CMake (brew install cmake),
# Python 3.9+ (for the one-time model conversion), and network access for this
# script only — the app itself is fully offline.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

./fetch-models.sh "$@"
./build-native.sh
./build-app.sh
