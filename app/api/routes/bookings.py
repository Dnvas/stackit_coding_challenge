from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import CurrentUserDep, SessionDep
from app.idempotency import IdempotencyKeyHeader, fingerprint
from app.schemas.bookings import BookingCreate, BookingRead, BookingWhen
from app.schemas.common import Page
from app.services import bookings

router = APIRouter(prefix="/api/v1", tags=["bookings"])

AUTHENTICATED: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or unknown X-User-Id"},
}
OWN_BOOKING: dict[int | str, dict[str, Any]] = {
    **AUTHENTICATED,
    404: {"description": "Booking does not exist or belongs to another user"},
}


@router.post(
    "/events/{event_id}/bookings",
    status_code=status.HTTP_201_CREATED,
    response_model=BookingRead,
    responses={
        **AUTHENTICATED,
        404: {"description": "Event does not exist"},
        409: {"description": "Event cancelled, already started, or not enough tickets"},
        422: {"description": "Invalid body, or Idempotency-Key reused for a different request"},
    },
)
async def create_booking(
    event_id: int,
    data: BookingCreate,
    request: Request,
    response: Response,
    session: SessionDep,
    user: CurrentUserDep,
    idempotency_key: IdempotencyKeyHeader,
) -> BookingRead:
    """Book tickets for an event. Safe to retry with the same Idempotency-Key."""
    now = datetime.now(UTC)
    booking, event, replayed = await bookings.create_booking(
        session, user, event_id, data, idempotency_key, fingerprint(request.url.path, data), now
    )
    response.headers["Location"] = f"{router.prefix}/bookings/{booking.id}"
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return BookingRead.from_models(booking, event, now)


@router.get("/bookings/{booking_id}", response_model=BookingRead, responses=OWN_BOOKING)
async def get_booking(booking_id: int, session: SessionDep, user: CurrentUserDep) -> BookingRead:
    """One of the caller's bookings."""
    booking, event = await bookings.get_booking_with_event(session, user, booking_id)
    return BookingRead.from_models(booking, event, datetime.now(UTC))


@router.get("/users/me/bookings", response_model=Page[BookingRead], responses=AUTHENTICATED)
async def list_my_bookings(
    session: SessionDep,
    user: CurrentUserDep,
    when: BookingWhen = BookingWhen.ALL,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[BookingRead]:
    """The caller's bookings, optionally only upcoming or past events."""
    now = datetime.now(UTC)
    rows, total = await bookings.list_bookings(session, user, when, now, limit, offset)
    return Page(
        items=[BookingRead.from_models(booking, event, now) for booking, event in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
