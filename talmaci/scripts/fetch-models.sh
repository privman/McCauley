#!/usr/bin/env bash
# Downloads the models Talmaci needs, once, at install time. The app itself
# never touches the network.
#
#   ./scripts/fetch-models.sh                 # default: whisper small + ro<->en translation
#   ./scripts/fetch-models.sh --whisper large-v3-turbo   # add another whisper model
#   ./scripts/fetch-models.sh --models-dir /some/dir
#
# Whisper models come from the official whisper.cpp collection on Hugging Face.
# Translation models are Helsinki-NLP OPUS-MT (Tatoeba-Challenge releases,
# SentencePiece variants) from the University of Helsinki's own server,
# converted locally to CTranslate2 format (int8) in a throwaway Python venv.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(uname)" == "Darwin" ]]; then
  DEFAULT_MODELS_DIR="$HOME/Library/Application Support/Talmaci/models"
else
  DEFAULT_MODELS_DIR="$SCRIPT_DIR/../models"
fi
MODELS_DIR="${TALMACI_MODELS_DIR:-$DEFAULT_MODELS_DIR}"

WHISPER_MODELS=()
SKIP_WHISPER=0
SKIP_MT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --models-dir) MODELS_DIR="$2"; shift 2 ;;
    --whisper) WHISPER_MODELS+=("$2"); shift 2 ;;
    --skip-whisper) SKIP_WHISPER=1; shift ;;
    --skip-mt) SKIP_MT=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ ${#WHISPER_MODELS[@]} -eq 0 ]]; then
  WHISPER_MODELS=(small)
fi

mkdir -p "$MODELS_DIR"
echo "Installing models into: $MODELS_DIR"

fetch() { # url dest
  echo "  downloading $(basename "$2") ..."
  curl -fSL --retry 4 --retry-delay 2 -C - -o "$2.partial" "$1"
  mv "$2.partial" "$2"
}

# ---- Whisper (speech to text) ----
if [[ $SKIP_WHISPER -eq 0 ]]; then
  for m in "${WHISPER_MODELS[@]}"; do
    dest="$MODELS_DIR/ggml-$m.bin"
    if [[ -f "$dest" ]]; then
      echo "  ggml-$m.bin already present, skipping"
      continue
    fi
    fetch "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$m.bin" "$dest"
  done
fi

# ---- OPUS-MT (translation), converted to CTranslate2 ----
# Release names pinned from the Tatoeba-Challenge model listings
# (https://github.com/Helsinki-NLP/Tatoeba-Challenge), SentencePiece variants.
# eng-ron is multi-target (ron+mol) and needs a >>ron<< prefix token; the app's
# native layer reads it from prefix_token.txt.
convert_mt() { # pair zip_url out_name prefix_token
  local pair="$1" url="$2" out="$3" prefix="$4"
  local out_dir="$MODELS_DIR/$out"
  if [[ -f "$out_dir/model.bin" && -f "$out_dir/source.spm" ]]; then
    echo "  $out already present, skipping"
    return
  fi
  local work
  work="$(mktemp -d)"
  fetch "$url" "$work/model.zip"
  (cd "$work" && unzip -oq model.zip)
  "$VENV_PY" -m ctranslate2.converters.opus_mt --model_dir "$work" \
      --output_dir "$out_dir.tmp" --quantization int8 --force
  cp "$work/source.spm" "$out_dir.tmp/source.spm"
  cp "$work/target.spm" "$out_dir.tmp/target.spm"
  if [[ -n "$prefix" ]]; then
    printf '%s\n' "$prefix" > "$out_dir.tmp/prefix_token.txt"
  fi
  rm -rf "$out_dir"
  mv "$out_dir.tmp" "$out_dir"
  rm -rf "$work"
  echo "  $out installed"
}

if [[ $SKIP_MT -eq 0 ]]; then
  # The ctranslate2 wheel needs Python >= 3.10 (Apple's CLT python3 is 3.9);
  # find the newest suitable interpreter.
  PYBIN=""
  for cand in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
        PYBIN="$cand"
        break
      fi
    fi
  done
  if [[ -z "$PYBIN" ]]; then
    echo "error: need Python >= 3.10 for the one-time model conversion." >&2
    echo "       brew install python   (then re-run this script)" >&2
    exit 1
  fi

  VENV="$MODELS_DIR/.convert-venv"
  if [[ ! -x "$VENV/bin/python" ]]; then
    echo "  creating conversion venv (one-time, using $PYBIN) ..."
    "$PYBIN" -m venv "$VENV"
    "$VENV/bin/pip" -q install --upgrade pip
    "$VENV/bin/pip" -q install "ctranslate2>=4.0,<5" pyyaml sentencepiece numpy
  fi
  VENV_PY="$VENV/bin/python"

  convert_mt ron-eng \
    "https://object.pouta.csc.fi/Tatoeba-MT-models/ron-eng/opus%2Bbt-2021-04-30.zip" \
    "opus-mt-ro-en" ""
  convert_mt eng-ron \
    "https://object.pouta.csc.fi/Tatoeba-MT-models/eng-ron/opus%2Bbt-2021-03-07.zip" \
    "opus-mt-en-ro" ">>ron<<"

  rm -rf "$VENV"
fi

echo "Done. Installed in $MODELS_DIR:"
ls -lh "$MODELS_DIR" | sed 's/^/  /'
