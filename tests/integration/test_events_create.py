import uuid

import pytest
from httpx import AsyncClient

from app.models import User
from tests.integration.helpers import EVENTS_URL, auth, event_payload

pytestmark = pytest.mark.integration


async def test_create_event(db_client: AsyncClient, owner: User) -> None:
    """Creating an event returns 201, a Location header, and the caller as owner."""
    response = await db_client.post(
        EVENTS_URL, json=event_payload(), headers=auth(owner, uuid.uuid4())
    )

    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"{EVENTS_URL}/{body['id']}"
    assert "idempotent-replayed" not in response.headers
    assert body["owner_id"] == owner.id
    assert body["status"] == "scheduled"
    assert body["tickets_available"] == 100


async def test_retry_with_same_key_returns_original(db_client: AsyncClient, owner: User) -> None:
    """A retried create with the same key returns the same event, marked as replayed."""
    headers = auth(owner, uuid.uuid4())
    payload = event_payload()
    first = await db_client.post(EVENTS_URL, json=payload, headers=headers)
    retry = await db_client.post(EVENTS_URL, json=payload, headers=headers)

    assert retry.status_code == 201
    assert retry.headers["idempotent-replayed"] == "true"
    assert retry.json() == first.json()


async def test_key_reused_with_different_body_is_422(db_client: AsyncClient, owner: User) -> None:
    """Reusing a key for a different event is rejected."""
    headers = auth(owner, uuid.uuid4())
    await db_client.post(EVENTS_URL, json=event_payload(), headers=headers)
    response = await db_client.post(EVENTS_URL, json=event_payload(capacity=5), headers=headers)

    assert response.status_code == 422
    assert "Idempotency-Key" in response.json()["detail"]


async def test_missing_idempotency_key_is_422(db_client: AsyncClient, owner: User) -> None:
    """The Idempotency-Key header is required."""
    response = await db_client.post(EVENTS_URL, json=event_payload(), headers=auth(owner))

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["header", "Idempotency-Key"]


async def test_anonymous_create_is_401(db_client: AsyncClient) -> None:
    """Creating an event requires an identified caller."""
    response = await db_client.post(
        EVENTS_URL, json=event_payload(), headers={"Idempotency-Key": str(uuid.uuid4())}
    )

    assert response.status_code == 401


async def test_invalid_body_is_422(db_client: AsyncClient, owner: User) -> None:
    """Validation errors are reported per field."""
    response = await db_client.post(
        EVENTS_URL, json=event_payload(capacity=0), headers=auth(owner, uuid.uuid4())
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "capacity"]
