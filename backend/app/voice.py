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
from collections.abc import AsyncIterator
from functools import lru_cache

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
STT_LOCATION = "global"
STT_MODEL = "chirp_2"


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


async def transcribe(audio_bytes: bytes) -> str:
    """Run a one-shot Google STT v2 recognition over a complete utterance.

    Push-to-talk only needs the final transcript, so we wait until the
    user releases the mic and send the whole utterance — no streaming.
    """
    if not audio_bytes:
        return ""
    from google.cloud.speech_v2 import SpeechClient, types  # type: ignore[attr-defined]

    project = _gcp_project_id()
    recognizer = f"projects/{project}/locations/{STT_LOCATION}/recognizers/_"

    def _sync_recognize() -> str:
        client = SpeechClient()
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

    return await asyncio.to_thread(_sync_recognize)


async def synthesize(text: str) -> AsyncIterator[bytes]:
    """Synthesize `text` via Google TTS Neural2 and yield the audio bytes."""
    if not text.strip():
        return
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
        )
        resp = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        return resp.audio_content

    audio = await asyncio.to_thread(_sync_synth)
    # Yield in chunks to play back progressively on the client.
    CHUNK = 8 * 1024
    for i in range(0, len(audio), CHUNK):
        yield audio[i : i + CHUNK]
