import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, User
from tests.integration.helpers import EVENTS_URL, auth, create_event, insert_event

pytestmark = pytest.mark.integration


async def test_owner_sees_booking_stats(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """Stats count only confirmed bookings and their tickets."""
    event = await insert_event(db_session, owner, capacity=10, tickets_booked=3)
    db_session.add_all(
        [
            Booking(
                event_id=event.id, user_id=attendee.id, quantity=1, idempotency_key=uuid.uuid4()
            ),
            Booking(
                event_id=event.id, user_id=attendee.id, quantity=2, idempotency_key=uuid.uuid4()
            ),
            Booking(
                event_id=event.id,
                user_id=attendee.id,
                quantity=4,
                status=BookingStatus.CANCELLED,
                idempotency_key=uuid.uuid4(),
            ),
        ]
    )
    await db_session.commit()

    response = await db_client.get(f"{EVENTS_URL}/{event.id}/stats", headers=auth(owner))

    assert response.status_code == 200
    assert response.json() == {
        "event_id": event.id,
        "capacity": 10,
        "tickets_booked": 3,
        "tickets_available": 7,
        "bookings_count": 2,
    }


async def test_stats_for_new_event_are_zero(db_client: AsyncClient, owner: User) -> None:
    """A fresh event has no bookings and full availability."""
    event = await create_event(db_client, owner, capacity=50)

    body = (await db_client.get(f"{EVENTS_URL}/{event['id']}/stats", headers=auth(owner))).json()

    assert (body["tickets_booked"], body["tickets_available"], body["bookings_count"]) == (0, 50, 0)


async def test_non_owner_cannot_see_stats(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """Stats are private to the event owner."""
    event = await create_event(db_client, owner)

    response = await db_client.get(f"{EVENTS_URL}/{event['id']}/stats", headers=auth(attendee))

    assert response.status_code == 403


async def test_stats_for_unknown_event_is_404(db_client: AsyncClient, owner: User) -> None:
    """Stats for an event that does not exist return 404."""
    response = await db_client.get(f"{EVENTS_URL}/999/stats", headers=auth(owner))

    assert response.status_code == 404
