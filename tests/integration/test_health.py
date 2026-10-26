import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_readiness_is_ok_with_migrated_database(db_client: AsyncClient) -> None:
    """Readiness succeeds when the DB is reachable."""
    response = await db_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
