"""Google STT/TTS helpers.

v0.1 keeps things simple — half-duplex push-to-talk (see v0.1-scope.md).
The voice WS endpoint accepts a binary audio stream, asks Google STT for
the final transcript, then synthesizes the bot reply via Google TTS and
sends the audio back. No barge-in, no streaming partial transcripts to
the UI (that's a UX upgrade for later).

Audio format: 16kHz mono LINEAR16 PCM in both directions.

STT uses the Speech-to-Text v2 API with the chirp_2 model — chirp_2 is
not available on v1. v2 requires a recognizer URI scoped to a GCP
project; we read the project id from GOOGLE_CLOUD_PROJECT, falling back
to the project_id field in the service-account JSON.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# chirp_2 isn't available on the global endpoint — pick any supported region.
STT_LOCATION = "europe-west4"
STT_MODEL = "chirp_2"


# Tagged-union result for transcribe(). Lets the WS handler distinguish
# the three outcomes — useful text, user-was-silent, and our-side-failed
# — and react with appropriate UX (the user-facing message for an STT
# outage shouldn't be the same as the response to a silent buffer).
@dataclass(frozen=True)
class TranscriptText:
    text: str


@dataclass(frozen=True)
class TranscriptSilence:
    """No speech detected in the audio (silence, noise, empty buffer)."""


@dataclass(frozen=True)
class TranscriptError:
    """STT call failed. `reason` is a human-readable summary for logs."""

    reason: str


TranscriptionResult = TranscriptText | TranscriptSilence | TranscriptError


@lru_cache(maxsize=1)
def _gcp_project_id() -> str:
    """Resolve the GCP project id for the v2 STT recognizer URI."""
    env = os.getenv("GOOGLE_CLOUD_PROJECT")
    if env:
        return env
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and os.path.exists(creds_path):
        with open(creds_path) as f:
            data = json.load(f)
        pid = data.get("project_id")
        if pid:
            return pid
    raise RuntimeError(
        "Cannot determine GCP project id. Set GOOGLE_CLOUD_PROJECT or "
        "ensure the service-account JSON at GOOGLE_APPLICATION_CREDENTIALS "
        "contains a project_id field."
    )


async def transcribe(audio_bytes: bytes) -> TranscriptionResult:
    """Run a one-shot Google STT v2 recognition over a complete utterance.

    Push-to-talk only needs the final transcript, so we wait until the
    user releases the mic and send the whole utterance — no streaming.

    Returns a TranscriptionResult union so the caller can distinguish:
      - TranscriptText:    we got text back
      - TranscriptSilence: empty buffer or STT returned no results
      - TranscriptError:   the STT call itself failed (network, auth,
                           config, quota) — caller should surface a
                           user-facing message, not silently drop the turn
    """
    if not audio_bytes:
        return TranscriptSilence()
    from google.api_core.client_options import ClientOptions
    from google.cloud.speech_v2 import SpeechClient, types  # type: ignore[attr-defined]

    project = _gcp_project_id()
    recognizer = f"projects/{project}/locations/{STT_LOCATION}/recognizers/_"

    def _sync_recognize() -> str:
        # Regional recognizers require a regional endpoint; the default
        # speech.googleapis.com routes only to `global`.
        client = SpeechClient(
            client_options=ClientOptions(
                api_endpoint=f"{STT_LOCATION}-speech.googleapis.com"
            )
        )
        config = types.RecognitionConfig(
            explicit_decoding_config=types.ExplicitDecodingConfig(
                encoding=types.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=SAMPLE_RATE,
                audio_channel_count=1,
            ),
            language_codes=["en-US"],
            model=STT_MODEL,
            features=types.RecognitionFeatures(
                enable_automatic_punctuation=True,
            ),
        )
        request = types.RecognizeRequest(
            recognizer=recognizer,
            config=config,
            content=audio_bytes,
        )
        resp = client.recognize(request=request)
        if not resp.results:
            return ""
        return " ".join(
            r.alternatives[0].transcript for r in resp.results if r.alternatives
        )

    try:
        text = await asyncio.to_thread(_sync_recognize)
    except Exception as e:
        logger.exception("STT failed")
        return TranscriptError(reason=str(e))

    if not text.strip():
        return TranscriptSilence()
    return TranscriptText(text=text)


# Strip the markdown markers that the chat renders visually but which TTS
# would otherwise read literally as "asterisk", "pound", "underscore", etc.
# Order matters: fenced code blocks first (multi-line), then inline `code`
# (which uses single backticks so wouldn't survive a global ` strip), then
# bold (`**`/`__`) before italic so the doubled markers don't get half-eaten.
_MARKDOWN_STRIP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"```[\s\S]*?```"), ""),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__(.+?)__"), r"\1"),
    (re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)"), r"\1"),
    (re.compile(r"(?<!_)_([^_\n]+)_(?!_)"), r"\1"),
    (re.compile(r"^#+\s+", re.MULTILINE), ""),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
    (re.compile(r"^>\s+", re.MULTILINE), ""),
    (re.compile(r"^[-*+]\s+", re.MULTILINE), ""),
    (re.compile(r"^\d+\.\s+", re.MULTILINE), ""),
]


def _strip_markdown_for_tts(text: str) -> str:
    """Best-effort plain-text version of the agent's chat markdown."""
    for pattern, replacement in _MARKDOWN_STRIP_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# Google's TTS speaking_rate defaults to 1.0, which is noticeably slow
# for a conversational agent. Our user-facing "speed=1.0" maps to 1.2× on
# Google's scale so the natural pace is brisk; UI multipliers (0.5–2.0)
# scale from there. Google clamps to [0.25, 4.0]; we mirror.
TTS_RATE_BASELINE = 1.2
TTS_RATE_MIN = 0.25
TTS_RATE_MAX = 4.0


async def synthesize(text: str, *, speed: float = 1.0) -> AsyncIterator[bytes]:
    """Synthesize `text` via Google TTS Neural2 and yield the audio bytes.

    Strips markdown formatting first — TTS would otherwise pronounce `**`
    as "asterisk asterisk" etc., since chat output is markdown-rendered
    visually but the audio path needs plain prose.

    `speed` is the user-facing multiplier (1.0 = default brisk pace).
    Multiplied by TTS_RATE_BASELINE before being sent to Google.
    """
    text = _strip_markdown_for_tts(text)
    if not text.strip():
        return
    speaking_rate = max(TTS_RATE_MIN, min(TTS_RATE_MAX, speed * TTS_RATE_BASELINE))
    from google.cloud import texttospeech  # type: ignore[attr-defined]

    def _sync_synth() -> bytes:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-F",
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE,
            speaking_rate=speaking_rate,
        )
        resp = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        return resp.audio_content

    audio = await asyncio.to_thread(_sync_synth)
    # LINEAR16 from Google is a WAV blob — strip the 44-byte RIFF header
    # so we yield raw PCM only. Otherwise the client interprets the
    # header bytes as int16 samples and you hear a click at the start of
    # every synthesis (~1.4ms of garbage at 16kHz).
    if audio[:4] == b"RIFF":
        audio = audio[44:]
    # Yield in chunks to play back progressively on the client.
    CHUNK = 8 * 1024
    for i in range(0, len(audio), CHUNK):
        yield audio[i : i + CHUNK]
