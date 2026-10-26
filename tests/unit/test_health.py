from httpx import AsyncClient


async def test_liveness_is_ok_without_database(client: AsyncClient) -> None:
    """Liveness only reports that the process is up; it never touches the DB."""
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_reports_503_when_database_unreachable(client: AsyncClient) -> None:
    """Readiness fails with 503 so a load balancer stops routing traffic here."""
    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
