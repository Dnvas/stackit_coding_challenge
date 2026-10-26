import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def _user(session: AsyncSession, name: str) -> User:
    user = User(name=name, email=f"{name.lower()}@example.com")
    session.add(user)
    await session.commit()
    return user


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, "Olivia")


@pytest.fixture
async def attendee(db_session: AsyncSession) -> User:
    return await _user(db_session, "Ada")
