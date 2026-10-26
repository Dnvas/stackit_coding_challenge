import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db import create_sessionmaker
from app.idempotency import IdempotencyKeyReusedError, insert_or_replay
from app.models import Event, User

pytestmark = pytest.mark.integration


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(name="Ada", email="ada@example.com")
    db_session.add(user)
    await db_session.commit()
    return user


def event_values(owner: User, key: uuid.UUID, fingerprint: str = "fp-1") -> dict[str, Any]:
    return {
        "owner_id": owner.id,
        "title": "Cloud Summit",
        "venue": "Heilbronn",
        "starts_at": datetime.now(UTC) + timedelta(days=30),
        "capacity": 10,
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
    }


async def count_events(session: AsyncSession) -> int | None:
    return await session.scalar(select(func.count()).select_from(Event))


async def test_first_request_creates_row(db_session: AsyncSession, owner: User) -> None:
    """A new key inserts the row and reports it as not replayed."""
    event, replayed = await insert_or_replay(
        db_session, Event, event_values(owner, uuid.uuid4()), scope_column="owner_id"
    )

    assert replayed is False
    assert event.id is not None


async def test_retry_returns_original_row(db_session: AsyncSession, owner: User) -> None:
    """Retrying with the same key and request returns the original row, no duplicate."""
    key = uuid.uuid4()
    first, _ = await insert_or_replay(
        db_session, Event, event_values(owner, key), scope_column="owner_id"
    )
    second, replayed = await insert_or_replay(
        db_session, Event, event_values(owner, key), scope_column="owner_id"
    )

    assert replayed is True
    assert second.id == first.id
    assert await count_events(db_session) == 1


async def test_key_reused_for_different_request_is_rejected(
    db_session: AsyncSession, owner: User
) -> None:
    """Reusing a key for a different request is a client bug and raises."""
    key = uuid.uuid4()
    await insert_or_replay(db_session, Event, event_values(owner, key), scope_column="owner_id")

    with pytest.raises(IdempotencyKeyReusedError):
        await insert_or_replay(
            db_session, Event, event_values(owner, key, "fp-2"), scope_column="owner_id"
        )


async def test_concurrent_duplicates_create_one_row(
    db_engine: AsyncEngine, db_session: AsyncSession, owner: User
) -> None:
    """Two simultaneous requests with the same key create exactly one row."""
    key = uuid.uuid4()
    sessionmaker = create_sessionmaker(db_engine)

    async def attempt() -> bool:
        async with sessionmaker() as session:
            _, replayed = await insert_or_replay(
                session, Event, event_values(owner, key), scope_column="owner_id"
            )
            await session.commit()
            return replayed

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(results) == [False, True]
    assert await count_events(db_session) == 1
