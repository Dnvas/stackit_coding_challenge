from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import CurrentUserDep, SessionDep
from app.idempotency import IdempotencyKeyHeader, fingerprint
from app.schemas.common import Page
from app.schemas.events import EventCreate, EventRead, EventStats
from app.services import events

router = APIRouter(prefix="/api/v1/events", tags=["events"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Event does not exist"}}
OWNER_ONLY: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND,
    401: {"description": "Missing or unknown X-User-Id"},
    403: {"description": "Caller is not the event owner"},
}


@router.get("", response_model=Page[EventRead])
async def list_events(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[EventRead]:
    """Upcoming, not-cancelled events, soonest first. Sold-out events are included."""
    now = datetime.now(UTC)
    rows, total = await events.list_upcoming_events(session, now, limit, offset)
    return Page(
        items=[EventRead.from_model(event, now) for event in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}", response_model=EventRead, responses=NOT_FOUND)
async def get_event(event_id: int, session: SessionDep) -> EventRead:
    """Any event, including past and cancelled ones."""
    event = await events.get_event(session, event_id)
    return EventRead.from_model(event, datetime.now(UTC))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=EventRead,
    responses={
        401: {"description": "Missing or unknown X-User-Id"},
        422: {"description": "Invalid body, or Idempotency-Key reused for a different request"},
    },
)
async def create_event(
    data: EventCreate,
    request: Request,
    response: Response,
    session: SessionDep,
    user: CurrentUserDep,
    idempotency_key: IdempotencyKeyHeader,
) -> EventRead:
    """Create an event owned by the caller. Safe to retry with the same Idempotency-Key."""
    event, replayed = await events.create_event(
        session, user, data, idempotency_key, fingerprint(request.url.path, data)
    )
    response.headers["Location"] = f"{router.prefix}/{event.id}"
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return EventRead.from_model(event, datetime.now(UTC))


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**OWNER_ONLY, 409: {"description": "Event has already started"}},
)
async def cancel_event(event_id: int, session: SessionDep, user: CurrentUserDep) -> None:
    """Soft-delete: cancels the event and all its bookings. Repeating it is a no-op."""
    await events.cancel_event(session, user, event_id, datetime.now(UTC))


@router.get("/{event_id}/stats", response_model=EventStats, responses=OWNER_ONLY)
async def get_event_stats(event_id: int, session: SessionDep, user: CurrentUserDep) -> EventStats:
    """Booked and available tickets for one of the caller's events."""
    return await events.get_event_stats(session, user, event_id)
