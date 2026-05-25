"""Unit tests for history compaction (`stub_old_tool_results`).

Search and report results dominate per-turn input cost; the helper
overwrites old tool_result payloads with a tiny constant, walking
back-to-front so the most recent `keep` blocks survive.
"""

from __future__ import annotations

import json
from typing import Any, cast

from anthropic.types import MessageParam

from app.llm import stub_old_tool_results

_STUB = json.dumps({"omitted": True, "note": "earlier tool result removed to fit context"})


def _user_tool_result(tool_use_id: str, content: str) -> MessageParam:
    return cast(
        MessageParam,
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                }
            ],
        },
    )


def _assistant_text(text: str) -> MessageParam:
    return cast(
        MessageParam,
        {"role": "assistant", "content": [{"type": "text", "text": text}]},
    )


def _tool_result_contents(history: list[MessageParam]) -> list[str]:
    """Pull out the `content` of every tool_result block in order."""
    out: list[str] = []
    for msg in history:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                out.append(cast(str, block.get("content")))
    return out


def test_empty_history_is_noop() -> None:
    history: list[MessageParam] = []
    stub_old_tool_results(history, keep=2)
    assert history == []


def test_history_without_tool_results_is_untouched() -> None:
    history: list[MessageParam] = [
        cast(MessageParam, {"role": "user", "content": "hi"}),
        _assistant_text("hello back"),
    ]
    before = [dict(m) for m in history]
    stub_old_tool_results(history, keep=2)
    assert history == before


def test_keep_zero_stubs_everything() -> None:
    history: list[MessageParam] = [
        _user_tool_result("a", "first result body"),
        _assistant_text("ok"),
        _user_tool_result("b", "second result body"),
        _assistant_text("ok"),
        _user_tool_result("c", "third result body"),
    ]
    stub_old_tool_results(history, keep=0)
    assert _tool_result_contents(history) == [_STUB, _STUB, _STUB]


def test_keep_n_preserves_n_most_recent() -> None:
    history: list[MessageParam] = [
        _user_tool_result("a", "OLD body"),
        _assistant_text("…"),
        _user_tool_result("b", "MIDDLE body"),
        _assistant_text("…"),
        _user_tool_result("c", "NEW body"),
    ]
    stub_old_tool_results(history, keep=2)
    # The two most recent survive; only the oldest is stubbed.
    assert _tool_result_contents(history) == [_STUB, "MIDDLE body", "NEW body"]


def test_keep_larger_than_history_preserves_all() -> None:
    history: list[MessageParam] = [
        _user_tool_result("a", "one"),
        _user_tool_result("b", "two"),
    ]
    stub_old_tool_results(history, keep=10)
    assert _tool_result_contents(history) == ["one", "two"]


def test_multiple_tool_results_per_message() -> None:
    """A single user-role turn can hold several tool_result blocks
    (parallel tool_use round); they should all be visited."""
    multi: MessageParam = cast(
        MessageParam,
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "x", "content": "X body"},
                {"type": "tool_result", "tool_use_id": "y", "content": "Y body"},
            ],
        },
    )
    history: list[MessageParam] = [
        _user_tool_result("a", "old single"),
        _assistant_text("…"),
        multi,
    ]
    stub_old_tool_results(history, keep=2)
    # `seen` counts each tool_result block, not each message — so keep=2 keeps
    # both blocks in the latest multi-result turn, stubbing the earlier one.
    assert _tool_result_contents(history) == [_STUB, "X body", "Y body"]


def test_idempotent() -> None:
    history: list[MessageParam] = [
        _user_tool_result("a", "old"),
        _user_tool_result("b", "newer"),
    ]
    stub_old_tool_results(history, keep=1)
    stub_old_tool_results(history, keep=1)
    assert _tool_result_contents(history) == [_STUB, "newer"]


def test_assistant_tool_use_blocks_are_not_touched() -> None:
    """tool_use blocks live on assistant messages; the stubber must not
    rewrite them (only tool_result on user messages)."""
    assistant_with_tool_use: MessageParam = cast(
        MessageParam,
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "calling tool"},
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "search",
                    "input": {"q": "x"},
                },
            ],
        },
    )
    history: list[MessageParam] = [
        assistant_with_tool_use,
        _user_tool_result("tu_1", "raw search payload"),
    ]
    stub_old_tool_results(history, keep=0)
    # The user's tool_result is stubbed.
    assert _tool_result_contents(history) == [_STUB]
    # The assistant's tool_use block is preserved verbatim.
    assistant_content = cast(list[dict[str, Any]], history[0]["content"])
    tool_use_block = next(b for b in assistant_content if b.get("type") == "tool_use")
    assert tool_use_block["input"] == {"q": "x"}
