from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start a throwaway PostgreSQL in Docker and migrate it to head.

    Only instantiated by integration tests, so unit tests run without Docker.
    """
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as pg:
        url: str = pg.get_connection_url()
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(alembic_cfg, "head")
        yield url


@pytest.fixture
def app() -> FastAPI:
    # Points at a port nothing listens on; unit tests never reach the DB.
    return create_app(Settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none"))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac,
    ):
        yield ac


@pytest.fixture
async def db_client(postgres_url: str) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(database_url=postgres_url))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac,
    ):
        yield ac
