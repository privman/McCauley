#!/usr/bin/env bash
# Builds libtalmaci_native (whisper.cpp + CTranslate2 + SentencePiece behind
# one C API) and the talmaci-cli test tool.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

cmake -S native -B native/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/build -j "$JOBS" --target talmaci_native talmaci-cli
echo "Built native/build/$(ls native/build | grep -E '^libtalmaci_native\.(dylib|so)$')"
