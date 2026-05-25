"""Unit tests for the date_range bound parser used by recipient orchestrator.

The model emits dates as either bare YYYY-MM-DD or a full ISO-8601
timestamp, and we need to (a) handle both, (b) make date-only upper
bounds inclusive of the named day, and (c) reject garbage instead of
raising.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.recipient.orchestrator import _parse_iso_datetime


@pytest.mark.parametrize(
    "value, end_of_day, expected",
    [
        # bare date, lower bound — start of day in UTC
        ("2026-05-01", False, datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)),
        # bare date, upper bound — pushed to end of day so the range is inclusive
        (
            "2026-05-01",
            True,
            datetime(2026, 5, 1, 23, 59, 59, 999999, tzinfo=UTC),
        ),
        # full ISO with explicit tz — preserved as-is
        (
            "2026-05-01T12:34:56+00:00",
            False,
            datetime(2026, 5, 1, 12, 34, 56, tzinfo=UTC),
        ),
        # full ISO without tz — assumed UTC, NOT pushed to end-of-day even with the flag
        # (only bare YYYY-MM-DD gets the end-of-day treatment, because a caller who
        # provided an explicit time meant it)
        (
            "2026-05-01T12:34:56",
            True,
            datetime(2026, 5, 1, 12, 34, 56, tzinfo=UTC),
        ),
        # None and empty string both yield None — the agent omitted that bound
        (None, False, None),
        ("", False, None),
        (None, True, None),
        # Garbage shouldn't crash the turn — return None and let the caller decide
        ("not-a-date", False, None),
        ("2026-13-99", False, None),
    ],
)
def test_parse_iso_datetime(value: str | None, end_of_day: bool, expected: datetime | None) -> None:
    assert _parse_iso_datetime(value, end_of_day=end_of_day) == expected
