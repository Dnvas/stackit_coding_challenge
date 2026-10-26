"""Seed a development database with sample users, events and bookings.

Usage: uv run python -m scripts.seed

Idempotent (skips if seed data exists) and refuses to run in production.
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import create_engine, create_sessionmaker
from app.models import Booking, BookingStatus, Event, User

SEED_MARKER_EMAIL = "organizer@example.com"


async def seed(session: AsyncSession) -> bool:
    """Insert sample data. Returns False if it was already present."""
    if await session.scalar(select(User).where(User.email == SEED_MARKER_EMAIL)):
        return False

    now = datetime.now(UTC)
    organizer = User(name="Olivia Organizer", email=SEED_MARKER_EMAIL)
    ada = User(name="Ada Lovelace", email="ada@example.com")
    alan = User(name="Alan Turing", email="alan@example.com")
    session.add_all([organizer, ada, alan])
    await session.flush()

    def event(title: str, starts_in: timedelta, capacity: int, **kwargs: object) -> Event:
        return Event(
            owner_id=organizer.id,
            title=title,
            venue="Neckarsulm",
            starts_at=now + starts_in,
            capacity=capacity,
            idempotency_key=uuid.uuid4(),
            **kwargs,
        )

    summit = event("Cloud Summit", timedelta(days=30), capacity=200)
    workshop = event("Kubernetes Workshop", timedelta(days=7), capacity=10)
    meetup = event("Python Meetup", timedelta(days=-14), capacity=50)
    cancelled = event("Postponed Hackathon", timedelta(days=60), capacity=100, cancelled_at=now)
    session.add_all([summit, workshop, meetup, cancelled])
    await session.flush()

    confirmed, cancelled_status = BookingStatus.CONFIRMED, BookingStatus.CANCELLED
    bookings = [
        (summit, ada, 2, confirmed),
        (workshop, ada, 5, confirmed),  # workshop: 9/10 booked -> nearly sold out
        (workshop, alan, 4, confirmed),
        (meetup, alan, 1, confirmed),  # past event
        (cancelled, ada, 1, cancelled_status),  # cancelled together with its event
    ]
    for ev, user, quantity, status in bookings:
        session.add(
            Booking(
                event_id=ev.id,
                user_id=user.id,
                quantity=quantity,
                status=status,
                idempotency_key=uuid.uuid4(),
            )
        )
        if status is confirmed:  # invariant: tickets_booked counts confirmed bookings only
            ev.tickets_booked += quantity

    await session.commit()
    return True


async def main() -> int:
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to seed: ENVIRONMENT=production", file=sys.stderr)
        return 1

    engine = create_engine(settings.database_url)
    try:
        async with create_sessionmaker(engine)() as session:
            created = await seed(session)
    finally:
        await engine.dispose()

    print("Seed data created." if created else "Seed data already present, nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
