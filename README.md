# STACKIT Ticketing API

A web service for booking tickets to events, built with **FastAPI** and **PostgreSQL**.

- Users browse upcoming events, book tickets, and list their bookings (past / upcoming).
- Event owners create and cancel events and see how many tickets are booked.

> Status: events API done; bookings API in progress.
>
> Design decisions and open questions: [docs/design-notes.md](docs/design-notes.md)

## Tech stack

| Concern        | Choice                                        |
| -------------- | --------------------------------------------- |
| Web framework  | FastAPI (async)                               |
| Database       | PostgreSQL 17                                 |
| ORM / driver   | SQLAlchemy 2 (async) + asyncpg                |
| Migrations     | Alembic                                       |
| Config         | pydantic-settings (environment variables)     |
| Tooling        | uv, ruff (lint + format), mypy (strict)       |
| Tests          | pytest, httpx, testcontainers (real Postgres) |

## Project layout

```
app/
  main.py          # app factory + lifespan (DB engine)
  config.py        # settings from env / .env
  db.py            # SQLAlchemy Base, engine, sessionmaker
  models/          # ORM models
  api/
    deps.py        # FastAPI dependencies (DB session, ...)
    routes/        # HTTP routers
migrations/        # Alembic migration environment + versions/
scripts/
  seed.py          # sample data for local development
tests/
  unit/            # fast, no external services
  integration/     # run against a real PostgreSQL in Docker
```

## Running locally (development)

Prerequisites: [uv](https://docs.astral.sh/uv/) and a running PostgreSQL. Docker is needed for the
integration tests.

```bash
uv sync                       # create .venv and install all dependencies
cp .env.example .env          # adjust DATABASE_URL if needed

# Start a local Postgres, for example:
docker run -d --name ticketing-db -p 5432:5432 \
  -e POSTGRES_USER=ticketing -e POSTGRES_PASSWORD=ticketing -e POSTGRES_DB=ticketing \
  postgres:17-alpine

uv run alembic upgrade head   # apply database migrations
uv run python -m scripts.seed # optional: sample users, events and bookings
uv run uvicorn app.main:app --reload
```

The seed script is idempotent (safe to rerun) and refuses to run when `ENVIRONMENT=production`.
It creates an organizer, two attendees, and events covering the main cases: upcoming, nearly
sold out, past, and cancelled.

- API: http://localhost:8000
- Interactive docs (Swagger UI): http://localhost:8000/docs
- Liveness: `GET /health/live`. Readiness (checks the DB): `GET /health/ready`

## API overview

| Method & path | Caller | Success | Description |
| --- | --- | --- | --- |
| `GET /api/v1/events` | anyone | 200 | Upcoming, not-cancelled events (sold out included), paginated with `limit` / `offset` |
| `GET /api/v1/events/{id}` | anyone | 200 | One event in any state |
| `POST /api/v1/events` | any user, who becomes the owner | 201 | Create an event. Requires `Idempotency-Key` |
| `DELETE /api/v1/events/{id}` | owner | 204 | Cancel the event and all its bookings (soft delete) |
| `GET /api/v1/events/{id}/stats` | owner | 200 | Booked / available tickets and booking count |

**Identifying the caller.** Send `X-User-Id: <id>` (a stand-in for real authentication).
A missing or unknown ID returns `401`.

**Idempotency.** `POST` endpoints require an `Idempotency-Key` header (a UUID). Retrying with the
same key returns the original resource with `Idempotent-Replayed: true`, never a duplicate.
Reusing a key for a different request returns `422`.

**Deleting events.** `DELETE` performs a soft delete: the event is marked cancelled and all its
confirmed bookings are cancelled, so booking records are kept. It is only possible before
the event starts (`409` afterwards), and repeating it is a no-op.

**Event status** is derived: `scheduled`, `sold_out`, `past`, or `cancelled`.

**Errors** use [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) Problem Details:

```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Only the event owner can do this",
  "instance": "/api/v1/events/2/stats"
}
```

Example, against seeded data:

```bash
curl -X POST http://localhost:8000/api/v1/events \
  -H "X-User-Id: 1" -H "Idempotency-Key: $(uuidgen)" -H "Content-Type: application/json" \
  -d '{"title": "Cloud Summit", "venue": "Heilbronn", "starts_at": "2027-03-01T09:00:00Z", "capacity": 200}'
```

## Database migrations

The schema is managed with [Alembic](https://alembic.sqlalchemy.org/), and every schema change is
a versioned, reviewable migration script in `migrations/versions/`.

```bash
uv run alembic revision --autogenerate -m "add events table"  # generate from model changes
uv run alembic upgrade head                                   # apply
uv run alembic downgrade -1                                   # roll back one step
uv run alembic upgrade head --sql                             # print SQL without running it
```

## Tests and quality checks

```bash
uv run pytest -m "not integration"   # unit tests only, no Docker required
uv run pytest                        # all tests; integration tests start Postgres via Docker
uv run pytest --cov                  # with coverage

uv run ruff check .                  # lint
uv run ruff format .                 # format
uv run mypy app tests migrations scripts  # type check
```

## Docker / Docker Compose

Coming soon.
