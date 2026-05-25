"""Unit tests for app.voice.transcribe — the tagged-union result type.

The function used to return "" on both silence and STT failure, which
left the UI with no way to tell the user "our side broke, try again"
vs "we heard nothing." These tests pin the three outcomes — silence,
error, text — so future refactors can't silently regress the contract.

The real Google STT call is monkeypatched out; we exercise the result-
shaping logic, not the API integration.
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


class _FakeResponse:
    def __init__(self, transcripts: list[str]) -> None:
        self.results = [_FakeResult(t) for t in transcripts]


def _install_fake_speech_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    recognize: Any,
) -> None:
    """Replace google.cloud.speech_v2.SpeechClient with one whose
    recognize() callback we control. Also short-circuits the GCP project
    id lookup so the test doesn't need real credentials or env vars."""
    import google.cloud.speech_v2 as speech_module

    class _FakeClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def recognize(self, *, request: Any) -> Any:
            return recognize(request)

    monkeypatch.setattr(speech_module, "SpeechClient", _FakeClient)
    # _gcp_project_id is lru_cache'd; replace the function directly so the
    # cache state doesn't matter.
    monkeypatch.setattr(voice, "_gcp_project_id", lambda: "fake-project")


@pytest.mark.asyncio
async def test_empty_audio_returns_silence_without_calling_stt() -> None:
    """Don't even bother round-tripping to Google for an empty buffer."""
    result = await voice.transcribe(b"")
    assert isinstance(result, voice.TranscriptSilence)


@pytest.mark.asyncio
async def test_stt_exception_returns_transcript_error_with_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception in the STT call must not propagate — the WS handler
    branches on TranscriptError to speak the user-facing apology."""

    def boom(_request: Any) -> Any:
        raise RuntimeError("upstream STT exploded")

    _install_fake_speech_client(monkeypatch, recognize=boom)
    result = await voice.transcribe(b"some-audio-bytes")
    assert isinstance(result, voice.TranscriptError)
    # `reason` is for logs; we just need a non-empty human-readable string.
    assert "STT exploded" in result.reason


@pytest.mark.asyncio
async def test_empty_stt_response_returns_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No results from STT (clean noise, low confidence drop) → silence,
    not an error — the user's side is the cause, not ours."""

    def empty(_request: Any) -> Any:
        return _FakeResponse([])

    _install_fake_speech_client(monkeypatch, recognize=empty)
    result = await voice.transcribe(b"some-audio-bytes")
    assert isinstance(result, voice.TranscriptSilence)


@pytest.mark.asyncio
async def test_whitespace_only_transcript_returns_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STT occasionally returns an all-whitespace alternative; treat that
    the same as silence so we don't ship an empty turn to the LLM."""

    def whitespace(_request: Any) -> Any:
        return _FakeResponse(["   "])

    _install_fake_speech_client(monkeypatch, recognize=whitespace)
    result = await voice.transcribe(b"some-audio-bytes")
    assert isinstance(result, voice.TranscriptSilence)


@pytest.mark.asyncio
async def test_successful_recognition_returns_joined_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple result segments are joined with spaces — STT v2 can split
    a long utterance across multiple `results` entries."""

    def two_segments(_request: Any) -> Any:
        return _FakeResponse(["hello world.", "how are you?"])

    _install_fake_speech_client(monkeypatch, recognize=two_segments)
    result = await voice.transcribe(b"some-audio-bytes")
    assert isinstance(result, voice.TranscriptText)
    assert result.text == "hello world. how are you?"
