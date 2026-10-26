import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, User
from tests.integration.helpers import (
    BOOKINGS_URL,
    EVENTS_URL,
    auth,
    book,
    create_event,
    insert_event,
)

pytestmark = pytest.mark.integration


async def tickets_available(client: AsyncClient, event_id: int) -> int:
    available: int = (await client.get(f"{EVENTS_URL}/{event_id}")).json()["tickets_available"]
    return available


async def test_cancel_releases_tickets(db_client: AsyncClient, owner: User, attendee: User) -> None:
    """Cancelling returns 204, marks the booking cancelled and frees its tickets."""
    event = await create_event(db_client, owner, capacity=10)
    booking = (await book(db_client, attendee, event["id"], quantity=4)).json()

    response = await db_client.delete(f"{BOOKINGS_URL}/{booking['id']}", headers=auth(attendee))

    assert response.status_code == 204
    detail = await db_client.get(f"{BOOKINGS_URL}/{booking['id']}", headers=auth(attendee))
    assert detail.json()["status"] == "cancelled"
    assert await tickets_available(db_client, event["id"]) == 10


async def test_cancel_twice_releases_once(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """Repeating a cancellation is a 204 no-op and does not release tickets twice."""
    event = await create_event(db_client, owner, capacity=10)
    await book(db_client, owner, event["id"], quantity=5)
    booking = (await book(db_client, attendee, event["id"], quantity=2)).json()
    url = f"{BOOKINGS_URL}/{booking['id']}"

    first = await db_client.delete(url, headers=auth(attendee))
    second = await db_client.delete(url, headers=auth(attendee))

    assert first.status_code == second.status_code == 204
    assert await tickets_available(db_client, event["id"]) == 5


async def test_booking_of_cancelled_event_is_already_cancelled(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """After the event is cancelled, cancelling its booking is a no-op."""
    event = await create_event(db_client, owner, capacity=10)
    booking = (await book(db_client, attendee, event["id"], quantity=3)).json()
    await db_client.delete(f"{EVENTS_URL}/{event['id']}", headers=auth(owner))

    response = await db_client.delete(f"{BOOKINGS_URL}/{booking['id']}", headers=auth(attendee))

    assert response.status_code == 204
    assert await tickets_available(db_client, event["id"]) == 10


async def test_cannot_cancel_after_event_started(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """Bookings for events that already started cannot be cancelled."""
    event = await insert_event(
        db_session, owner, starts_at=datetime.now(UTC) - timedelta(hours=1), tickets_booked=1
    )
    booking = Booking(
        event_id=event.id, user_id=attendee.id, quantity=1, idempotency_key=uuid.uuid4()
    )
    db_session.add(booking)
    await db_session.commit()

    response = await db_client.delete(f"{BOOKINGS_URL}/{booking.id}", headers=auth(attendee))

    assert response.status_code == 409


async def test_cannot_cancel_other_users_booking(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """Another user's booking is reported as not found and stays confirmed."""
    event = await create_event(db_client, owner)
    booking = (await book(db_client, attendee, event["id"])).json()

    response = await db_client.delete(f"{BOOKINGS_URL}/{booking['id']}", headers=auth(owner))

    assert response.status_code == 404
    detail = await db_client.get(f"{BOOKINGS_URL}/{booking['id']}", headers=auth(attendee))
    assert detail.json()["status"] == "confirmed"


async def test_cancel_unknown_booking_is_404(db_client: AsyncClient, attendee: User) -> None:
    """Cancelling a booking that does not exist returns 404."""
    response = await db_client.delete(f"{BOOKINGS_URL}/999", headers=auth(attendee))

    assert response.status_code == 404
