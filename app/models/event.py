import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin


class Event(CreatedAtMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="capacity_positive"),
        # Backstop for the atomic booking UPDATE: the DB itself refuses to oversell.
        CheckConstraint(
            "tickets_booked >= 0 AND tickets_booked <= capacity",
            name="tickets_booked_within_capacity",
        ),
        # A retried create (same key) can never create a second event.
        # Also serves as the index for "events by owner" lookups (owner_id is the leading column).
        UniqueConstraint("owner_id", "idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    venue: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    capacity: Mapped[int]
    tickets_booked: Mapped[int] = mapped_column(server_default="0")
    # Soft delete: cancelled events keep their bookings for history.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[uuid.UUID]
    # SHA-256 of the creating request; NULL for rows not created via the API (e.g. seed data).
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
