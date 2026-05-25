"""Unit tests for locale-aware voice plumbing.

`transcribe` and `synthesize` both translate the frontend locale code
(en-US, es-419, fr-CA, …) into the BCP-47 codes Google's STT v2 and TTS
APIs actually expect. The mapping lives in app.locales.LOCALES; an
incorrect entry there would silently degrade transcription accuracy or
voice naturalness for non-English locales, so we pin every cell of the
table.

Special cases worth noticing:
- es-419 (BCP-47 LatAm Spanish) maps to es-US on Google's side, which
  is the code Google groups Latin American Spanish under.
- An unknown frontend code falls back to en-US silently (a typoed
  locale shouldn't block the whole session).
"""

from __future__ import annotations

from typing import Any

import pytest

from app import voice


class _FakeAlternative:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript


class _FakeResult:
    def __init__(self, transcript: str) -> None:
        self.alternatives = [_FakeAlternative(transcript)]


class _FakeSttResponse:
    def __init__(self, transcripts: list[str]) -> None:
        self.results = [_FakeResult(t) for t in transcripts]


class _FakeTtsResponse:
    def __init__(self, audio: bytes) -> None:
        self.audio_content = audio


def _install_fake_speech_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    capture: dict[str, Any],
) -> None:
    """Replace google.cloud.speech_v2.SpeechClient with one that records
    every RecognizeRequest's `language_codes` into `capture`."""
    import google.cloud.speech_v2 as speech_module

    class _FakeClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def recognize(self, *, request: Any) -> Any:
            capture["language_codes"] = list(request.config.language_codes)
            return _FakeSttResponse([])

    monkeypatch.setattr(speech_module, "SpeechClient", _FakeClient)
    # Bypass the credential-derived project lookup so the test doesn't
    # need real GCP env vars.
    monkeypatch.setattr(voice, "_gcp_project_id", lambda: "fake-project")


def _install_fake_tts_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    capture: dict[str, Any],
) -> None:
    """Replace google.cloud.texttospeech.TextToSpeechClient with one
    that records the voice param's `language_code`. Returns a tiny
    LINEAR16 PCM payload so synthesize()'s consumer doesn't choke."""
    from google.cloud import texttospeech as tts_module

    class _FakeTtsClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def synthesize_speech(self, *, input: Any, voice: Any, audio_config: Any) -> Any:
            capture["language_code"] = voice.language_code
            # Two int16 samples — enough that the function yields once
            # without choking on an empty buffer.
            return _FakeTtsResponse(b"\x00\x00\x00\x00")

    monkeypatch.setattr(tts_module, "TextToSpeechClient", _FakeTtsClient)


_LOCALE_CASES = [
    # (frontend locale, expected Google STT code, expected Google TTS code)
    ("en-US", "en-US", "en-US"),
    ("en-GB", "en-GB", "en-GB"),
    ("es-ES", "es-ES", "es-ES"),
    # The interesting one: BCP-47 says es-419 for LatAm Spanish but
    # Google's catalog uses es-US — the mapping is supposed to bridge.
    ("es-419", "es-US", "es-US"),
    ("fr-FR", "fr-FR", "fr-FR"),
    ("fr-CA", "fr-CA", "fr-CA"),
    ("de-DE", "de-DE", "de-DE"),
    # Unknown code falls back to en-US silently so a typoed locale
    # doesn't break the session.
    ("ja-JP", "en-US", "en-US"),
    ("garbage", "en-US", "en-US"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("locale,expected_stt,_expected_tts", _LOCALE_CASES)
async def test_transcribe_forwards_correct_stt_language_code(
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    expected_stt: str,
    _expected_tts: str,
) -> None:
    capture: dict[str, Any] = {}
    _install_fake_speech_client(monkeypatch, capture=capture)
    await voice.transcribe(b"some-audio", locale=locale)
    assert capture["language_codes"] == [expected_stt]


@pytest.mark.asyncio
@pytest.mark.parametrize("locale,_expected_stt,expected_tts", _LOCALE_CASES)
async def test_synthesize_forwards_correct_tts_language_code(
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    _expected_stt: str,
    expected_tts: str,
) -> None:
    capture: dict[str, Any] = {}
    _install_fake_tts_client(monkeypatch, capture=capture)
    # synthesize() is an async generator — consuming any item triggers
    # the inner sync call that captures the voice param.
    async for _ in voice.synthesize("hello", locale=locale):
        break
    assert capture["language_code"] == expected_tts
