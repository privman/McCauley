"""Org-chart navigation for orchestrator tool calls.

Provider needs it to resolve self-referential phrases like "my manager"
or "my direct reports" to UUIDs. Recipient needs it for "feedback about
Priya's reports" — resolve_entity gives one id, org_graph expands it
to the relational set.

All queries are org-scoped — passing a user_id from another tenant
returns no rows (the org_id filter rejects).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


VALID_RELATIONS = ("manager", "manager_chain", "direct_reports", "all_reports")


async def query(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    relation: str,
    org_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Users related to `user_id` by `relation`, scoped to `org_id`.

    Relations:
      - manager:         direct manager (0 or 1 row).
      - manager_chain:   manager, manager's manager, ..., ordered closest first.
      - direct_reports:  users whose manager_id is this user.
      - all_reports:     transitive subordinates via org_subordinates,
                         excluding the user themselves.

    Returns: list of {id, name, title}.
    """
    if relation not in VALID_RELATIONS:
        raise ValueError(f"unknown relation {relation!r}; must be one of {list(VALID_RELATIONS)}")

    if relation == "manager":
        sql = text("""
            SELECT m.id, m.name, m.title
            FROM users u
            JOIN users m ON m.id = u.manager_id
            WHERE u.id = :uid AND u.org_id = :org AND m.org_id = :org
            """)
        rows = (await session.execute(sql, {"uid": user_id, "org": org_id})).all()

    elif relation == "manager_chain":
        # Recursive CTE walks up via manager_id. Depth cap is defensive —
        # a real org chart shouldn't be > 20 deep, 50 is generous.
        sql = text("""
            WITH RECURSIVE chain AS (
                SELECT u.manager_id AS id, 1 AS depth
                FROM users u
                WHERE u.id = :uid AND u.org_id = :org
                UNION ALL
                SELECT u.manager_id, c.depth + 1
                FROM chain c
                JOIN users u ON u.id = c.id
                WHERE u.manager_id IS NOT NULL AND c.depth < 50
            )
            SELECT m.id, m.name, m.title, c.depth
            FROM chain c
            JOIN users m ON m.id = c.id
            WHERE m.org_id = :org
            ORDER BY c.depth
            """)
        rows = (await session.execute(sql, {"uid": user_id, "org": org_id})).all()

    elif relation == "direct_reports":
        sql = text("""
            SELECT id, name, title
            FROM users
            WHERE manager_id = :uid AND org_id = :org AND active
            ORDER BY name
            """)
        rows = (await session.execute(sql, {"uid": user_id, "org": org_id})).all()

    else:  # all_reports
        sql = text("""
            SELECT u.id, u.name, u.title
            FROM org_subordinates s
            JOIN users u ON u.id = s.descendant_user_id
            WHERE s.ancestor_user_id = :uid
              AND u.org_id = :org
              AND u.active
              AND s.descendant_user_id != :uid
            ORDER BY u.name
            """)
        rows = (await session.execute(sql, {"uid": user_id, "org": org_id})).all()

    return [{"id": str(r.id), "name": r.name, "title": r.title} for r in rows]
