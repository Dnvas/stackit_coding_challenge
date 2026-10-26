"""add idempotency to events

Revision ID: 1280fd91dda9
Revises: 1708a5405836
Create Date: 2026-10-26 12:51:07.057755

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1280fd91dda9"
down_revision: str | Sequence[str] | None = "1708a5405836"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("bookings", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("events", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))

    # Existing rows need a key before the column can be NOT NULL: add nullable, backfill, tighten.
    op.add_column("events", sa.Column("idempotency_key", sa.Uuid(), nullable=True))
    op.execute("UPDATE events SET idempotency_key = gen_random_uuid()")
    op.alter_column("events", "idempotency_key", nullable=False)

    # Create the new (owner_id, ...) index before dropping the old owner_id one.
    op.create_unique_constraint(
        op.f("uq_events_owner_id_idempotency_key"), "events", ["owner_id", "idempotency_key"]
    )
    op.drop_index(op.f("ix_events_owner_id"), table_name="events")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_index(op.f("ix_events_owner_id"), "events", ["owner_id"], unique=False)
    op.drop_constraint(op.f("uq_events_owner_id_idempotency_key"), "events", type_="unique")
    op.drop_column("events", "idempotency_key")
    op.drop_column("events", "request_fingerprint")
    op.drop_column("bookings", "request_fingerprint")
