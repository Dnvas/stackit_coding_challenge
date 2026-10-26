"""Concurrent requests against a real PostgreSQL: the booking guarantees must hold under load."""

import asyncio
import uuid
from collections import Counter

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Event, User
from tests.integration.helpers import EVENTS_URL, auth, book, create_event

pytestmark = pytest.mark.integration


async def confirmed_tickets(session: AsyncSession, event_id: int) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(Booking.quantity), 0)).where(
            Booking.event_id == event_id, Booking.status == BookingStatus.CONFIRMED
        )
    )
    return int(total or 0)


async def test_parallel_bookings_never_oversell(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """50 simultaneous bookings for 10 seats: exactly 10 succeed, the rest get 409."""
    event = await create_event(db_client, owner, capacity=10)

    responses = await asyncio.gather(*(book(db_client, attendee, event["id"]) for _ in range(50)))

    assert Counter(r.status_code for r in responses) == {201: 10, 409: 40}
    tickets_booked = await db_session.scalar(
        select(Event.tickets_booked).where(Event.id == event["id"])
    )
    assert tickets_booked == await confirmed_tickets(db_session, event["id"]) == 10


async def test_parallel_retries_book_once(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """The same request sent 10 times at once creates one booking and reserves once."""
    event = await create_event(db_client, owner, capacity=10)
    key = uuid.uuid4()

    responses = await asyncio.gather(
        *(
            book(db_client, attendee, event["id"], quantity=2, idempotency_key=key)
            for _ in range(10)
        )
    )

    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["id"] for r in responses}) == 1
    assert await confirmed_tickets(db_session, event["id"]) == 2


async def test_bookings_racing_event_cancellation_stay_consistent(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """Whatever wins the race, no confirmed booking survives on a cancelled event."""
    event = await create_event(db_client, owner, capacity=100)

    cancel = db_client.delete(f"{EVENTS_URL}/{event['id']}", headers=auth(owner))
    results = await asyncio.gather(
        cancel, *(book(db_client, attendee, event["id"]) for _ in range(20))
    )

    assert results[0].status_code == 204
    assert {r.status_code for r in results[1:]} <= {201, 409}
    tickets_booked = await db_session.scalar(
        select(Event.tickets_booked).where(Event.id == event["id"])
    )
    assert tickets_booked == await confirmed_tickets(db_session, event["id"]) == 0
