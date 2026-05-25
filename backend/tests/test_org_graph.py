"""Integration tests for app.org_graph (DB-dependent, testcontainers).

The provider uses org_graph to resolve self-referential phrases like
"my manager" or "my direct reports"; the recipient uses it to expand
"Priya's reports". Each relation has its own SQL, including a recursive
CTE for manager_chain and a closure-table read for all_reports — worth
pinning all four plus the org-scoping guard against cross-tenant leaks.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import org_graph
from app.closure import recompute
from app.models import Org, User


async def _build_tree(session: AsyncSession) -> dict[str, Any]:
    """Build: CEO ── VP ── Manager ── IC1
                           └─ IC2
                    └─ Manager2 (no reports)
    plus a sibling-VP-with-no-reports off the CEO.

    Emails are uniquified per call so successive tests sharing the
    session-scoped Postgres don't collide on the users.email unique index.
    """
    tag = uuid.uuid4().hex[:8]
    org = Org(name=f"OrgGraphTest-{tag}")
    session.add(org)
    await session.flush()

    ceo = User(org_id=org.id, name="Cee Eeo", email=f"ceo-{tag}@ogt.test")
    session.add(ceo)
    await session.flush()
    vp = User(org_id=org.id, name="Vee Pee", email=f"vp-{tag}@ogt.test", manager_id=ceo.id)
    sibling_vp = User(
        org_id=org.id, name="Sibling Vp", email=f"svp-{tag}@ogt.test", manager_id=ceo.id
    )
    session.add_all([vp, sibling_vp])
    await session.flush()
    manager = User(org_id=org.id, name="Mgr One", email=f"m1-{tag}@ogt.test", manager_id=vp.id)
    manager2 = User(org_id=org.id, name="Mgr Two", email=f"m2-{tag}@ogt.test", manager_id=vp.id)
    session.add_all([manager, manager2])
    await session.flush()
    ic1 = User(org_id=org.id, name="Ic One", email=f"ic1-{tag}@ogt.test", manager_id=manager.id)
    ic2 = User(org_id=org.id, name="Ic Two", email=f"ic2-{tag}@ogt.test", manager_id=manager.id)
    session.add_all([ic1, ic2])
    await session.flush()
    await session.commit()
    await recompute(session)
    return {
        "org": org,
        "ceo": ceo,
        "vp": vp,
        "sibling_vp": sibling_vp,
        "manager": manager,
        "manager2": manager2,
        "ic1": ic1,
        "ic2": ic2,
    }


@pytest.mark.asyncio
async def test_manager_returns_direct_manager(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        t = await _build_tree(session)

    async with session_factory() as session:
        out = await org_graph.query(
            session, user_id=t["ic1"].id, relation="manager", org_id=t["org"].id
        )
        assert [r["id"] for r in out] == [str(t["manager"].id)]

    async with session_factory() as session:
        # CEO has no manager — zero rows, not an error.
        out = await org_graph.query(
            session, user_id=t["ceo"].id, relation="manager", org_id=t["org"].id
        )
        assert out == []


@pytest.mark.asyncio
async def test_manager_chain_walks_up_closest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        t = await _build_tree(session)

    async with session_factory() as session:
        out = await org_graph.query(
            session, user_id=t["ic1"].id, relation="manager_chain", org_id=t["org"].id
        )
        # IC1's chain: Mgr One → Vee Pee → Cee Eeo. Order matters (closest first).
        assert [r["id"] for r in out] == [
            str(t["manager"].id),
            str(t["vp"].id),
            str(t["ceo"].id),
        ]


@pytest.mark.asyncio
async def test_direct_reports_returns_only_immediate_reports(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        t = await _build_tree(session)

    async with session_factory() as session:
        out = await org_graph.query(
            session, user_id=t["vp"].id, relation="direct_reports", org_id=t["org"].id
        )
        # VP's direct reports are the two managers — NOT the ICs.
        assert {r["id"] for r in out} == {str(t["manager"].id), str(t["manager2"].id)}

    async with session_factory() as session:
        # Leaf user has no reports.
        out = await org_graph.query(
            session, user_id=t["ic1"].id, relation="direct_reports", org_id=t["org"].id
        )
        assert out == []


@pytest.mark.asyncio
async def test_all_reports_is_transitive_and_excludes_self(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        t = await _build_tree(session)

    async with session_factory() as session:
        out = await org_graph.query(
            session, user_id=t["vp"].id, relation="all_reports", org_id=t["org"].id
        )
        # VP's transitive subordinates: the two managers AND both ICs.
        # Critically: NOT the VP themselves.
        assert {r["id"] for r in out} == {
            str(t["manager"].id),
            str(t["manager2"].id),
            str(t["ic1"].id),
            str(t["ic2"].id),
        }
        assert str(t["vp"].id) not in {r["id"] for r in out}


@pytest.mark.asyncio
async def test_org_scoping_prevents_cross_tenant_leaks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The org_id filter is the load-bearing tenant boundary — feed in a
    user_id from a different org and the query must return zero rows
    even though the user exists."""
    async with session_factory() as session:
        t = await _build_tree(session)
        other = Org(name="OtherTenant")
        session.add(other)
        await session.flush()
        await session.commit()

    async with session_factory() as session:
        # Real user, real relation, wrong org → empty.
        out = await org_graph.query(
            session,
            user_id=t["ic1"].id,
            relation="manager_chain",
            org_id=t["org"].id,
        )
        assert len(out) == 3  # sanity: correct org returns the chain

        out = await org_graph.query(
            session,
            user_id=t["ic1"].id,
            relation="manager_chain",
            org_id=uuid.uuid4(),  # nonexistent org
        )
        assert out == []


@pytest.mark.asyncio
async def test_unknown_relation_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        t = await _build_tree(session)
        with pytest.raises(ValueError, match="unknown relation"):
            await org_graph.query(
                session, user_id=t["ic1"].id, relation="cousins", org_id=t["org"].id
            )
