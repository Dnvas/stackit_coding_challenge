from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import AuthenticationError
from app.models import User


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    x_user_id: Annotated[
        str | None, Header(description="ID of the calling user (placeholder for real auth)")
    ] = None,
) -> User:
    """Resolve the caller. The single place to swap in real authentication later."""
    try:
        user_id = int(x_user_id) if x_user_id is not None else None
    except ValueError:
        user_id = None
    if user_id is None or user_id <= 0:
        raise AuthenticationError("Missing or invalid X-User-Id header")

    user = await session.get(User, user_id)
    if user is None:
        raise AuthenticationError("Unknown user")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
