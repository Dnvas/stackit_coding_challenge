from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from tests.integration.helpers import EVENTS_URL, create_event, insert_event

pytestmark = pytest.mark.integration


async def test_list_shows_only_upcoming_not_cancelled(
    db_client: AsyncClient, db_session: AsyncSession, owner: User
) -> None:
    """Past and cancelled events are hidden; sold-out events are shown as sold_out."""
    now = datetime.now(UTC)
    await insert_event(db_session, owner, title="Past", starts_at=now - timedelta(days=1))
    await insert_event(db_session, owner, title="Cancelled", cancelled_at=now)
    await insert_event(db_session, owner, title="Sold out", tickets_booked=5)
    await create_event(db_client, owner, title="Open")

    body = (await db_client.get(EVENTS_URL)).json()

    assert {(e["title"], e["status"]) for e in body["items"]} == {
        ("Sold out", "sold_out"),
        ("Open", "scheduled"),
    }
    assert body["total"] == 2


async def test_list_is_sorted_and_paginated(db_client: AsyncClient, owner: User) -> None:
    """Events come soonest first and limit/offset page through them."""
    now = datetime.now(UTC)
    for days in (3, 1, 2):
        await create_event(
            db_client,
            owner,
            title=f"In {days}d",
            starts_at=(now + timedelta(days=days)).isoformat(),
        )

    first = (await db_client.get(EVENTS_URL, params={"limit": 2})).json()
    second = (await db_client.get(EVENTS_URL, params={"limit": 2, "offset": 2})).json()

    assert [e["title"] for e in first["items"]] == ["In 1d", "In 2d"]
    assert [e["title"] for e in second["items"]] == ["In 3d"]
    assert first["total"] == second["total"] == 3


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_list_rejects_invalid_pagination(
    db_client: AsyncClient, params: dict[str, int]
) -> None:
    """Out-of-range limit or offset is a validation error."""
    response = await db_client.get(EVENTS_URL, params=params)

    assert response.status_code == 422


async def test_get_event_includes_past_and_cancelled(
    db_client: AsyncClient, db_session: AsyncSession, owner: User
) -> None:
    """A single event is visible in any state, so bookers can still look it up."""
    event = await insert_event(db_session, owner, cancelled_at=datetime.now(UTC))

    response = await db_client.get(f"{EVENTS_URL}/{event.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_get_unknown_event_is_404(db_client: AsyncClient) -> None:
    """Unknown event IDs return a 404 problem."""
    response = await db_client.get(f"{EVENTS_URL}/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Event 999 not found"
