"""Tests for the provider DraftStack — pivot, resume, SBI completeness."""

from __future__ import annotations

import pytest

from app.provider.state import DraftStack


def test_new_draft_becomes_current_and_paused_grows() -> None:
    stack = DraftStack()
    a = stack.new_draft()
    assert stack.current is a
    assert stack.paused == []

    b = stack.new_draft()
    assert stack.current is b
    assert stack.paused == [a]


def test_resume_swaps_paused_with_current() -> None:
    stack = DraftStack()
    a = stack.new_draft()
    b = stack.new_draft()
    # Current = b, paused = [a]. Resume a -> current = a, paused = [b].
    stack.resume(a.local_id)
    assert stack.current is a
    assert stack.paused == [b]


def test_resume_current_is_noop() -> None:
    stack = DraftStack()
    a = stack.new_draft()
    stack.resume(a.local_id)
    assert stack.current is a


def test_resume_unknown_raises() -> None:
    stack = DraftStack()
    stack.new_draft()
    with pytest.raises(KeyError):
        stack.resume("nope")


def test_sbi_completeness_gates_submit() -> None:
    stack = DraftStack()
    d = stack.new_draft()
    ok, reason = d.ready_to_submit()
    assert not ok and reason and "subject" in reason

    d.subject_kind = "user"
    import uuid

    d.subject_id = uuid.uuid4()
    d.subject_name = "X"
    d.headline = "X is great at Y"
    ok, reason = d.ready_to_submit()
    assert not ok and reason and "SBI" in reason

    sbi = d.add_sbi()
    sbi.situation = "in a meeting"
    sbi.behavior = "did X"
    sbi.impact = "improved Y"
    ok, _ = d.ready_to_submit()
    assert ok
