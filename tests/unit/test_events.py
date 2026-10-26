from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.models import Event, EventStatus
from app.schemas.events import EventCreate

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def event(**overrides: Any) -> Event:
    fields: dict[str, Any] = {
        "starts_at": NOW + timedelta(days=1),
        "capacity": 10,
        "tickets_booked": 0,
        "cancelled_at": None,
    }
    return Event(**(fields | overrides))


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, EventStatus.SCHEDULED),
        ({"tickets_booked": 10}, EventStatus.SOLD_OUT),
        ({"starts_at": NOW}, EventStatus.PAST),
        ({"starts_at": NOW - timedelta(days=1), "tickets_booked": 10}, EventStatus.PAST),
        ({"cancelled_at": NOW}, EventStatus.CANCELLED),
        ({"cancelled_at": NOW, "starts_at": NOW - timedelta(days=1)}, EventStatus.CANCELLED),
    ],
    ids=[
        "open",
        "full",
        "starting-now",
        "past-and-full",
        "cancelled",
        "cancelled-and-past",
    ],
)
def test_status_is_derived(overrides: dict[str, Any], expected: EventStatus) -> None:
    """Status follows the priority cancelled > past > sold out > scheduled."""
    assert event(**overrides).status_at(NOW) is expected


def valid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "Cloud Summit",
        "venue": "Heilbronn",
        "starts_at": datetime.now(UTC) + timedelta(days=30),
        "capacity": 100,
    }
    return payload | overrides


def test_valid_event_is_accepted() -> None:
    """A complete, future event with positive capacity passes validation."""
    assert EventCreate.model_validate(valid_payload()).capacity == 100


@pytest.mark.parametrize(
    "overrides",
    [
        {"starts_at": datetime.now(UTC) - timedelta(minutes=1)},
        {"starts_at": datetime(2099, 1, 1, 12, 0)},
        {"capacity": 0},
        {"capacity": 100_001},
        {"title": "   "},
        {"capcity": 5},
    ],
    ids=["in-the-past", "no-timezone", "zero-capacity", "huge-capacity", "blank-title", "typo"],
)
def test_invalid_event_is_rejected(overrides: dict[str, Any]) -> None:
    """Past or naive start times, out-of-range capacity, blank or unknown fields are rejected."""
    with pytest.raises(ValidationError):
        EventCreate.model_validate(valid_payload(**overrides))
