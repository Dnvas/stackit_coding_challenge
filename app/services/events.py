"""Event business logic. Raises domain errors; knows nothing about HTTP."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.idempotency import insert_or_replay
from app.models import Event, User
from app.schemas.events import EventCreate


async def create_event(
    session: AsyncSession,
    owner: User,
    data: EventCreate,
    idempotency_key: uuid.UUID,
    request_fingerprint: str,
) -> tuple[Event, bool]:
    """Create an event owned by `owner`. Returns `(event, replayed)`."""
    event, replayed = await insert_or_replay(
        session,
        Event,
        {
            **data.model_dump(),
            "owner_id": owner.id,
            "idempotency_key": idempotency_key,
            "request_fingerprint": request_fingerprint,
        },
        scope_column="owner_id",
    )
    await session.commit()
    return event, replayed
