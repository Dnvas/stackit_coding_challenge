"""Event business logic. Raises domain errors; knows nothing about HTTP."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.idempotency import insert_or_replay
from app.models import Event, User
from app.schemas.events import EventCreate


class EventNotFoundError(NotFoundError):
    def __init__(self, event_id: int) -> None:
        super().__init__(f"Event {event_id} not found")


async def create_event(
    session: AsyncSession,
    owner: User,
    data: EventCreate,
    idempotency_key: uuid.UUID,
    request_fingerprint: str,
) -> tuple[Event, bool]:
    """Create an event owned by `owner`. Returns `(event, replayed)`."""
    event, replayed = await insert_or_replay(
        session,
        Event,
        {
            **data.model_dump(),
            "owner_id": owner.id,
            "idempotency_key": idempotency_key,
            "request_fingerprint": request_fingerprint,
        },
        scope_column="owner_id",
    )
    await session.commit()
    return event, replayed


async def list_upcoming_events(
    session: AsyncSession, now: datetime, limit: int, offset: int
) -> tuple[list[Event], int]:
    """Not-cancelled events that have not started yet (sold-out included), soonest first."""
    upcoming = select(Event).where(Event.cancelled_at.is_(None), Event.starts_at > now)
    total = await session.scalar(select(func.count()).select_from(upcoming.subquery()))
    rows = await session.scalars(
        upcoming.order_by(Event.starts_at, Event.id).limit(limit).offset(offset)
    )
    return list(rows), total or 0


async def get_event(session: AsyncSession, event_id: int) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    return event
