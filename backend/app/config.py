"""Application settings, loaded from environment / .env (never from the repo)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings. All optional in v1 — the app runs with zero keys."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Tearsheet"
    app_version: str = "1.0.0"

    # Data source: "free" = live yfinance, "fmp" = Financial Modeling Prep (live, key),
    # "fixture" = recorded sample data (offline).
    data_provider: str = "free"

    # Financial Modeling Prep (free key works from any network; yfinance is IP-blocked in some envs).
    fmp_api_key: str | None = None
    fmp_base_url: str = "https://financialmodelingprep.com/stable"

    # If a live fetch returns essentially nothing (e.g. Yahoo rate-limit) AND this is true,
    # fall back to a fixture for the same ticker when one exists — clearly labelled as sample.
    fixture_fallback: bool = True

    # Anthropic model used for synthesis when a key is present.
    anthropic_model: str = "claude-opus-4-8"

    # Optional keys — see .env.example. Absent keys degrade gracefully.
    anthropic_api_key: str | None = None
    fred_api_key: str | None = None

    # Comma-separated list of allowed CORS origins (the frontend dev server).
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
