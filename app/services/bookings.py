"""Booking business logic. Raises domain errors; knows nothing about HTTP."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError, NotFoundError
from app.idempotency import insert_or_replay
from app.models import Booking, Event, EventStatus, User
from app.schemas.bookings import BookingCreate
from app.services.events import get_event


class BookingNotFoundError(NotFoundError):
    def __init__(self, booking_id: int) -> None:
        super().__init__(f"Booking {booking_id} not found")


class EventCancelledError(ConflictError):
    def __init__(self) -> None:
        super().__init__("Event has been cancelled")


class EventStartedError(ConflictError):
    def __init__(self) -> None:
        super().__init__("Event has already started")


class NotEnoughTicketsError(ConflictError):
    def __init__(self, available: int) -> None:
        super().__init__(
            "Event is sold out" if available <= 0 else f"Only {available} tickets left"
        )


async def create_booking(
    session: AsyncSession,
    user: User,
    event_id: int,
    data: BookingCreate,
    idempotency_key: uuid.UUID,
    request_fingerprint: str,
    now: datetime,
) -> tuple[Booking, Event, bool]:
    """Book tickets atomically. Returns `(booking, event, replayed)`.

    The booking row is inserted first, so a retry is recognised (and replayed) before any
    capacity check. The conditional UPDATE then reserves the tickets: concurrent bookings
    queue on the event row lock and Postgres re-checks the WHERE clause, so it cannot oversell.
    """
    event = await get_event(session, event_id)
    booking, replayed = await insert_or_replay(
        session,
        Booking,
        {
            "event_id": event.id,
            "user_id": user.id,
            "quantity": data.quantity,
            "idempotency_key": idempotency_key,
            "request_fingerprint": request_fingerprint,
        },
        scope_column="user_id",
    )

    if not replayed:
        reserved = await session.scalar(
            update(Event)
            .where(
                Event.id == event.id,
                Event.cancelled_at.is_(None),
                Event.starts_at > now,
                Event.tickets_booked + data.quantity <= Event.capacity,
            )
            .values(tickets_booked=Event.tickets_booked + data.quantity)
            .returning(Event.id)
            .execution_options(synchronize_session=False)
        )
        if reserved is None:
            await session.rollback()  # also removes the inserted booking
            await session.refresh(event)
            match event.status_at(now):
                case EventStatus.CANCELLED:
                    raise EventCancelledError()
                case EventStatus.PAST:
                    raise EventStartedError()
                case _:
                    raise NotEnoughTicketsError(event.tickets_available)

    await session.commit()
    await session.refresh(event)
    return booking, event, replayed


async def get_booking(
    session: AsyncSession, user: User, booking_id: int, *, for_update: bool = False
) -> Booking:
    """The caller's own booking. Other users' bookings are reported as not found."""
    booking = await session.get(Booking, booking_id, with_for_update=for_update)
    if booking is None or booking.user_id != user.id:
        raise BookingNotFoundError(booking_id)
    return booking


async def get_booking_with_event(
    session: AsyncSession, user: User, booking_id: int
) -> tuple[Booking, Event]:
    booking = await get_booking(session, user, booking_id)
    event = await session.scalar(select(Event).where(Event.id == booking.event_id))
    assert event is not None, "FK guarantees the event exists"
    return booking, event
