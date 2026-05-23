"""Identity of the user driving a conversation.

Both orchestrators receive a ViewerProfile so the model can ground
self-referential phrases like "me", "my team", or "feedback about myself"
without asking the user to repeat their user_id or unit names.

The profile is built once at WebSocket connect time and frozen for the
lifetime of the orchestrator — manager/unit changes mid-conversation are
out of scope for v0.1.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrgUnit, UnitOversight, User


@dataclass(frozen=True)
class HeadedUnit:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class ViewerProfile:
    user_id: uuid.UUID
    name: str
    title: str | None
    manager_name: str | None
    units_overseen: list[HeadedUnit] = field(default_factory=list)

    def prompt_block(self) -> str:
        """Render as a labelled block for inclusion in a system prompt."""
        lines = [
            "You are talking with:",
            f"- Name: {self.name}",
            f"- user_id: {self.user_id}",
        ]
        if self.title:
            lines.append(f"- Title: {self.title}")
        if self.manager_name:
            lines.append(f"- Manager: {self.manager_name}")
        if self.units_overseen:
            unit_lines = ", ".join(f"{u.name} (id={u.id})" for u in self.units_overseen)
            lines.append(f"- Oversees units: {unit_lines}")
        else:
            lines.append("- Oversees units: (none)")
        return "\n".join(lines)


async def load_viewer(session: AsyncSession, user_id: uuid.UUID) -> ViewerProfile:
    """Fetch the viewer's identity context in one shot."""
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")

    manager_name: str | None = None
    if user.manager_id is not None:
        manager = await session.get(User, user.manager_id)
        manager_name = manager.name if manager else None

    unit_rows = (
        await session.execute(
            select(OrgUnit.id, OrgUnit.name)
            .join(UnitOversight, UnitOversight.unit_id == OrgUnit.id)
            .where(UnitOversight.user_id == user_id)
            .order_by(OrgUnit.name)
        )
    ).all()
    units = [HeadedUnit(id=r[0], name=r[1]) for r in unit_rows]

    return ViewerProfile(
        user_id=user.id,
        name=user.name,
        title=user.title,
        manager_name=manager_name,
        units_overseen=units,
    )
