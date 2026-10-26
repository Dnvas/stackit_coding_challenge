"""End-to-end smoke test against a running, seeded deployment (e.g. the Compose stack).

Usage: python scripts/smoke_test.py [BASE_URL]   (default http://localhost:8000)

Standard library only, so it runs anywhere without installing the project.
"""

import json
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

ORGANIZER, ATTENDEE = "1", "2"  # seeded users


def call(
    base: str,
    method: str,
    path: str,
    user: str | None = None,
    body: dict[str, Any] | None = None,
    key: uuid.UUID | None = None,
) -> tuple[int, dict[str, str], Any]:
    headers = {"Content-Type": "application/json"}
    if user:
        headers["X-User-Id"] = user
    if method == "POST":
        headers["Idempotency-Key"] = str(key or uuid.uuid4())
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, dict(response.headers), json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), json.loads(error.read() or b"null")


def check(condition: bool, message: str) -> None:
    print(("PASS " if condition else "FAIL ") + message)
    if not condition:
        sys.exit(1)


def main(base: str) -> None:
    status, _, _ = call(base, "GET", "/health/ready")
    check(status == 200, "readiness reports the database reachable")

    status, _, events = call(base, "GET", "/api/v1/events")
    check(status == 200 and events["total"] > 0, "seeded upcoming events are listed")

    event_body = {
        "title": "Smoke test event",
        "venue": "CI",
        "starts_at": "2099-01-01T10:00:00Z",
        "capacity": 5,
    }
    status, _, event = call(base, "POST", "/api/v1/events", ORGANIZER, event_body)
    check(status == 201, "organizer creates an event")

    booking_path = f"/api/v1/events/{event['id']}/bookings"
    booking_key = uuid.uuid4()
    status, _, booking = call(base, "POST", booking_path, ATTENDEE, {"quantity": 2}, booking_key)
    check(status == 201, "attendee books 2 tickets")

    status, headers, replay = call(
        base, "POST", booking_path, ATTENDEE, {"quantity": 2}, booking_key
    )
    replayed = {k.lower(): v for k, v in headers.items()}.get("idempotent-replayed") == "true"
    check(status == 201 and replayed and replay["id"] == booking["id"], "retry is replayed")

    status, _, stats = call(base, "GET", f"/api/v1/events/{event['id']}/stats", ORGANIZER)
    check(status == 200 and stats["tickets_booked"] == 2, "owner sees 2 tickets booked")

    status, _, mine = call(base, "GET", "/api/v1/users/me/bookings?when=upcoming", ATTENDEE)
    check(any(b["id"] == booking["id"] for b in mine["items"]), "booking appears in my bookings")

    status, _, _ = call(base, "DELETE", f"/api/v1/bookings/{booking['id']}", ATTENDEE)
    check(status == 204, "attendee cancels the booking")

    status, _, _ = call(base, "DELETE", f"/api/v1/events/{event['id']}", ORGANIZER)
    check(status == 204, "organizer cancels the event")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000")
