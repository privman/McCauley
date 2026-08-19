# Talmaci

*(from Romanian „tălmaci" — interpreter)*

A macOS app that transcribes speech and translates it **live, entirely on
your Mac**. Pick the audio language (Romanian or English), pick the sources
(microphone, system audio, or both), press Start — the transcript and its
translation appear side by side in near-real-time. Nothing ever goes over the
network; the app behaves identically offline.

```
┌───────────────────────────────────────────────────────────────┐
│ [Romanian | English]  →  English     ☑ Microphone ☑ System ▶ │
├───────────────────────────────┬───────────────────────────────┤
│ Transcript — Romanian         │ Translation — English         │
│ Bună dimineața. Astăzi vorbim │ Good morning. Today we are    │
│ despre vreme *și poate...*    │ talking about the weather...  │
├───────────────────────────────┴───────────────────────────────┤
│ ● Live   STT 210 ms · MT 24 ms · total 234 ms    [Copy][Clear]│
└───────────────────────────────────────────────────────────────┘
```

## Requirements

- Apple Silicon Mac, macOS 14.4 or newer
- To build: Xcode command line tools, CMake (`brew install cmake`), Python 3.9+
- ~1 GB of disk for the default models

## Install

```bash
cd talmaci
./scripts/setup.sh
open build/Talmaci.app
```

`setup.sh` does three things (network is used here, **once**, and never by the
app):

1. `fetch-models.sh` — downloads the Whisper speech model (official
   whisper.cpp collection) and the Helsinki-NLP OPUS-MT ro↔en translation
   models (from the University of Helsinki's servers), converting the latter
   to CTranslate2 int8 format in a throwaway Python venv.
   Models land in `~/Library/Application Support/Talmaci/models`.
2. `build-native.sh` — builds `libtalmaci_native.dylib`: whisper.cpp (with
   Metal), CTranslate2 (with Accelerate) and SentencePiece behind one small
   C API.
3. `build-app.sh` — builds the SwiftUI app and assembles `build/Talmaci.app`
   (ad-hoc signed; fine for your own machine).

### Permissions

- **Microphone** — prompted on first Start with the mic source enabled.
- **System audio** — prompted on first Start with the system-audio source
  enabled (System Settings → Privacy & Security → Screen & System Audio
  Recording). Talmaci uses a CoreAudio process tap (macOS 14.4+); no video is
  captured, ever.

## Latency and choosing a model

The requirement this app is built around: **transcription + translation under
500 ms per update** on Apple Silicon. Translation (OPUS-MT via CTranslate2)
costs ~10–40 ms; the budget is really about Whisper.

The footer shows a live `STT · MT · total` readout (an exponential moving
average of actual processing time per update). It turns orange above 500 ms.
Guidance:

| Model             | Size   | Notes                                            |
|-------------------|--------|--------------------------------------------------|
| `small` (default) | 466 MB | Good ro/en accuracy, well under budget on M1+    |
| `medium`          | 1.5 GB | Better accuracy; near/over budget on older chips |
| `large-v3-turbo`  | 1.6 GB | Best accuracy; fits budget on M2 Pro and up      |

Install extras with `./scripts/fetch-models.sh --whisper large-v3-turbo`
(also: `base`, `medium`), then pick the model in **Settings** (⌘,) and watch
the readout on your machine — that's the ground truth.

## Languages

Romanian and English, both directions. The transcription language is chosen
explicitly (no auto-detection); the translation target is the other language.
The OPUS-MT models used are the Tatoeba-Challenge SentencePiece releases
(`ron-eng opus+bt-2021-04-30`, `eng-ron opus+bt-2021-03-07`). Additional
languages would need the same model families (Whisper covers ~90 languages;
OPUS-MT most pairs) — the plumbing is language-agnostic.

## How it works

```
mic ──┐ AVAudioEngine
      ├──► 16 kHz mono mix ──► sliding window ──► whisper.cpp (Metal)
sys ──┘ CoreAudio process tap        │                  │
                                     │       LocalAgreement-2 stabilization
                                     ▼                  ▼
                              silence detector   transcript panes
                              (commits window)          │ sentences
                                                        ▼
                                          OPUS-MT via CTranslate2 (int8)
```

- Audio from the selected sources is resampled to 16 kHz mono and mixed.
- Every ~600 ms the open audio window is re-transcribed; words that two
  consecutive decodes agree on are shown as stable text, the changing tail is
  dimmed. On a speech pause (or a 12 s cap) the window is committed and
  restarted — that keeps each Whisper call small and fast.
- Committed text is translated sentence-by-sentence (cached, so nothing is
  re-translated); the open tail is re-translated as it changes.

Layout:

```
Sources/TalmaciCore/   platform-neutral engine: buffers, mixer, hypothesis
                       stabilization, window policy, dlopen bridge (unit-tested,
                       runs on Linux too)
Sources/Talmaci/       SwiftUI app: capture (mic + system tap), session, UI
native/                C API over whisper.cpp + CTranslate2 + SentencePiece
                       (one dylib, built by CMake; talmaci-cli test harness)
scripts/               setup.sh / fetch-models.sh / build-native.sh / build-app.sh
```

## Testing

- `swift test` — engine/logic unit tests (macOS or Linux).
- `./native/test/wiring_test.sh` — native library smoke test using synthetic
  models; no downloads.
- `TALMACI_MODELS_DIR=... ./native/test/e2e_test.sh` — real-model end-to-end
  checks: JFK sample (en) and espeak-synthesized Romanian through the full
  STT → translation pipeline, plus a streaming latency probe.
- CI (`.github/workflows/talmaci.yml`) runs all of the above on Linux **and
  Apple Silicon macOS**, and uploads a built `Talmaci.app` artifact.
- `talmaci-cli` (built next to the dylib) exercises the exact code paths the
  app uses, from any platform:
  `talmaci-cli --stt ggml-small.bin --lang ro --mt models/opus-mt-ro-en --stream audio.wav`

## Privacy / offline guarantee

The app links no networking code and makes no network requests; models load
from local disk. You can verify: `Talmaci.app` runs identically with Wi-Fi
off. Only `scripts/fetch-models.sh` (run by you, at install time) downloads
anything.

## Licenses

whisper.cpp (MIT), CTranslate2 (MIT), SentencePiece (Apache-2.0). OPUS-MT
models are released under CC-BY 4.0 by the Helsinki-NLP group — see
https://github.com/Helsinki-NLP/Tatoeba-Challenge.
