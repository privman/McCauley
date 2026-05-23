"""Recipient WebSocket endpoint.

Same shape as the provider WS: {"type": "user_text", "text": "..."} in,
{"type": "assistant_text" | "sources"} out. The ACL is enforced by SET
LOCAL app.current_user_id on every turn.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Cookie, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import text as sql_text

from app.auth import COOKIE_NAME, _user_id_from_cookie
from app.current_user import load_current_user
from app.db import sessionmaker
from app.models import Conversation, User
from app.recipient.orchestrator import (
    RecipientTurnResult,
    TextDelta,
    drop,
    get_or_create,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["recipient"])


@router.websocket("/recipient")
async def recipient_ws(
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
            convo = Conversation(org_id=org_id, user_id=user.id, mode="recipient")
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
            if msg.get("type") != "user_text":
                await ws.send_json({"type": "error", "message": "unknown type"})
                continue
            user_text = msg.get("text", "")

            result: RecipientTurnResult | None = None
            async with sessionmaker()() as session:
                async with session.begin():
                    await session.execute(
                        sql_text(f"SET LOCAL app.current_user_id = '{user_id}'")
                    )
                    async for event in orchestrator.step(session, user_text):
                        if isinstance(event, TextDelta):
                            await ws.send_json(
                                {"type": "assistant_text_delta", "text": event.text}
                            )
                        else:
                            result = event

            assert result is not None
            if result.sources:
                await ws.send_json({"type": "sources", "items": result.sources})
            await ws.send_json(
                {"type": "assistant_text", "text": result.assistant_text}
            )
    except WebSocketDisconnect:
        logger.info("recipient WS disconnected for convo %s", convo_id)
    except Exception:
        logger.exception("recipient WS error")
        drop(convo_id)
        try:
            await ws.close()
        except RuntimeError:
            pass
