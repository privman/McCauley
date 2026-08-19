#!/usr/bin/env bash
# Wiring smoke test for libtalmaci_native + talmaci-cli, no model downloads:
# - STT path: whisper.cpp's bundled for-tests model (random weights) must load
#   and produce a well-formed (possibly empty) result.
# - MT path: a locally generated tiny random CTranslate2 model must load,
#   tokenize, translate, and detokenize.
# Output quality is meaningless here by design; e2e_test.sh covers quality
# with real models.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

CLI=build/talmaci-cli
TESTS_MODEL=build/_deps/whisper-src/models/for-tests-ggml-tiny.bin
WORK="${TMPDIR:-/tmp}/talmaci-wiring-test"
rm -rf "$WORK" && mkdir -p "$WORK"

[[ -x "$CLI" ]] || { echo "build talmaci-cli first (scripts/build-native.sh)"; exit 1; }
[[ -f "$TESTS_MODEL" ]] || { echo "missing $TESTS_MODEL"; exit 1; }

# 1 s of a 440 Hz tone as a 16 kHz PCM16 WAV, generated with python (portable).
python3 - "$WORK/tone.wav" <<'EOF'
import math, struct, sys, wave
w = wave.open(sys.argv[1], "w")
w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000)))
w.close()
EOF

echo "== STT wiring =="
"$CLI" --stt "$TESTS_MODEL" --lang en --no-gpu "$WORK/tone.wav" | tee "$WORK/stt.out"
grep -q '"segments"' "$WORK/stt.out" || { echo "FAIL: no segments JSON"; exit 1; }

echo "== MT wiring =="
python3 test/make_tiny_ct2_model.py "$WORK/tinymt" > /dev/null
"$CLI" --mt "$WORK/tinymt/model" --text "buna dimineata. astazi vorbim." | tee "$WORK/mt.out"
grep -q '^translation: ' "$WORK/mt.out" || { echo "FAIL: no translation output"; exit 1; }

echo "== combined streaming =="
"$CLI" --stt "$TESTS_MODEL" --lang ro --no-gpu --mt "$WORK/tinymt/model" --stream "$WORK/tone.wav" | tee "$WORK/combined.out"

echo "WIRING TEST PASSED"
