"""Entity resolver for the provider conversation.

Two-stage:

1. **Shortlist** in Postgres using pg_trgm fuzzy match on name. Cheap, no
   LLM call. Returns ranked candidates with hints (title, manager name,
   unit name) the model needs for disambiguation.
2. **Tie-break** is the LLM's job — the orchestrator passes the candidates
   and the conversation context back to Sonnet, which either picks one or
   asks the user to disambiguate on the same turn (design.md §5).

For v0.1 we do not run a separate Haiku ranker pass — Sonnet picks from
the shortlist inline. The function below only does the SQL shortlist.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class EntityCandidate:
    id: uuid.UUID
    kind: str  # "user" | "unit"
    name: str
    title: str | None = None
    manager_name: str | None = None
    unit_name: str | None = None
    head_user_id: uuid.UUID | None = None  # for kind="unit" only


SIMILARITY_THRESHOLD = 0.2  # pg_trgm default is 0.3; we widen for short queries


async def resolve(
    session: AsyncSession,
    query: str,
    *,
    kind: str = "any",
    org_id: uuid.UUID | None = None,
    limit: int = 5,
) -> list[EntityCandidate]:
    """Fuzzy match against users and/or org_units.

    kind: "user" | "unit" | "any". Returns up to `limit` candidates ranked by
    pg_trgm similarity, with hints to help the model disambiguate.
    """
    candidates: list[EntityCandidate] = []

    if kind in ("user", "any"):
        rows = (
            await session.execute(
                text(
                    """
                    SELECT u.id, u.name, u.title, m.name AS manager_name,
                           similarity(u.name, :q) AS s
                    FROM users u
                    LEFT JOIN users m ON m.id = u.manager_id
                    WHERE u.active
                      AND (CAST(:org AS uuid) IS NULL OR u.org_id = CAST(:org AS uuid))
                      AND similarity(u.name, :q) >= :threshold
                    ORDER BY s DESC
                    LIMIT :limit
                    """
                ),
                {
                    "q": query,
                    "org": org_id,
                    "threshold": SIMILARITY_THRESHOLD,
                    "limit": limit,
                },
            )
        ).all()
        for r in rows:
            candidates.append(
                EntityCandidate(
                    id=r.id,
                    kind="user",
                    name=r.name,
                    title=r.title,
                    manager_name=r.manager_name,
                )
            )

    if kind in ("unit", "any"):
        rows = (
            await session.execute(
                text(
                    """
                    SELECT ou.id, ou.name, ou.head_user_id,
                           h.name AS head_name,
                           similarity(ou.name, :q) AS s
                    FROM org_units ou
                    LEFT JOIN users h ON h.id = ou.head_user_id
                    WHERE (CAST(:org AS uuid) IS NULL OR ou.org_id = CAST(:org AS uuid))
                      AND similarity(ou.name, :q) >= :threshold
                    ORDER BY s DESC
                    LIMIT :limit
                    """
                ),
                {
                    "q": query,
                    "org": org_id,
                    "threshold": SIMILARITY_THRESHOLD,
                    "limit": limit,
                },
            )
        ).all()
        for r in rows:
            candidates.append(
                EntityCandidate(
                    id=r.id,
                    kind="unit",
                    name=r.name,
                    title=f"unit (head: {r.head_name})" if r.head_name else "unit",
                    head_user_id=r.head_user_id,
                )
            )

    return candidates[:limit]


def to_tool_payload(candidates: list[EntityCandidate]) -> list[dict[str, str]]:
    """Shape candidates as a JSON-safe list the LLM can consume directly."""
    out: list[dict[str, str]] = []
    for c in candidates:
        item = {"id": str(c.id), "kind": c.kind, "name": c.name}
        if c.title:
            item["title"] = c.title
        if c.manager_name:
            item["manager"] = c.manager_name
        if c.head_user_id:
            # Lets the agent chain into org_graph(head_user_id, "all_reports")
            # to get the unit's transitive members — there's no direct
            # user_unit membership table; membership is implicit via reporting.
            item["head_user_id"] = str(c.head_user_id)
        out.append(item)
    return out
