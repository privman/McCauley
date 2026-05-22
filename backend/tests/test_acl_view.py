"""Integration test for feedback_visible_to_me (design.md §4.3).

Seeds a small org, submits feedback, and asserts each user sees exactly
the records they should. This is the load-bearing correctness check
called out in v0.1-scope.md ("everything else is testable manually for
v0.1").

Skipped if testcontainers isn't installed.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.closure import recompute
from app.models import (
    Feedback,
    FeedbackStatus,
    Org,
    OrgUnit,
    SubjectKind,
    User,
)


async def _set_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(text(f"SET LOCAL app.current_user_id = '{user_id}'"))


async def _visible_ids(session: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    async with session.begin():
        await _set_user(session, user_id)
        rows = (
            await session.execute(text("SELECT id FROM feedback_visible_to_me"))
        ).scalars().all()
        return set(rows)


@pytest.mark.asyncio
async def test_acl_view_respects_closures(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Build: CEO ── VP ── IC, plus a sibling VP/IC. Submit feedback about
    each user and the IC's unit; assert every user sees exactly what they're
    entitled to.
    """
    async with session_factory() as session:
        org = Org(name="ACLTest")
        session.add(org)
        await session.flush()

        ceo = User(org_id=org.id, name="CEO", email="ceo@t.test")
        session.add(ceo)
        await session.flush()
        vp_a = User(org_id=org.id, name="VP A", email="vpa@t.test", manager_id=ceo.id)
        vp_b = User(org_id=org.id, name="VP B", email="vpb@t.test", manager_id=ceo.id)
        session.add_all([vp_a, vp_b])
        await session.flush()
        ic_a = User(org_id=org.id, name="IC A", email="ica@t.test", manager_id=vp_a.id)
        ic_b = User(org_id=org.id, name="IC B", email="icb@t.test", manager_id=vp_b.id)
        session.add_all([ic_a, ic_b])
        await session.flush()

        # Org units: a root, plus a unit headed by vp_a.
        root = OrgUnit(org_id=org.id, name="Root", head_user_id=ceo.id)
        session.add(root)
        await session.flush()
        team_a = OrgUnit(
            org_id=org.id, name="Team A", parent_unit_id=root.id, head_user_id=vp_a.id
        )
        team_b = OrgUnit(
            org_id=org.id, name="Team B", parent_unit_id=root.id, head_user_id=vp_b.id
        )
        session.add_all([team_a, team_b])
        await session.flush()
        await session.commit()

        await recompute(session)

        # Submit feedback: about ic_a (user), about team_a (unit), about root (unit).
        fb_ic_a = Feedback(
            org_id=org.id,
            subject_kind=SubjectKind.user,
            subject_user_id=ic_a.id,
            headline="About IC A",
            status=FeedbackStatus.submitted,
        )
        fb_team_a = Feedback(
            org_id=org.id,
            subject_kind=SubjectKind.unit,
            subject_unit_id=team_a.id,
            headline="About Team A",
            status=FeedbackStatus.submitted,
        )
        fb_root = Feedback(
            org_id=org.id,
            subject_kind=SubjectKind.unit,
            subject_unit_id=root.id,
            headline="About the whole org",
            status=FeedbackStatus.submitted,
        )
        # A draft about ic_a — should never be visible.
        fb_draft = Feedback(
            org_id=org.id,
            subject_kind=SubjectKind.user,
            subject_user_id=ic_a.id,
            headline="Draft about IC A",
            status=FeedbackStatus.draft,
        )
        session.add_all([fb_ic_a, fb_team_a, fb_root, fb_draft])
        await session.commit()

    # Each scenario uses a fresh session.
    async with session_factory() as session:
        # IC A: sees own feedback only.
        assert await _visible_ids(session, ic_a.id) == {fb_ic_a.id}

    async with session_factory() as session:
        # IC B: sees nothing (no feedback about them or their chain).
        assert await _visible_ids(session, ic_b.id) == set()

    async with session_factory() as session:
        # VP A: sees feedback about IC A (chain) and Team A (heads it).
        assert await _visible_ids(session, vp_a.id) == {fb_ic_a.id, fb_team_a.id}

    async with session_factory() as session:
        # VP B: sees nothing — doesn't manage IC A, doesn't head Team A or root.
        assert await _visible_ids(session, vp_b.id) == set()

    async with session_factory() as session:
        # CEO: sees everything submitted (manager of both VPs, head of root unit).
        assert await _visible_ids(session, ceo.id) == {fb_ic_a.id, fb_team_a.id, fb_root.id}
        # And critically the draft is NOT visible even to CEO.
        assert fb_draft.id not in await _visible_ids(session, ceo.id)
