from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.main import create_app


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start a throwaway PostgreSQL in Docker and migrate it to head.

    Only instantiated by integration tests, so unit tests run without Docker.
    """
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as pg:
        url: str = pg.get_connection_url()
        command.upgrade(make_alembic_config(url), "head")
        yield url


def make_alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session")
async def db_engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(postgres_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session on the migrated test DB; all tables are emptied after each test."""
    async with create_sessionmaker(db_engine)() as session:
        yield session
    async with db_engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, events, bookings RESTART IDENTITY CASCADE"))


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
