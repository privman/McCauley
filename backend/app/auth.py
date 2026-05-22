"""Local auth seam for v0.1 (see v0.1-scope.md "Simplifications").

The whole point of this module: every request must end up with
`app.current_user_id` set on the Postgres session via SET LOCAL — that's
what feedback_visible_to_me reads. In v1 the user comes from OIDC; in v0.1
it comes from a signed cookie set by a "log in as" form.

The cookie payload is just the user UUID. Signed with SESSION_SECRET via
itsdangerous so a malicious client can't impersonate by editing the cookie.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Response, status
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionDep
from app.models import User
from app.settings import get_settings

COOKIE_NAME = "mccauley_session"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().session_secret, salt="login-as")


def issue_session_cookie(response: Response, user_id: uuid.UUID) -> None:
    token = _serializer().dumps(str(user_id))
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",  # lax so frontend at :5173 can use it talking to :8000
        secure=False,  # local-dev only
        max_age=60 * 60 * 8,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def _user_id_from_cookie(token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    try:
        raw = _serializer().loads(token)
    except BadSignature:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def current_user(
    session: SessionDep,
    cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> User:
    """FastAPI dependency: requires a valid session cookie, sets
    `app.current_user_id` on the DB session, and returns the User."""
    user_id = _user_id_from_cookie(cookie)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in")
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown user")
    # Critical: this is what feedback_visible_to_me reads.
    await _set_pg_current_user(session, user.id)
    return user


async def _set_pg_current_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    # SET LOCAL is bound to the current transaction; SQLAlchemy will start one on first use.
    await session.execute(text(f"SET LOCAL app.current_user_id = '{user_id}'"))


CurrentUser = Annotated[User, Depends(current_user)]
