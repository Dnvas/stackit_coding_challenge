from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUserDep, SessionDep
from app.idempotency import IdempotencyKeyHeader, fingerprint
from app.schemas.events import EventCreate, EventRead
from app.services import events

router = APIRouter(prefix="/api/v1/events", tags=["events"])


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
