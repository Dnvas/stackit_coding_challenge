"""Request builders shared by the API integration tests."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, User

EVENTS_URL = "/api/v1/events"
BOOKINGS_URL = "/api/v1/bookings"
MY_BOOKINGS_URL = "/api/v1/users/me/bookings"


def auth(user: User, idempotency_key: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"X-User-Id": str(user.id)}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = str(idempotency_key)
    return headers


def event_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "Cloud Summit",
        "description": "Talks about sovereign cloud",
        "venue": "Heilbronn",
        "starts_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "capacity": 100,
    }
    return payload | overrides


async def create_event(client: AsyncClient, owner: User, **overrides: Any) -> dict[str, Any]:
    response = await client.post(
        EVENTS_URL, json=event_payload(**overrides), headers=auth(owner, uuid.uuid4())
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def insert_event(session: AsyncSession, owner: User, **overrides: Any) -> Event:
    """Insert directly, for states the API cannot create (past, cancelled, sold out)."""
    fields: dict[str, Any] = {
        "owner_id": owner.id,
        "title": "Direct insert",
        "venue": "Heilbronn",
        "starts_at": datetime.now(UTC) + timedelta(days=10),
        "capacity": 5,
        "idempotency_key": uuid.uuid4(),
    }
    event = Event(**(fields | overrides))
    session.add(event)
    await session.commit()
    return event


async def book(
    client: AsyncClient,
    user: User,
    event_id: int,
    quantity: int = 1,
    idempotency_key: uuid.UUID | None = None,
) -> Response:
    return await client.post(
        f"{EVENTS_URL}/{event_id}/bookings",
        json={"quantity": quantity},
        headers=auth(user, idempotency_key or uuid.uuid4()),
    )
