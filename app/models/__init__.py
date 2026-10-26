"""ORM models. Import every model module here so Alembic autogenerate sees them."""

from app.db import Base

__all__ = ["Base"]
