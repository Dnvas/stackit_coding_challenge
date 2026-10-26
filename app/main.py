import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.problems import register_problem_handlers
from app.api.routes import health
from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine = create_engine(settings.database_url)
        app.state.sessionmaker = create_sessionmaker(engine)
        yield
        await engine.dispose()

    app = FastAPI(title="STACKIT Ticketing API", version="0.1.0", lifespan=lifespan)
    register_problem_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
