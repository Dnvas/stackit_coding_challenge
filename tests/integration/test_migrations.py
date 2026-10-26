"""Migrations stay in sync with the ORM models and can be rolled back cleanly."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Base
from tests.conftest import make_alembic_config

pytestmark = pytest.mark.integration


async def test_models_match_migrated_schema(db_engine: AsyncEngine) -> None:
    """Fails if a model was changed without generating a migration."""

    def diff(connection: Connection) -> list[object]:
        return list(compare_metadata(MigrationContext.configure(connection), Base.metadata))

    async with db_engine.connect() as conn:
        assert await conn.run_sync(diff) == []


def test_downgrade_and_upgrade_roundtrip(postgres_url: str) -> None:
    """Every migration can be rolled back and re-applied without errors."""
    config = make_alembic_config(postgres_url)

    command.downgrade(config, "base")
    command.upgrade(config, "head")
