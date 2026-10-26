from datetime import UTC, datetime
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.models import Event, EventStatus


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    venue: str = Field(min_length=1, max_length=200)
    starts_at: AwareDatetime = Field(
        description="Start time with timezone, e.g. 2026-12-01T18:00:00Z"
    )
    capacity: int = Field(gt=0, le=100_000)

    @field_validator("starts_at")
    @classmethod
    def must_be_in_future(cls, value: datetime) -> datetime:
        if value <= datetime.now(UTC):
            raise ValueError("must be in the future")
        return value


class EventRead(BaseModel):
    id: int
    owner_id: int
    title: str
    description: str | None
    venue: str
    starts_at: datetime
    capacity: int
    tickets_available: int
    status: EventStatus
    cancelled_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, event: Event, now: datetime) -> Self:
        return cls(
            id=event.id,
            owner_id=event.owner_id,
            title=event.title,
            description=event.description,
            venue=event.venue,
            starts_at=event.starts_at,
            capacity=event.capacity,
            tickets_available=event.tickets_available,
            status=event.status_at(now),
            cancelled_at=event.cancelled_at,
            created_at=event.created_at,
        )


class EventStats(BaseModel):
    event_id: int
    capacity: int
    tickets_booked: int
    tickets_available: int
    bookings_count: int = Field(description="Number of confirmed bookings")
