"""Application settings, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "reactor-monitor"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://reactor:reactor@localhost:5432/reactor"
    # Comma-separated in the environment, e.g. CORS_ORIGINS=http://localhost:5173,http://foo
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance. Override with app.dependency_overrides in tests."""
    return Settings()
