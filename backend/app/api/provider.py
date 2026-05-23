"""Provider WebSocket endpoint.

The frontend opens a WS per conversation; each message from the client is
{"type": "user_text", "text": "..."}. We respond with one or more
{"type": "assistant_text" | "draft_state" | "submitted"} frames.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Cookie, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import _user_id_from_cookie, COOKIE_NAME
from app.current_user import UserProfile, load_current_user
from app.db import sessionmaker
from app.models import Conversation, User
from app.provider.orchestrator import TextDelta, TurnResult, drop, get_or_create

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["provider"])


async def _authenticate(
    ws: WebSocket, cookie: str | None
) -> tuple[uuid.UUID, uuid.UUID, UserProfile] | None:
    user_id = _user_id_from_cookie(cookie)
    if user_id is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    async with sessionmaker()() as session:
        user = await session.get(User, user_id)
        if user is None or not user.active:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
        current_user = await load_current_user(session, user.id)
        return user.id, user.org_id, current_user


async def _set_pg_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(sql_text(f"SET LOCAL app.current_user_id = '{user_id}'"))


@router.websocket("/provider")
async def provider_ws(
    ws: WebSocket,
    conversation_id: str | None = Query(default=None),
    cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> None:
    await ws.accept()
    auth = await _authenticate(ws, cookie)
    if auth is None:
        return
    user_id, org_id, current_user = auth

    # Open or resume a conversation row.
    async with sessionmaker()() as session:
        if conversation_id:
            convo_id = uuid.UUID(conversation_id)
            convo = await session.get(Conversation, convo_id)
            if convo is None:
                await ws.send_json({"type": "error", "message": "conversation not found"})
                await ws.close()
                return
        else:
            convo = Conversation(
                org_id=org_id, user_id=user_id, mode="provider"
            )
            session.add(convo)
            await session.commit()
            await session.refresh(convo)
            convo_id = convo.id

    orchestrator = get_or_create(
        convo_id, user_id=user_id, org_id=org_id, current_user=current_user
    )

    try:
        await ws.send_json({"type": "ready", "conversation_id": str(convo_id)})
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "invalid json"})
                continue
            mtype = msg.get("type")
            if mtype != "user_text":
                await ws.send_json({"type": "error", "message": f"unknown type {mtype}"})
                continue
            user_text = msg.get("text", "")

            result: TurnResult | None = None
            async with sessionmaker()() as session:
                async with session.begin():
                    await _set_pg_user(session, user_id)
                    async for event in orchestrator.step(session, user_text):
                        if isinstance(event, TextDelta):
                            await ws.send_json(
                                {"type": "assistant_text_delta", "text": event.text}
                            )
                        else:
                            result = event

            assert result is not None  # orchestrator always yields a final TurnResult
            await ws.send_json(
                {"type": "draft_state", "stack": result.stack_payload}
            )
            for fb_id in result.submitted_feedback_ids:
                await ws.send_json({"type": "submitted", "feedback_id": str(fb_id)})
            await ws.send_json(
                {"type": "assistant_text", "text": result.assistant_text}
            )
    except WebSocketDisconnect:
        # Keep the orchestrator alive in case the client reconnects with the
        # same conversation_id. v1 will TTL or persist this.
        logger.info("provider WS disconnected for convo %s", convo_id)
    except Exception:
        logger.exception("provider WS error")
        drop(convo_id)
        try:
            await ws.close()
        except RuntimeError:
            pass
