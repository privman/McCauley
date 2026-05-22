"""Google STT/TTS helpers.

v0.1 keeps things simple — half-duplex push-to-talk (see v0.1-scope.md).
The voice WS endpoint accepts a binary audio stream, asks Google STT for
the final transcript, then synthesizes the bot reply via Google TTS and
sends the audio back. No barge-in, no streaming partial transcripts to
the UI (that's a UX upgrade for later).

Audio format: 16kHz mono LINEAR16 PCM in both directions.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


async def transcribe(audio_bytes: bytes) -> str:
    """Run a one-shot Google STT recognition over a complete utterance.

    Streaming is supported in the upstream API but for push-to-talk we
    can wait until the user releases the mic and then send the whole
    utterance — much simpler and the latency penalty is small.
    """
    if not audio_bytes:
        return ""
    from google.cloud import speech  # type: ignore[attr-defined]

    def _sync_recognize() -> str:
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE,
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="chirp_2",
        )
        resp = client.recognize(config=config, audio=audio)
        if not resp.results:
            return ""
        return " ".join(r.alternatives[0].transcript for r in resp.results if r.alternatives)

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
