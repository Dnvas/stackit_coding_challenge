# syntax=docker/dockerfile:1

# --- builder: resolve and install dependencies with uv -------------------------------
FROM python:3.14-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first: this layer is cached until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# --- runtime: just Python, the virtualenv and the code ------------------------------
FROM python:3.14-slim-trixie AS runtime

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

WORKDIR /app
COPY --from=builder /app /app

# Fail-safe default: one image is promoted through every environment, and each deployment
# sets its own ENVIRONMENT (compose.yaml uses development). Forgetting to set it must
# never enable dev-only behaviour such as seeding.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

# Exec form: uvicorn is PID 1 and receives SIGTERM for graceful shutdown.
# One worker per container; scale with more containers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
