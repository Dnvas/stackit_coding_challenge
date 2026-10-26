from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.config import Settings
from app.main import create_app
from app.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def whoami_client(postgres_url: str) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(database_url=postgres_url))

    @app.get("/whoami")
    async def whoami(user: CurrentUserDep) -> int:
        return user.id

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    user = User(name="Ada", email="ada@example.com")
    db_session.add(user)
    await db_session.commit()
    return user


async def test_known_user_is_resolved(whoami_client: AsyncClient, user: User) -> None:
    """A valid X-User-Id resolves to that user."""
    response = await whoami_client.get("/whoami", headers={"X-User-Id": str(user.id)})

    assert response.status_code == 200
    assert response.json() == user.id


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-User-Id": "abc"}, {"X-User-Id": "0"}, {"X-User-Id": "-1"}],
    ids=["missing", "not-a-number", "zero", "negative"],
)
async def test_missing_or_malformed_header_is_401(
    whoami_client: AsyncClient, headers: dict[str, str]
) -> None:
    """Requests without a usable X-User-Id are rejected before touching any resource."""
    response = await whoami_client.get("/whoami", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing or invalid X-User-Id header"


async def test_unknown_user_is_401(whoami_client: AsyncClient, db_session: AsyncSession) -> None:
    """An X-User-Id that matches no user is rejected."""
    response = await whoami_client.get("/whoami", headers={"X-User-Id": "999"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Unknown user"
