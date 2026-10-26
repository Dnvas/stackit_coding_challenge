"""Request builders shared by the API integration tests."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient

from app.models import User

EVENTS_URL = "/api/v1/events"


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
