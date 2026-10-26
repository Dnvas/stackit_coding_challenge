from pydantic import BaseModel

from app.idempotency import fingerprint


class Payload(BaseModel):
    quantity: int


def test_fingerprint_is_deterministic() -> None:
    """The same request always produces the same fingerprint."""
    assert fingerprint("/a", Payload(quantity=1)) == fingerprint("/a", Payload(quantity=1))


def test_fingerprint_differs_by_body() -> None:
    """A different body produces a different fingerprint."""
    assert fingerprint("/a", Payload(quantity=1)) != fingerprint("/a", Payload(quantity=2))


def test_fingerprint_differs_by_path() -> None:
    """The same body sent to a different resource is a different request."""
    assert fingerprint("/events/1", Payload(quantity=1)) != fingerprint(
        "/events/2", Payload(quantity=1)
    )
