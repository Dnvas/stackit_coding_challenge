import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Event, User
from tests.integration.helpers import EVENTS_URL, auth, create_event, insert_event

pytestmark = pytest.mark.integration


async def test_owner_cancels_event(db_client: AsyncClient, owner: User) -> None:
    """The owner's DELETE returns 204; the event stays readable as cancelled."""
    event = await create_event(db_client, owner)

    response = await db_client.delete(f"{EVENTS_URL}/{event['id']}", headers=auth(owner))

    assert response.status_code == 204
    detail = (await db_client.get(f"{EVENTS_URL}/{event['id']}")).json()
    assert detail["status"] == "cancelled"
    assert detail["cancelled_at"] is not None


async def test_cancel_is_idempotent(db_client: AsyncClient, owner: User) -> None:
    """Cancelling twice returns 204 both times, so clients can retry safely."""
    event = await create_event(db_client, owner)
    url = f"{EVENTS_URL}/{event['id']}"

    first = await db_client.delete(url, headers=auth(owner))
    second = await db_client.delete(url, headers=auth(owner))

    assert first.status_code == second.status_code == 204


async def test_cancelled_event_leaves_the_listing(db_client: AsyncClient, owner: User) -> None:
    """A cancelled event no longer appears among available events."""
    event = await create_event(db_client, owner)
    await db_client.delete(f"{EVENTS_URL}/{event['id']}", headers=auth(owner))

    assert (await db_client.get(EVENTS_URL)).json()["total"] == 0


async def test_cancel_cancels_confirmed_bookings(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """All confirmed bookings are cancelled and the ticket counter resets to 0."""
    event = await insert_event(db_session, owner, capacity=10, tickets_booked=3)
    db_session.add_all(
        Booking(event_id=event.id, user_id=attendee.id, quantity=q, idempotency_key=uuid.uuid4())
        for q in (1, 2)
    )
    await db_session.commit()

    response = await db_client.delete(f"{EVENTS_URL}/{event.id}", headers=auth(owner))

    assert response.status_code == 204
    statuses = await db_session.scalars(select(Booking.status).where(Booking.event_id == event.id))
    assert set(statuses) == {BookingStatus.CANCELLED}
    assert await db_session.scalar(select(Event.tickets_booked).where(Event.id == event.id)) == 0


async def test_non_owner_cannot_cancel(db_client: AsyncClient, owner: User, attendee: User) -> None:
    """Only the owner may cancel; others get 403 and the event is unchanged."""
    event = await create_event(db_client, owner)

    response = await db_client.delete(f"{EVENTS_URL}/{event['id']}", headers=auth(attendee))

    assert response.status_code == 403
    detail = (await db_client.get(f"{EVENTS_URL}/{event['id']}")).json()
    assert detail["status"] == "scheduled"


async def test_started_event_cannot_be_cancelled(
    db_client: AsyncClient, db_session: AsyncSession, owner: User
) -> None:
    """An event that already started returns 409: history is not rewritten."""
    event = await insert_event(db_session, owner, starts_at=datetime.now(UTC) - timedelta(hours=1))

    response = await db_client.delete(f"{EVENTS_URL}/{event.id}", headers=auth(owner))

    assert response.status_code == 409


async def test_cancel_unknown_event_is_404(db_client: AsyncClient, owner: User) -> None:
    """Cancelling an event that does not exist returns 404."""
    response = await db_client.delete(f"{EVENTS_URL}/999", headers=auth(owner))

    assert response.status_code == 404


async def test_anonymous_cancel_is_401(db_client: AsyncClient, owner: User) -> None:
    """Cancelling requires an identified caller."""
    event = await create_event(db_client, owner)

    response = await db_client.delete(f"{EVENTS_URL}/{event['id']}")

    assert response.status_code == 401
