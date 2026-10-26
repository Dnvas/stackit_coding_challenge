import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
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


async def test_book_tickets(db_client: AsyncClient, owner: User, attendee: User) -> None:
    """Booking returns 201 with a Location header and reserves the tickets."""
    event = await create_event(db_client, owner, capacity=10)

    response = await book(db_client, attendee, event["id"], quantity=3)

    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"{BOOKINGS_URL}/{body['id']}"
    assert body["quantity"] == 3
    assert body["status"] == "confirmed"
    assert body["event"]["id"] == event["id"]
    assert await tickets_available(db_client, event["id"]) == 7


async def test_retry_with_same_key_books_once(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """A retried booking returns the original and reserves the tickets only once."""
    event = await create_event(db_client, owner, capacity=10)
    key = uuid.uuid4()

    first = await book(db_client, attendee, event["id"], quantity=2, idempotency_key=key)
    retry = await book(db_client, attendee, event["id"], quantity=2, idempotency_key=key)

    assert retry.status_code == 201
    assert retry.headers["idempotent-replayed"] == "true"
    assert retry.json()["id"] == first.json()["id"]
    assert await tickets_available(db_client, event["id"]) == 8


async def test_retry_succeeds_even_after_sell_out(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """A retry of a successful booking is replayed, even if the event sold out meanwhile."""
    event = await create_event(db_client, owner, capacity=2)
    key = uuid.uuid4()
    await book(db_client, attendee, event["id"], quantity=1, idempotency_key=key)
    await book(db_client, owner, event["id"], quantity=1)

    retry = await book(db_client, attendee, event["id"], quantity=1, idempotency_key=key)

    assert retry.status_code == 201
    assert retry.headers["idempotent-replayed"] == "true"


async def test_key_reused_for_different_booking_is_422(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """The same key cannot be used for a different quantity or event."""
    first = await create_event(db_client, owner)
    second = await create_event(db_client, owner)
    key = uuid.uuid4()
    await book(db_client, attendee, first["id"], quantity=1, idempotency_key=key)

    other_quantity = await book(db_client, attendee, first["id"], quantity=2, idempotency_key=key)
    other_event = await book(db_client, attendee, second["id"], quantity=1, idempotency_key=key)

    assert other_quantity.status_code == other_event.status_code == 422


async def test_not_enough_tickets_is_409(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """Asking for more tickets than are left fails and reserves nothing."""
    event = await create_event(db_client, owner, capacity=5)
    await book(db_client, owner, event["id"], quantity=3)

    response = await book(db_client, attendee, event["id"], quantity=3)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only 2 tickets left"
    assert await tickets_available(db_client, event["id"]) == 2


async def test_sold_out_event_is_409(db_client: AsyncClient, owner: User, attendee: User) -> None:
    """A sold-out event cannot be booked."""
    event = await create_event(db_client, owner, capacity=1)
    await book(db_client, owner, event["id"])

    response = await book(db_client, attendee, event["id"])

    assert response.status_code == 409
    assert response.json()["detail"] == "Event is sold out"


async def test_failed_booking_leaves_no_row(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """A rejected booking is rolled back, so its key can be used again later."""
    event = await create_event(db_client, owner, capacity=1)
    key = uuid.uuid4()
    await book(db_client, owner, event["id"])
    rejected = await book(db_client, attendee, event["id"], idempotency_key=key)

    retry_elsewhere = await book(
        db_client, attendee, (await create_event(db_client, owner))["id"], idempotency_key=key
    )

    assert rejected.status_code == 409
    assert retry_elsewhere.status_code == 201


async def test_cancelled_event_is_409(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """A cancelled event cannot be booked."""
    event = await insert_event(db_session, owner, cancelled_at=datetime.now(UTC))

    response = await book(db_client, attendee, event.id)

    assert response.status_code == 409
    assert response.json()["detail"] == "Event has been cancelled"


async def test_started_event_is_409(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """An event that already started cannot be booked."""
    event = await insert_event(db_session, owner, starts_at=datetime.now(UTC) - timedelta(hours=1))

    response = await book(db_client, attendee, event.id)

    assert response.status_code == 409
    assert response.json()["detail"] == "Event has already started"


async def test_unknown_event_is_404(db_client: AsyncClient, attendee: User) -> None:
    """Booking an event that does not exist returns 404."""
    response = await book(db_client, attendee, 999)

    assert response.status_code == 404


async def test_anonymous_booking_is_401(db_client: AsyncClient, owner: User) -> None:
    """Booking requires an identified caller."""
    event = await create_event(db_client, owner)

    response = await db_client.post(
        f"{EVENTS_URL}/{event['id']}/bookings",
        json={"quantity": 1},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert response.status_code == 401


async def test_owner_can_book_own_event(db_client: AsyncClient, owner: User) -> None:
    """Event owners may book tickets for their own events."""
    event = await create_event(db_client, owner)

    response = await book(db_client, owner, event["id"])

    assert response.status_code == 201


async def test_get_own_booking(db_client: AsyncClient, owner: User, attendee: User) -> None:
    """Users can read their own booking via the Location URL."""
    event = await create_event(db_client, owner)
    created = await book(db_client, attendee, event["id"])

    response = await db_client.get(created.headers["location"], headers=auth(attendee))

    assert response.status_code == 200
    assert response.json() == created.json()


async def test_other_users_booking_is_404(
    db_client: AsyncClient, owner: User, attendee: User
) -> None:
    """Another user's booking is reported as not found, hiding that it exists."""
    event = await create_event(db_client, owner)
    created = await book(db_client, attendee, event["id"])

    response = await db_client.get(created.headers["location"], headers=auth(owner))

    assert response.status_code == 404
