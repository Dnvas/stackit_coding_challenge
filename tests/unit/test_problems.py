from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableError,
)


@pytest.fixture
async def problem_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    @app.get("/raise/{kind}")
    async def raise_error(kind: str) -> None:
        errors: dict[str, Exception] = {
            "auth": AuthenticationError("who are you?"),
            "forbidden": PermissionDeniedError("not yours"),
            "missing": NotFoundError("no such thing"),
            "conflict": ConflictError("too late"),
            "unprocessable": UnprocessableError("makes no sense"),
            "domain": DomainError("generic"),
            "crash": RuntimeError("secret internals"),
        }
        raise errors[kind]

    @app.get("/typed/{number}")
    async def typed(number: int) -> int:
        return number

    # raise_app_exceptions=False: return the 500 response instead of re-raising in the test.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        ("auth", 401),
        ("forbidden", 403),
        ("missing", 404),
        ("conflict", 409),
        ("unprocessable", 422),
        ("domain", 400),
    ],
)
async def test_domain_errors_map_to_status_codes(
    problem_client: AsyncClient, kind: str, status: int
) -> None:
    """Each domain error category becomes its HTTP status, with the message as detail."""
    response = await problem_client.get(f"/raise/{kind}")

    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == status
    assert body["type"] == "about:blank"
    assert body["instance"] == f"/raise/{kind}"
    assert body["detail"]


async def test_unauthorized_includes_www_authenticate(problem_client: AsyncClient) -> None:
    """401 responses carry the WWW-Authenticate header required by RFC 9110."""
    response = await problem_client.get("/raise/auth")

    assert response.headers["www-authenticate"] == "X-User-Id"


async def test_unexpected_error_hides_internals(problem_client: AsyncClient) -> None:
    """Crashes return a generic 500 problem without leaking the exception message."""
    response = await problem_client.get("/raise/crash")

    assert response.status_code == 500
    assert response.json() == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "instance": "/raise/crash",
    }


async def test_validation_error_lists_invalid_fields(problem_client: AsyncClient) -> None:
    """Invalid input returns 422 with a list of which fields failed and why."""
    response = await problem_client.get("/typed/not-a-number")

    assert response.status_code == 422
    body = response.json()
    assert body["title"] == "Unprocessable Content"
    assert body["errors"][0]["loc"] == ["path", "number"]


async def test_unknown_route_is_a_problem(problem_client: AsyncClient) -> None:
    """Framework errors such as unknown routes use the same problem format."""
    response = await problem_client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["title"] == "Not Found"
