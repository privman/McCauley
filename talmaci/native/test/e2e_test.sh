#!/usr/bin/env bash
# End-to-end quality test with REAL models (network needed once to fetch them;
# CI runs this on both Linux and Apple Silicon macOS).
#
# - English: whisper.cpp's bundled JFK sample -> transcript must contain
#   known words -> en->ro translation must contain the Romanian for "country".
# - Romanian: espeak-ng synthesized speech -> ro transcript -> ro->en
#   translation must contain expected keywords.
#
# Env:
#   TALMACI_MODELS_DIR   where fetch-models.sh installed models (required)
#   WHISPER_MODEL        ggml file name (default ggml-small.bin)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

CLI=build/talmaci-cli
MODELS="${TALMACI_MODELS_DIR:?set TALMACI_MODELS_DIR}"
WHISPER="${WHISPER_MODEL:-ggml-small.bin}"
WORK="${TMPDIR:-/tmp}/talmaci-e2e"
rm -rf "$WORK" && mkdir -p "$WORK"

JFK=build/_deps/whisper-src/samples/jfk.wav
[[ -f "$JFK" ]] || { echo "missing $JFK"; exit 1; }

norm() { # lowercase + strip diacritics, portably (BSD sed mangles multibyte)
  python3 -c "import sys,unicodedata as u; t=u.normalize('NFD', sys.stdin.read().lower()); sys.stdout.write(''.join(c for c in t if not u.combining(c)))"
}

fail=0

echo "== English STT + en->ro translation (JFK sample) =="
"$CLI" --stt "$MODELS/$WHISPER" --lang en --no-gpu \
       --mt "$MODELS/opus-mt-en-ro" "$JFK" | tee "$WORK/en.out"
TRANSCRIPT=$(grep '^transcript: ' "$WORK/en.out" | norm)
TRANSLATION=$(grep '^translation: ' "$WORK/en.out" | norm)
echo "$TRANSCRIPT" | grep -q "your country" || { echo "FAIL: en transcript missing 'your country'"; fail=1; }
echo "$TRANSLATION" | grep -Eq "tara|natiun" || { echo "FAIL: en->ro translation missing 'tara'"; fail=1; }

echo "== Romanian STT + ro->en translation (espeak sample) =="
if command -v espeak-ng >/dev/null; then
  espeak-ng -v ro -s 130 -w "$WORK/ro.wav" \
    "Bună dimineața. Mulțumesc foarte mult pentru ajutor."
  "$CLI" --stt "$MODELS/$WHISPER" --lang ro --no-gpu \
         --mt "$MODELS/opus-mt-ro-en" "$WORK/ro.wav" | tee "$WORK/ro.out"
  RO_TRANSLATION=$(grep '^translation: ' "$WORK/ro.out" | norm)
  echo "$RO_TRANSLATION" | grep -Eq "morning|thank" \
    || { echo "FAIL: ro->en translation missing morning/thank"; fail=1; }
else
  echo "espeak-ng not installed; skipping Romanian audio leg"
fi

echo "== Text-only translation sanity, both directions =="
"$CLI" --mt "$MODELS/opus-mt-ro-en" --text "Bună dimineața. Cum te simți astăzi?" | tee "$WORK/t1.out"
grep '^translation: ' "$WORK/t1.out" | norm | grep -Eq "morning" || { echo "FAIL: ro->en text"; fail=1; }
"$CLI" --mt "$MODELS/opus-mt-en-ro" --text "Good morning. How are you feeling today?" | tee "$WORK/t2.out"
grep '^translation: ' "$WORK/t2.out" | norm | grep -Eq "dimineata|buna" || { echo "FAIL: en->ro text"; fail=1; }

echo "== Streaming latency probe (per-window decode times) =="
"$CLI" --stt "$MODELS/$WHISPER" --lang en --no-gpu --stream "$JFK" | tail -5

[[ $fail -eq 0 ]] && echo "E2E TEST PASSED" || { echo "E2E TEST FAILED"; exit 1; }
