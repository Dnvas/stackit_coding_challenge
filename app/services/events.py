"""Event business logic. Raises domain errors; knows nothing about HTTP."""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.idempotency import insert_or_replay
from app.models import Booking, BookingStatus, Event, User
from app.schemas.events import EventCreate


class EventNotFoundError(NotFoundError):
    def __init__(self, event_id: int) -> None:
        super().__init__(f"Event {event_id} not found")


class NotEventOwnerError(PermissionDeniedError):
    def __init__(self) -> None:
        super().__init__("Only the event owner can do this")


class EventAlreadyStartedError(ConflictError):
    def __init__(self) -> None:
        super().__init__("Event has already started and can no longer be cancelled")


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


async def get_event(session: AsyncSession, event_id: int, *, for_update: bool = False) -> Event:
    event = await session.get(Event, event_id, with_for_update=for_update)
    if event is None:
        raise EventNotFoundError(event_id)
    return event


async def get_owned_event(
    session: AsyncSession, user: User, event_id: int, *, for_update: bool = False
) -> Event:
    event = await get_event(session, event_id, for_update=for_update)
    if event.owner_id != user.id:
        raise NotEventOwnerError()
    return event


async def cancel_event(session: AsyncSession, user: User, event_id: int, now: datetime) -> None:
    """Soft-delete: mark cancelled and cancel its confirmed bookings, in one transaction.

    Idempotent: cancelling an already-cancelled event is a no-op. The row lock serializes
    this with concurrent bookings, so no booking can land on a cancelled event.
    """
    event = await get_owned_event(session, user, event_id, for_update=True)
    if event.cancelled_at is None:
        if event.starts_at <= now:
            raise EventAlreadyStartedError()
        event.cancelled_at = now
        event.tickets_booked = 0  # invariant: counts confirmed bookings only
        await session.execute(
            update(Booking)
            .where(Booking.event_id == event.id, Booking.status == BookingStatus.CONFIRMED)
            .values(status=BookingStatus.CANCELLED)
        )
    await session.commit()
