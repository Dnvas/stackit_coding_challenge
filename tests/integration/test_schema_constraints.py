"""The database itself enforces core invariants, independent of application code."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Event, User

pytestmark = pytest.mark.integration


async def make_user(session: AsyncSession, email: str = "ada@example.com") -> User:
    user = User(name="Ada", email=email)
    session.add(user)
    await session.flush()
    return user


async def make_event(session: AsyncSession, owner: User, capacity: int = 10) -> Event:
    event = Event(
        owner_id=owner.id,
        title="Cloud Summit",
        venue="Heilbronn",
        starts_at=datetime.now(UTC) + timedelta(days=30),
        capacity=capacity,
    )
    session.add(event)
    await session.flush()
    return event


def make_booking(
    event: Event, user_id: int, quantity: int = 1, key: uuid.UUID | None = None
) -> Booking:
    return Booking(
        event_id=event.id, user_id=user_id, quantity=quantity, idempotency_key=key or uuid.uuid4()
    )


async def test_server_defaults_are_applied(db_session: AsyncSession) -> None:
    """New events start with 0 tickets booked, not cancelled; new bookings are confirmed."""
    user = await make_user(db_session)
    event = await make_event(db_session, user)
    booking = make_booking(event, user.id)
    db_session.add(booking)
    await db_session.flush()
    await db_session.refresh(event)
    await db_session.refresh(booking)

    assert event.tickets_booked == 0
    assert event.cancelled_at is None
    assert event.created_at is not None
    assert booking.status is BookingStatus.CONFIRMED


async def test_email_is_unique(db_session: AsyncSession) -> None:
    """Two users cannot register with the same email."""
    await make_user(db_session)

    with pytest.raises(IntegrityError, match="uq_users_email"):
        await make_user(db_session)


async def test_capacity_must_be_positive(db_session: AsyncSession) -> None:
    """An event cannot be created with zero capacity."""
    user = await make_user(db_session)

    with pytest.raises(IntegrityError, match="ck_events_capacity_positive"):
        await make_event(db_session, user, capacity=0)


async def test_tickets_booked_cannot_exceed_capacity(db_session: AsyncSession) -> None:
    """The DB refuses to oversell an event, even if application code tries to."""
    user = await make_user(db_session)
    event = await make_event(db_session, user, capacity=2)

    with pytest.raises(IntegrityError, match="ck_events_tickets_booked_within_capacity"):
        await db_session.execute(update(Event).where(Event.id == event.id).values(tickets_booked=3))


async def test_booking_quantity_must_be_positive(db_session: AsyncSession) -> None:
    """A booking for zero tickets is rejected."""
    user = await make_user(db_session)
    event = await make_event(db_session, user)
    db_session.add(make_booking(event, user.id, quantity=0))

    with pytest.raises(IntegrityError, match="ck_bookings_quantity_positive"):
        await db_session.flush()


async def test_booking_requires_existing_user(db_session: AsyncSession) -> None:
    """A booking cannot reference a user that does not exist."""
    owner = await make_user(db_session)
    event = await make_event(db_session, owner)
    db_session.add(make_booking(event, user_id=999))

    with pytest.raises(IntegrityError, match="fk_bookings_user_id_users"):
        await db_session.flush()


async def test_idempotency_key_is_unique_per_user(db_session: AsyncSession) -> None:
    """A retried request with the same key cannot create a second booking."""
    user = await make_user(db_session)
    event = await make_event(db_session, user)
    key = uuid.uuid4()
    db_session.add(make_booking(event, user.id, key=key))
    await db_session.flush()
    db_session.add(make_booking(event, user.id, key=key))

    with pytest.raises(IntegrityError, match="uq_bookings_user_id_idempotency_key"):
        await db_session.flush()


async def test_same_idempotency_key_is_allowed_for_different_users(
    db_session: AsyncSession,
) -> None:
    """Keys are scoped per user, so one user's key never blocks another user."""
    ada = await make_user(db_session)
    bob = await make_user(db_session, email="bob@example.com")
    event = await make_event(db_session, ada)
    key = uuid.uuid4()
    db_session.add_all([make_booking(event, ada.id, key=key), make_booking(event, bob.id, key=key)])

    await db_session.flush()


async def test_event_with_bookings_cannot_be_deleted(db_session: AsyncSession) -> None:
    """Hard-deleting a booked event is blocked; events are soft-cancelled instead."""
    user = await make_user(db_session)
    event = await make_event(db_session, user)
    db_session.add(make_booking(event, user.id))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="fk_bookings_event_id_events"):
        await db_session.execute(delete(Event).where(Event.id == event.id))


async def test_user_with_bookings_cannot_be_deleted(db_session: AsyncSession) -> None:
    """Deleting a user does not silently drop their bookings (and leave seats taken)."""
    owner = await make_user(db_session)
    attendee = await make_user(db_session, email="bob@example.com")
    event = await make_event(db_session, owner)
    db_session.add(make_booking(event, attendee.id))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="fk_bookings_user_id_users"):
        await db_session.execute(delete(User).where(User.id == attendee.id))


async def test_owner_with_events_cannot_be_deleted(db_session: AsyncSession) -> None:
    """An event owner cannot be deleted while they still own events."""
    owner = await make_user(db_session)
    await make_event(db_session, owner)

    with pytest.raises(IntegrityError, match="fk_events_owner_id_users"):
        await db_session.execute(delete(User).where(User.id == owner.id))
