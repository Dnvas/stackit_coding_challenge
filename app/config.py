from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables (and a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "stackit-ticketing"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://ticketing:ticketing@localhost:5432/ticketing"


@lru_cache
def get_settings() -> Settings:
    return Settings()
