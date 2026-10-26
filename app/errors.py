"""Domain errors raised by the service layer.

Services raise these without knowing about HTTP; `app.api.problems` maps each
category to a status code. Concrete errors subclass one of the categories.
"""


class DomainError(Exception):
    """Base class for expected, client-facing errors."""


class AuthenticationError(DomainError):
    """The caller could not be identified."""


class PermissionDeniedError(DomainError):
    """The caller is identified but not allowed to do this."""


class NotFoundError(DomainError):
    """The requested resource does not exist."""


class ConflictError(DomainError):
    """The request conflicts with the current state of the resource."""


class UnprocessableError(DomainError):
    """The request is well-formed but semantically invalid."""
