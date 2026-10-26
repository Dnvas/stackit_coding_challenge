"""create users events bookings

Revision ID: 1708a5405836
Revises:
Create Date: 2026-10-26 11:56:16.089848

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1708a5405836"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("venue", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("tickets_booked", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("capacity > 0", name=op.f("ck_events_capacity_positive")),
        sa.CheckConstraint(
            "tickets_booked >= 0 AND tickets_booked <= capacity",
            name=op.f("ck_events_tickets_booked_within_capacity"),
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_events_owner_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_owner_id"), "events", ["owner_id"], unique=False)
    op.create_index(op.f("ix_events_starts_at"), "events", ["starts_at"], unique=False)
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("confirmed", "cancelled", name="booking_status"),
            server_default="confirmed",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_bookings_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_bookings_event_id_events")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_bookings_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name=op.f("uq_bookings_user_id_idempotency_key")
        ),
    )
    op.create_index(op.f("ix_bookings_event_id"), "bookings", ["event_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_bookings_event_id"), table_name="bookings")
    op.drop_table("bookings")
    # drop_table leaves PostgreSQL enum types behind; drop explicitly so upgrade can rerun.
    sa.Enum(name="booking_status").drop(op.get_bind(), checkfirst=True)
    op.drop_index(op.f("ix_events_starts_at"), table_name="events")
    op.drop_index(op.f("ix_events_owner_id"), table_name="events")
    op.drop_table("events")
    op.drop_table("users")
