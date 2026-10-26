from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok"]


@router.get("/health/live", response_model=HealthStatus)
async def liveness() -> HealthStatus:
    """The process is up. Does not touch the database."""
    return HealthStatus(status="ok")


@router.get(
    "/health/ready",
    response_model=HealthStatus,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Database unreachable"}},
)
async def readiness(session: SessionDep) -> HealthStatus:
    """The service can serve traffic: the database answers a trivial query."""
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    return HealthStatus(status="ok")
