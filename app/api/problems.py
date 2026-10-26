"""Render every error as RFC 9457 Problem Details (application/problem+json)."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableError,
)

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

DOMAIN_STATUS: dict[type[DomainError], HTTPStatus] = {
    AuthenticationError: HTTPStatus.UNAUTHORIZED,
    PermissionDeniedError: HTTPStatus.FORBIDDEN,
    NotFoundError: HTTPStatus.NOT_FOUND,
    ConflictError: HTTPStatus.CONFLICT,
    UnprocessableError: HTTPStatus.UNPROCESSABLE_CONTENT,
}


def problem(
    request: Request,
    status: HTTPStatus,
    detail: str | None = None,
    headers: Mapping[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": status.phrase,
        "status": status.value,
        "instance": request.url.path,
    }
    if detail:
        body["detail"] = detail
    body.update(extensions)
    return JSONResponse(
        jsonable_encoder(body), status_code=status, headers=headers, media_type=PROBLEM_MEDIA_TYPE
    )


def status_for(exc: DomainError) -> HTTPStatus:
    for category, status in DOMAIN_STATUS.items():
        if isinstance(exc, category):
            return status
    return HTTPStatus.BAD_REQUEST


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    status = status_for(exc)
    headers = {"WWW-Authenticate": "X-User-Id"} if status is HTTPStatus.UNAUTHORIZED else None
    return problem(request, status, str(exc) or None, headers)


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    status = HTTPStatus(exc.status_code)
    detail = exc.detail if exc.detail != status.phrase else None
    return problem(request, status, detail, exc.headers)


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()
    ]
    return problem(
        request, HTTPStatus.UNPROCESSABLE_CONTENT, "Request validation failed", errors=errors
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return problem(request, HTTPStatus.INTERNAL_SERVER_ERROR)


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
