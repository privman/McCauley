"""Unit tests for the deterministic provider greeting.

Rendered at WS connect time without an LLM round-trip so the user sees
something immediately. The first name comes from a naive split of the
profile name — the test pins the contract.
"""

from __future__ import annotations

import uuid

import pytest

from app.current_user import UserProfile
from app.provider.orchestrator import greeting


def _profile(name: str) -> UserProfile:
    return UserProfile(
        user_id=uuid.uuid4(),
        name=name,
        title=None,
        manager_name=None,
        units_overseen=[],
    )


@pytest.mark.parametrize(
    "name, expected_addressed_as",
    [
        ("Sam Rivera", "Hi Sam,"),
        ("Priya Singh", "Hi Priya,"),
        # Single-name profile: the whole name IS the first name.
        ("Cher", "Hi Cher,"),
        # Triple-barreled: still just the first token.
        ("Maria de la Cruz", "Hi Maria,"),
        # Empty name falls back to a neutral greeting.
        ("", "Hi there,"),
    ],
)
def test_greeting_addresses_user_by_first_name(name: str, expected_addressed_as: str) -> None:
    out = greeting(_profile(name))
    assert out.startswith(expected_addressed_as)


def test_greeting_covers_the_three_things_the_user_needs_up_front() -> None:
    """The greeting is the only thing the user sees before they type, so
    it has to (1) introduce the bot, (2) warn that their name is attached
    by default, and (3) prompt for a subject. Pin all three."""
    out = greeting(_profile("Sam Rivera"))
    assert "McCauley" in out
    # Name-attached / anonymity warning — phrasing may evolve, so match a key fragment.
    assert "anonymous" in out.lower()
    # Open-ended opener that points the user at "who", not "what about".
    assert "?" in out
    assert "who" in out.lower()
