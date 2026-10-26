import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Event, User
from scripts.seed import seed

pytestmark = pytest.mark.integration


async def test_seed_is_idempotent(db_session: AsyncSession) -> None:
    """Running the seed twice does not duplicate data."""
    assert await seed(db_session) is True
    assert await seed(db_session) is False

    assert await db_session.scalar(select(func.count()).select_from(User)) == 3


async def test_seeded_ticket_counts_match_bookings(db_session: AsyncSession) -> None:
    """Each event's tickets_booked equals the sum of its booking quantities."""
    await seed(db_session)

    booked = (
        select(Booking.event_id, func.sum(Booking.quantity).label("total"))
        .group_by(Booking.event_id)
        .subquery()
    )
    rows = await db_session.execute(
        select(Event.tickets_booked, func.coalesce(booked.c.total, 0)).outerjoin(
            booked, booked.c.event_id == Event.id
        )
    )

    assert all(counter == total for counter, total in rows)
