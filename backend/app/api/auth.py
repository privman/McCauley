"""Login-as endpoints and /me. Demo-only auth (see v0.1-scope.md)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import CurrentUser, clear_session_cookie, issue_session_cookie
from app.db import SessionDep
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class UserSummary(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    title: str | None


class LoginRequest(BaseModel):
    user_id: uuid.UUID


@router.get("/users", response_model=list[UserSummary])
async def list_users(session: SessionDep) -> list[UserSummary]:
    """Lists all seeded users so the frontend can render the picker."""
    rows = (
        (await session.execute(select(User).where(User.active).order_by(User.name))).scalars().all()
    )
    return [UserSummary(id=u.id, name=u.name, email=u.email, title=u.title) for u in rows]


@router.post("/login", response_model=UserSummary)
async def login(req: LoginRequest, response: Response, session: SessionDep) -> UserSummary:
    user = (
        await session.execute(select(User).where(User.id == req.user_id, User.active))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    issue_session_cookie(response, user.id)
    return UserSummary(id=user.id, name=user.name, email=user.email, title=user.title)


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserSummary)
async def me(user: CurrentUser) -> UserSummary:
    return UserSummary(id=user.id, name=user.name, email=user.email, title=user.title)
