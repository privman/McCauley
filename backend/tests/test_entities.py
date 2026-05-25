"""Integration tests for app.entities.resolve (DB-dependent, testcontainers).

The provider orchestrator uses this to fuzzy-match the human's free-text
subject ("priya", "the mobile team") to a user or org_unit UUID. The
shortlist is pg_trgm-based, so the test needs a real Postgres with the
pg_trgm extension (set up by Alembic migrations).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.entities import resolve, to_tool_payload
from app.models import Org, OrgUnit, User


async def _seed(session: AsyncSession) -> dict[str, uuid.UUID]:
    # Uniquify identifiers so successive tests sharing the session-scoped
    # Postgres don't collide on the users.email unique index.
    tag = uuid.uuid4().hex[:8]
    org = Org(name=f"EntTest-{tag}")
    session.add(org)
    await session.flush()
    priya = User(org_id=org.id, name="Priya Singh", title="Engineer", email=f"p-{tag}@e.test")
    omar = User(org_id=org.id, name="Omar Hassan", title="Manager", email=f"o-{tag}@e.test")
    inactive = User(
        org_id=org.id,
        name="Priya Old",
        email=f"po-{tag}@e.test",
        active=False,
    )
    session.add_all([priya, omar, inactive])
    await session.flush()
    priya.manager_id = omar.id
    await session.flush()
    mobile = OrgUnit(org_id=org.id, name="Mobile Team", head_user_id=omar.id)
    platform = OrgUnit(org_id=org.id, name="Platform Engineering", head_user_id=None)
    session.add_all([mobile, platform])
    await session.flush()
    await session.commit()
    return {
        "org_id": org.id,
        "priya": priya.id,
        "omar": omar.id,
        "inactive": inactive.id,
        "mobile": mobile.id,
        "platform": platform.id,
    }


@pytest.mark.asyncio
async def test_resolve_user_by_first_name(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed(session)

    async with session_factory() as session:
        cands = await resolve(session, "Priya", kind="user", org_id=ids["org_id"])
        # Priya Singh should be the top hit; the inactive "Priya Old" is excluded.
        assert cands[0].id == ids["priya"]
        assert all(c.id != ids["inactive"] for c in cands)
        # manager_name hint surfaces so the model can disambiguate same-name people.
        top = cands[0]
        assert top.manager_name == "Omar Hassan"
        assert top.title == "Engineer"
        assert top.kind == "user"


@pytest.mark.asyncio
async def test_resolve_unit_returns_head_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """head_user_id lets the agent chain into org_graph(all_reports) to
    enumerate the unit's transitive members."""
    async with session_factory() as session:
        ids = await _seed(session)

    async with session_factory() as session:
        cands = await resolve(session, "Mobile", kind="unit", org_id=ids["org_id"])
        assert cands[0].id == ids["mobile"]
        assert cands[0].kind == "unit"
        assert cands[0].head_user_id == ids["omar"]

    async with session_factory() as session:
        # Unit with no head — head_user_id is None, not a fabricated value.
        cands = await resolve(session, "Platform", kind="unit", org_id=ids["org_id"])
        assert cands[0].id == ids["platform"]
        assert cands[0].head_user_id is None


@pytest.mark.asyncio
async def test_resolve_kind_filter_excludes_other_kind(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """If the agent says kind=user, units must not appear and vice versa,
    even when the query string would fuzzy-match both."""
    async with session_factory() as session:
        ids = await _seed(session)
        # Add a user whose name overlaps with a unit name. Uniquify the
        # email — other tests may have inserted "mb@e.test" already.
        extra = User(
            org_id=ids["org_id"], name="Mobile Bob", email=f"mb-{uuid.uuid4().hex[:8]}@e.test"
        )
        session.add(extra)
        await session.commit()

    async with session_factory() as session:
        users_only = await resolve(session, "Mobile", kind="user", org_id=ids["org_id"])
        assert all(c.kind == "user" for c in users_only)
        units_only = await resolve(session, "Mobile", kind="unit", org_id=ids["org_id"])
        assert all(c.kind == "unit" for c in units_only)
        # kind="any" surfaces both.
        any_kind = await resolve(session, "Mobile", kind="any", org_id=ids["org_id"])
        kinds = {c.kind for c in any_kind}
        assert kinds == {"user", "unit"}


@pytest.mark.asyncio
async def test_resolve_org_scoping(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A second tenant's user with the same name must not surface — the
    org_id filter is the only thing standing between providers and
    cross-tenant name leakage."""
    async with session_factory() as session:
        ids = await _seed(session)
        other = Org(name="OtherTenant")
        session.add(other)
        await session.flush()
        other_priya = User(
            org_id=other.id,
            name="Priya Singh",
            email=f"op-{uuid.uuid4().hex[:8]}@e.test",
            title="Other Tenant Eng",
        )
        session.add(other_priya)
        await session.commit()
        other_priya_id = other_priya.id

    async with session_factory() as session:
        cands = await resolve(session, "Priya Singh", kind="user", org_id=ids["org_id"])
        ids_found = {c.id for c in cands}
        assert ids["priya"] in ids_found
        assert other_priya_id not in ids_found


@pytest.mark.asyncio
async def test_resolve_no_match_returns_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed(session)

    async with session_factory() as session:
        # Query well below pg_trgm similarity threshold for any seeded name.
        cands = await resolve(session, "xqz-nonexistent-name", kind="any", org_id=ids["org_id"])
        assert cands == []


@pytest.mark.asyncio
async def test_resolve_limit_caps_result_count(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed(session)
        suffix = uuid.uuid4().hex[:8]
        for i in range(8):
            session.add(
                User(
                    org_id=ids["org_id"],
                    name=f"Priya Number{i:02d}",
                    email=f"pn{i}-{suffix}@e.test",
                )
            )
        await session.commit()

    async with session_factory() as session:
        cands = await resolve(session, "Priya", kind="user", org_id=ids["org_id"], limit=3)
        assert len(cands) == 3


def test_to_tool_payload_shapes_for_llm() -> None:
    """The payload omits empty fields and stringifies UUIDs — the LLM
    can't pass uuid.UUID objects back as tool input."""
    from app.entities import EntityCandidate

    user_id = uuid.uuid4()
    head_id = uuid.uuid4()
    payload = to_tool_payload(
        [
            EntityCandidate(id=user_id, kind="user", name="Anna", title="Eng"),
            EntityCandidate(id=uuid.uuid4(), kind="unit", name="Team", head_user_id=head_id),
            # Bare candidate with no hints — only id/kind/name appear.
            EntityCandidate(id=uuid.uuid4(), kind="user", name="Bo"),
        ]
    )
    assert payload[0] == {"id": str(user_id), "kind": "user", "name": "Anna", "title": "Eng"}
    assert payload[1]["head_user_id"] == str(head_id)
    assert payload[2].keys() == {"id", "kind", "name"}
