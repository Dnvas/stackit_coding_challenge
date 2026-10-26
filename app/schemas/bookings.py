import enum
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from app.models import Booking, BookingStatus, Event, EventStatus


class BookingWhen(enum.StrEnum):
    UPCOMING = "upcoming"
    PAST = "past"
    ALL = "all"


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1, le=10, description="Number of tickets (1-10)")


class EventSummary(BaseModel):
    id: int
    title: str
    venue: str
    starts_at: datetime
    status: EventStatus


class BookingRead(BaseModel):
    id: int
    event: EventSummary
    quantity: int
    status: BookingStatus
    created_at: datetime

    @classmethod
    def from_models(cls, booking: Booking, event: Event, now: datetime) -> Self:
        return cls(
            id=booking.id,
            event=EventSummary(
                id=event.id,
                title=event.title,
                venue=event.venue,
                starts_at=event.starts_at,
                status=event.status_at(now),
            ),
            quantity=booking.quantity,
            status=booking.status,
            created_at=booking.created_at,
        )
