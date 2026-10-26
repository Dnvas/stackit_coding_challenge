"""Idempotent creation: a retried request returns the original resource, never a duplicate.

Clients send an `Idempotency-Key` (UUID) and reuse it when retrying. The key is stored
on the created row, unique per caller, so it is written in the same transaction as
the resource itself.
"""

import hashlib
import uuid
from typing import Annotated, Any

from fastapi import Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Base
from app.errors import UnprocessableError

IdempotencyKeyHeader = Annotated[
    uuid.UUID,
    Header(
        alias="Idempotency-Key",
        description="Client-generated UUID. Reuse the same key when retrying the same request.",
    ),
]


class IdempotencyKeyReusedError(UnprocessableError):
    def __init__(self) -> None:
        super().__init__("Idempotency-Key was already used for a different request")


def fingerprint(path: str, payload: BaseModel) -> str:
    """Identify a request by its target and body, to detect a key reused for another request."""
    return hashlib.sha256(f"{path}\n{payload.model_dump_json()}".encode()).hexdigest()


async def insert_or_replay[M: Base](
    session: AsyncSession, model: type[M], values: dict[str, Any], *, scope_column: str
) -> tuple[M, bool]:
    """Insert a row, or return the existing row created earlier with the same key.

    `values` must include `scope_column` (the caller, e.g. owner_id), `idempotency_key` and
    `request_fingerprint`. Returns `(row, replayed)`. A concurrent duplicate waits on the
    unique index until the first transaction finishes, then replays its row.
    """
    created = await session.scalar(
        insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[scope_column, "idempotency_key"])
        .returning(model)
    )
    if created is not None:
        return created, False

    existing = await session.scalar(
        select(model).where(
            getattr(model, scope_column) == values[scope_column],
            getattr(model, "idempotency_key") == values["idempotency_key"],  # noqa: B009
        )
    )
    assert existing is not None, "conflicting row must exist"
    if getattr(existing, "request_fingerprint") != values["request_fingerprint"]:  # noqa: B009
        raise IdempotencyKeyReusedError()
    return existing, True
