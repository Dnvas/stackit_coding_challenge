import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, User
from tests.integration.helpers import MY_BOOKINGS_URL, auth, book, insert_event

pytestmark = pytest.mark.integration


@pytest.fixture
async def history(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """Attendee: 2 upcoming bookings (in 2d, in 1d) and 1 past one; owner: 1 upcoming."""
    now = datetime.now(UTC)
    for title, days in [("In 2d", 2), ("In 1d", 1)]:
        event = await insert_event(
            db_session, owner, title=title, starts_at=now + timedelta(days=days)
        )
        assert (await book(db_client, attendee, event.id)).status_code == 201
    past = await insert_event(db_session, owner, title="Past", starts_at=now - timedelta(days=3))
    db_session.add(
        Booking(event_id=past.id, user_id=attendee.id, quantity=1, idempotency_key=uuid.uuid4())
    )
    await db_session.commit()
    other = await insert_event(db_session, owner, title="Owner's own")
    assert (await book(db_client, owner, other.id)).status_code == 201


async def my_titles(client: AsyncClient, user: User, **params: str | int) -> list[str]:
    response = await client.get(MY_BOOKINGS_URL, params=params, headers=auth(user))
    assert response.status_code == 200
    return [item["event"]["title"] for item in response.json()["items"]]


@pytest.mark.usefixtures("history")
async def test_upcoming_bookings_are_soonest_first(db_client: AsyncClient, attendee: User) -> None:
    """when=upcoming lists only future events, soonest first."""
    assert await my_titles(db_client, attendee, when="upcoming") == ["In 1d", "In 2d"]


@pytest.mark.usefixtures("history")
async def test_past_bookings(db_client: AsyncClient, attendee: User) -> None:
    """when=past lists only events that already started."""
    assert await my_titles(db_client, attendee, when="past") == ["Past"]


@pytest.mark.usefixtures("history")
async def test_all_bookings_by_default_latest_first(db_client: AsyncClient, attendee: User) -> None:
    """Without a filter all bookings are listed, latest event first."""
    assert await my_titles(db_client, attendee) == ["In 2d", "In 1d", "Past"]


@pytest.mark.usefixtures("history")
async def test_only_callers_bookings_are_listed(db_client: AsyncClient, owner: User) -> None:
    """Users never see other users' bookings."""
    assert await my_titles(db_client, owner) == ["Owner's own"]


@pytest.mark.usefixtures("history")
async def test_bookings_are_paginated(db_client: AsyncClient, attendee: User) -> None:
    """limit/offset page through bookings and total counts all matches."""
    response = await db_client.get(
        MY_BOOKINGS_URL, params={"limit": 2, "offset": 2}, headers=auth(attendee)
    )

    body = response.json()
    assert [item["event"]["title"] for item in body["items"]] == ["Past"]
    assert body["total"] == 3


async def test_cancelled_bookings_are_listed_with_status(
    db_client: AsyncClient, db_session: AsyncSession, owner: User, attendee: User
) -> None:
    """Bookings of a cancelled event stay visible, marked cancelled."""
    event = await insert_event(db_session, owner)
    await book(db_client, attendee, event.id)
    await db_client.delete(f"/api/v1/events/{event.id}", headers=auth(owner))

    item = (await db_client.get(MY_BOOKINGS_URL, headers=auth(attendee))).json()["items"][0]

    assert item["status"] == "cancelled"
    assert item["event"]["status"] == "cancelled"


async def test_invalid_filter_is_422(db_client: AsyncClient, attendee: User) -> None:
    """Unknown values for `when` are rejected."""
    response = await db_client.get(
        MY_BOOKINGS_URL, params={"when": "tomorrow"}, headers=auth(attendee)
    )

    assert response.status_code == 422


async def test_anonymous_listing_is_401(db_client: AsyncClient) -> None:
    """Listing bookings requires an identified caller."""
    assert (await db_client.get(MY_BOOKINGS_URL)).status_code == 401
