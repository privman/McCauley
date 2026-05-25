"""Recompute org_subordinates and unit_oversight from the org graph.

These are the access closures from design.md §4.3. v0.1 does a full rebuild;
v1 will rebuild incrementally on `users.manager_id` and `org_units` changes.
The function signature stays the same in v1.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrgUnit, User


@dataclass(frozen=True)
class _UserNode:
    id: uuid.UUID
    manager_id: uuid.UUID | None


@dataclass(frozen=True)
class _UnitNode:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    head_user_id: uuid.UUID | None


def compute_org_subordinates(
    users: list[_UserNode],
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """Transitive closure of the manager tree, including self-pairs.

    Returns the set of (ancestor_user_id, descendant_user_id). Detects cycles
    and refuses to follow them (a manager cycle is malformed input).
    """
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    by_id = {u.id: u for u in users}

    for user in users:
        # walk up from `user` collecting ancestors; user is their own ancestor.
        visited: set[uuid.UUID] = set()
        cursor: uuid.UUID | None = user.id
        while cursor is not None:
            if cursor in visited:
                raise ValueError(f"cycle in manager chain at user {cursor}")
            visited.add(cursor)
            pairs.add((cursor, user.id))
            node = by_id.get(cursor)
            cursor = node.manager_id if node else None

    return pairs


def compute_unit_oversight(
    units: list[_UnitNode],
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """For each unit, the heads of that unit and every ancestor unit oversee it.

    Returns the set of (user_id, unit_id). Cycles in parent_unit_id raise.
    """
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    by_id = {u.id: u for u in units}

    for unit in units:
        visited: set[uuid.UUID] = set()
        cursor: uuid.UUID | None = unit.id
        while cursor is not None:
            if cursor in visited:
                raise ValueError(f"cycle in unit parent chain at unit {cursor}")
            visited.add(cursor)
            node = by_id.get(cursor)
            if node is None:
                break
            if node.head_user_id is not None:
                pairs.add((node.head_user_id, unit.id))
            cursor = node.parent_id

    return pairs


async def recompute(session: AsyncSession) -> tuple[int, int]:
    """Full rebuild of both closure tables. Returns (subordinate_rows, oversight_rows)."""
    user_rows = (await session.execute(select(User.id, User.manager_id))).all()
    unit_rows = (
        await session.execute(select(OrgUnit.id, OrgUnit.parent_unit_id, OrgUnit.head_user_id))
    ).all()

    users = [_UserNode(id=r[0], manager_id=r[1]) for r in user_rows]
    units = [_UnitNode(id=r[0], parent_id=r[1], head_user_id=r[2]) for r in unit_rows]

    subs = compute_org_subordinates(users)
    over = compute_unit_oversight(units)

    await session.execute(text("TRUNCATE org_subordinates, unit_oversight"))

    if subs:
        await session.execute(
            text(
                "INSERT INTO org_subordinates (ancestor_user_id, descendant_user_id) "
                "VALUES " + ", ".join(f"(:a{i}, :d{i})" for i in range(len(subs)))
            ),
            {f"a{i}": a for i, (a, _) in enumerate(subs)}
            | {f"d{i}": d for i, (_, d) in enumerate(subs)},
        )
    if over:
        await session.execute(
            text(
                "INSERT INTO unit_oversight (user_id, unit_id) "
                "VALUES " + ", ".join(f"(:u{i}, :n{i})" for i in range(len(over)))
            ),
            {f"u{i}": u for i, (u, _) in enumerate(over)}
            | {f"n{i}": n for i, (_, n) in enumerate(over)},
        )
    await session.commit()
    return (len(subs), len(over))
