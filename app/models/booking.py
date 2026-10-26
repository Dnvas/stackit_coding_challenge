import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin


class BookingStatus(enum.StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Booking(CreatedAtMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        # A retried request (same key) can never create a second booking.
        # Also serves as the index for "my bookings" lookups (user_id is the leading column).
        UniqueConstraint("user_id", "idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT: bookings are records we keep; events are soft-cancelled, users anonymized.
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    quantity: Mapped[int]
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            values_callable=lambda e: [member.value for member in e],
        ),
        default=BookingStatus.CONFIRMED,
        server_default=BookingStatus.CONFIRMED.value,
    )
    idempotency_key: Mapped[uuid.UUID]
