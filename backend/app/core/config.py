"""Application settings, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Annotated

from fastapi import Request
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-do-not-use-in-production"
INSECURE_SECRETS = {DEV_JWT_SECRET, "change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "reactor-monitor"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://reactor:reactor@localhost:5432/reactor"
    # Comma-separated in the environment, e.g. CORS_ORIGINS=http://localhost:5173,http://foo
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # --- Simulator loop -----------------------------------------------------------------
    simulator_enabled: bool = True
    simulator_hz: float = Field(default=10.0, gt=0, le=100)
    persist_interval_s: float = Field(default=1.0, gt=0)

    # --- Alarm limits (educational defaults; see app/alarms/definitions.py) -------------
    alarm_hi_power_percent: float = 105.0
    alarm_hi_power_deadband: float = Field(default=2.0, ge=0)
    alarm_hi_temp_c: float = 314.0
    alarm_hi_temp_deadband: float = Field(default=1.0, ge=0)
    alarm_short_period_s: float = Field(default=15.0, gt=0)
    alarm_short_period_deadband: float = Field(default=5.0, ge=0)

    # --- Auth ---------------------------------------------------------------------------
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    # The default only works in development/test; any other environment refuses to start.
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=7, gt=0)
    # bcrypt work factor: 12 is about 0.25 s per hash on a laptop. Tests use 4 for speed.
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)

    # Create demo accounts with known passwords on start (`python -m app.cli seed-demo`).
    # Only honoured when environment == "development"; see app/cli.py.
    seed_demo_users: bool = False

    # --- Rod control envelope (applies to every role) -------------------------------------
    # Rods may not be withdrawn above 10 % inserted (fully withdrawn is +~1000s pcm from
    # the critical position), and one command may move the target at most 5 % of stroke.
    rod_min_insertion_percent: float = Field(default=10.0, ge=0, le=100)
    rod_max_step_percent: float = Field(default=5.0, gt=0, le=100)

    @model_validator(mode="after")
    def require_real_secret_outside_dev(self) -> "Settings":
        if self.environment not in {"development", "test"} and (
            self.jwt_secret in INSECURE_SECRETS or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance built from the environment."""
    return Settings()


def app_settings(request: Request) -> Settings:
    """FastAPI dependency: the Settings this app instance was created with."""
    settings: Settings = request.app.state.settings
    return settings
