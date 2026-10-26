from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.bookings import BookingCreate


@pytest.mark.parametrize("quantity", [1, 10])
def test_quantity_within_limits_is_accepted(quantity: int) -> None:
    """Bookings of 1 to 10 tickets are valid."""
    assert BookingCreate(quantity=quantity).quantity == quantity


@pytest.mark.parametrize(
    "payload",
    [{"quantity": 0}, {"quantity": 11}, {"quantity": 1, "seat": "A1"}, {}],
    ids=["zero", "too-many", "unknown-field", "missing"],
)
def test_invalid_booking_is_rejected(payload: dict[str, Any]) -> None:
    """Out-of-range, missing or unknown fields are rejected."""
    with pytest.raises(ValidationError):
        BookingCreate.model_validate(payload)
