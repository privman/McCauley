"""Thin async wrappers around the Anthropic SDK.

Two helpers only:

- `sonnet_message(...)` for multi-turn tool-using orchestration (provider
  and recipient modes).
- `haiku_classify(...)` for cheap structured single-shot extraction
  (sentiment + topic tagging at submit time).

We do not hide the SDK's message shapes; callers build standard message
lists. We only centralize the model IDs (from settings) and the async
adapter (the SDK's async client is fine; this just makes typing easier
and gives us a single seam to wrap for prompt caching, logging, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam, ToolParam

from app.settings import get_settings

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


async def sonnet_message(
    *,
    system: str,
    messages: list[MessageParam],
    tools: list[ToolParam] | None = None,
    max_tokens: int = 1024,
) -> Message:
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "model": settings.sonnet_model,
        "system": system,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    return await client().messages.create(**kwargs)


def sonnet_stream(
    *,
    system: str,
    messages: list[MessageParam],
    tools: list[ToolParam] | None = None,
    max_tokens: int = 1024,
) -> Any:
    """Return the SDK's stream() async context manager pre-configured for Sonnet.

    Use as:
        async with sonnet_stream(...) as stream:
            async for event in stream:
                ...
            final = await stream.get_final_message()
    """
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "model": settings.sonnet_model,
        "system": system,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    return client().messages.stream(**kwargs)


async def haiku_classify(
    *,
    system: str,
    user_text: str,
    json_schema_hint: str,
    max_tokens: int = 256,
) -> dict[str, Any]:
    """Single-shot classification: ask Haiku for a JSON object, parse it.

    json_schema_hint is described in the prompt; we don't use the tool API
    here because we don't need it and it's cheaper as a plain message.
    """
    settings = get_settings()
    full_system = (
        system
        + "\n\nRespond with a single JSON object only — no prose, no code fences. "
        + "Shape: "
        + json_schema_hint
    )
    msg = await client().messages.create(
        model=settings.haiku_model,
        system=full_system,
        messages=[{"role": "user", "content": user_text}],
        max_tokens=max_tokens,
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    # Tolerate fenced output anyway.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    try:
        return cast(dict[str, Any], json.loads(raw))
    except json.JSONDecodeError as e:
        logger.warning("haiku JSON parse failed: %s — raw=%r", e, raw)
        return {}
