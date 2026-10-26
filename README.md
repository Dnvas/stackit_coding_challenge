# STACKIT Ticketing API

A web service for booking tickets to events, built with **FastAPI** and **PostgreSQL**.

- Users browse upcoming events, book tickets, and list their bookings (past / upcoming).
- Event owners create and cancel events and see how many tickets are booked.

> Status: project scaffold. Domain endpoints are in progress.

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
uv run uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive docs (Swagger UI): http://localhost:8000/docs
- Liveness: `GET /health/live`. Readiness (checks the DB): `GET /health/ready`

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
uv run mypy app tests                # type check
```

## Docker / Docker Compose

Coming soon.
