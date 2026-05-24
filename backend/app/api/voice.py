"""Voice WebSocket — push-to-talk for provider mode.

Protocol per turn:
- Client opens WS, sends {"type": "begin"} text frame.
- Client streams binary frames containing LINEAR16 16k PCM.
- Client sends {"type": "end"} text frame when the user releases the mic.
- Server transcribes, runs one orchestrator step, sends back:
    text frame {"type": "transcript", "text": "..."} (what we heard)
    text frame {"type": "draft_state", "stack": ...}
    text frame {"type": "submitted", ...} (zero or more)
    text frame {"type": "assistant_text", "text": "..."}
    binary frames of LINEAR16 16k PCM (TTS audio)
    text frame {"type": "audio_end"}
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from fastapi import APIRouter, Cookie, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import text as sql_text

from app.auth import COOKIE_NAME, _user_id_from_cookie
from app.current_user import load_current_user
from app.db import sessionmaker
from app.models import Conversation, User
from app.provider.orchestrator import TextDelta, TurnResult, get_or_create
from app.voice import (
    TranscriptError,
    TranscriptSilence,
    TranscriptText,
    synthesize,
    transcribe,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["voice"])

# Where it's safe to break the streaming text into a TTS chunk. Matches a
# sentence-ending punctuation followed by whitespace (or end of buffer).
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?][\"')\]]*(?:\s+|$)")
# Don't flush a chunk smaller than this — a couple of words on their own
# have weird prosody when synthesized in isolation.
_MIN_TTS_CHUNK_CHARS = 30


@router.websocket("/voice")
async def voice_ws(
    ws: WebSocket,
    conversation_id: str | None = Query(default=None),
    cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> None:
    await ws.accept()
    user_id = _user_id_from_cookie(cookie)
    if user_id is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with sessionmaker()() as session:
        user = await session.get(User, user_id)
        if user is None or not user.active:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        org_id = user.org_id
        current_user = await load_current_user(session, user.id)

        if conversation_id:
            convo_id = uuid.UUID(conversation_id)
        else:
            convo = Conversation(org_id=org_id, user_id=user.id, mode="provider", channel="voice")
            session.add(convo)
            await session.commit()
            await session.refresh(convo)
            convo_id = convo.id

    orchestrator = get_or_create(
        convo_id, user_id=user_id, org_id=org_id, current_user=current_user
    )

    pcm_buffer = bytearray()
    tts_speed = 1.0  # user-facing multiplier; synthesize() applies the baseline
    try:
        await ws.send_json({"type": "ready", "conversation_id": str(convo_id)})
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if "bytes" in msg and msg["bytes"]:
                pcm_buffer.extend(msg["bytes"])
                continue
            if "text" not in msg:
                continue
            try:
                payload = json.loads(msg["text"])
            except json.JSONDecodeError:
                continue

            mtype = payload.get("type")
            if mtype == "begin":
                pcm_buffer.clear()
                continue
            if mtype == "set_speed":
                try:
                    tts_speed = float(payload.get("speed", 1.0))
                except (TypeError, ValueError):
                    pass  # ignore bad input; keep the previous value
                continue
            if mtype != "end":
                continue

            audio = bytes(pcm_buffer)
            pcm_buffer.clear()
            transcript_result = await transcribe(audio)

            if isinstance(transcript_result, TranscriptError):
                # STT itself failed — speak a user-facing apology so the
                # user knows to try again. The orchestrator never runs.
                error_msg = (
                    "I'm having trouble hearing you right now — "
                    "mind trying again in a moment?"
                )
                await ws.send_json(
                    {"type": "transcript", "text": "", "error": "stt_failed"}
                )
                await ws.send_json({"type": "assistant_text", "text": error_msg})
                try:
                    async for chunk in synthesize(error_msg, speed=tts_speed):
                        await ws.send_bytes(chunk)
                except Exception:
                    logger.exception("TTS failed during STT-error apology")
                await ws.send_json({"type": "audio_end"})
                continue

            if isinstance(transcript_result, TranscriptSilence):
                # Silent / empty buffer — just echo an empty transcript and
                # wait for the next push-to-talk. No bot turn, no TTS.
                await ws.send_json({"type": "transcript", "text": ""})
                continue

            # TranscriptText: happy path.
            assert isinstance(transcript_result, TranscriptText)
            transcript = transcript_result.text
            await ws.send_json({"type": "transcript", "text": transcript})

            logger.info(
                "voice convo=%s user=%s user_message chars=%d",
                convo_id,
                user_id,
                len(transcript),
            )

            # Pipeline: orchestrator deltas → text WS frames; the same
            # text gets buffered into sentence-sized chunks, each handed to
            # a synthesize() task. A drainer awaits those tasks in order
            # and ships audio frames as soon as each chunk's synthesis
            # completes — so TTS starts well before the model finishes
            # writing.
            synth_queue: asyncio.Queue[asyncio.Task[list[bytes]] | None] = (
                asyncio.Queue()
            )

            async def _synth_chunk(chunk_text: str) -> list[bytes]:
                out: list[bytes] = []
                async for audio in synthesize(chunk_text, speed=tts_speed):
                    out.append(audio)
                return out

            async def _audio_drainer() -> None:
                while True:
                    task = await synth_queue.get()
                    if task is None:
                        return
                    try:
                        for audio in await task:
                            await ws.send_bytes(audio)
                    except Exception:
                        logger.exception("TTS chunk failed")

            drainer = asyncio.create_task(_audio_drainer())
            text_buffer = ""

            def _enqueue_sentences(*, flush_remainder: bool) -> None:
                """Pop completed sentences off text_buffer and dispatch them."""
                nonlocal text_buffer
                while True:
                    match = _SENTENCE_BOUNDARY_RE.search(text_buffer)
                    if match and match.end() >= _MIN_TTS_CHUNK_CHARS:
                        chunk_text = text_buffer[: match.end()]
                        text_buffer = text_buffer[match.end() :]
                        synth_queue.put_nowait(
                            asyncio.create_task(_synth_chunk(chunk_text))
                        )
                        continue
                    break
                if flush_remainder and text_buffer.strip():
                    synth_queue.put_nowait(
                        asyncio.create_task(_synth_chunk(text_buffer))
                    )
                    text_buffer = ""

            result: TurnResult | None = None
            async with sessionmaker()() as session:
                async with session.begin():
                    await session.execute(
                        sql_text(f"SET LOCAL app.current_user_id = '{user_id}'")
                    )
                    async for event in orchestrator.step(session, transcript):
                        if isinstance(event, TextDelta):
                            text_buffer += event.text
                            await ws.send_json(
                                {"type": "assistant_text_delta", "text": event.text}
                            )
                            _enqueue_sentences(flush_remainder=False)
                        else:
                            result = event

            # Whatever didn't end on a sentence boundary still needs to be
            # spoken — flush the tail and signal the drainer to stop after
            # the queued tasks complete.
            _enqueue_sentences(flush_remainder=True)
            synth_queue.put_nowait(None)

            # Finalize the chat bubble before waiting on audio — user sees
            # the final text immediately while TTS continues to play.
            assert result is not None
            await ws.send_json({"type": "draft_state", "stack": result.stack_payload})
            for fb_id in result.submitted_feedback_ids:
                await ws.send_json({"type": "submitted", "feedback_id": str(fb_id)})
            await ws.send_json({"type": "assistant_text", "text": result.assistant_text})
            logger.info(
                "voice convo=%s response_complete chars=%d submitted=%d",
                convo_id,
                len(result.assistant_text),
                len(result.submitted_feedback_ids),
            )

            await drainer
            await ws.send_json({"type": "audio_end"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("voice WS error")
        try:
            await ws.close()
        except RuntimeError:
            pass
