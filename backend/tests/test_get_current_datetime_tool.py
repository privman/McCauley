"""Unit tests for the get_current_datetime tool.

Both orchestrators expose the same tool so the model can anchor
relative time expressions ("last week", "the last 90 days") to the
real current date instead of its training cutoff. The handler itself
is trivial — these tests just pin its shape and presence in both
tool_defs lists, so a refactor can't silently drop the tool or change
the payload shape the system prompt promises.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.current_user import UserProfile
from app.provider.orchestrator import ProviderConversation
from app.provider.orchestrator import _tool_defs as provider_tool_defs
from app.recipient.orchestrator import RecipientConversation
from app.recipient.orchestrator import _tool_defs as recipient_tool_defs


def _profile() -> UserProfile:
    return UserProfile(
        user_id=uuid.uuid4(),
        name="Test User",
        title=None,
        manager_name=None,
        units_overseen=[],
    )


def _recipient_conv() -> RecipientConversation:
    return RecipientConversation(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        current_user=_profile(),
    )


def _provider_conv() -> ProviderConversation:
    return ProviderConversation(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        current_user=_profile(),
    )


def test_tool_def_present_in_recipient() -> None:
    names = [t["name"] for t in recipient_tool_defs()]
    assert "get_current_datetime" in names


def test_tool_def_present_in_provider() -> None:
    names = [t["name"] for t in provider_tool_defs()]
    assert "get_current_datetime" in names


def _assert_payload_is_current(payload: dict[str, object]) -> None:
    """The payload must (a) carry the three keys the system prompt
    promises, (b) parse back to a UTC datetime within a couple of
    seconds of `now`, and (c) name the right weekday."""
    assert set(payload.keys()) == {"datetime_utc", "weekday", "timezone"}
    assert payload["timezone"] == "UTC"

    before = datetime.now(UTC)
    parsed = datetime.fromisoformat(cast(str, payload["datetime_utc"]))
    after = datetime.now(UTC)
    # The handler was called fractionally before this assertion, so
    # `parsed` must sit in [before - small slack, after].
    slack = 2  # seconds
    assert (before.timestamp() - slack) <= parsed.timestamp() <= after.timestamp()
    assert parsed.tzinfo is not None
    assert parsed.strftime("%A") == payload["weekday"]


@pytest.mark.asyncio
async def test_recipient_handler_returns_current_utc_datetime() -> None:
    """The handler doesn't touch the session for this tool, so a None
    cast through the type is enough — no DB fixture needed."""
    conv = _recipient_conv()
    result, sources = await conv.handle_tool(cast(AsyncSession, None), "get_current_datetime", {})
    assert sources == []
    _assert_payload_is_current(result)


@pytest.mark.asyncio
async def test_provider_handler_returns_current_utc_datetime() -> None:
    conv = _provider_conv()
    result, submitted_id = await conv.handle_tool(
        cast(AsyncSession, None), "get_current_datetime", {}
    )
    assert submitted_id is None
    _assert_payload_is_current(cast(dict[str, object], result))
