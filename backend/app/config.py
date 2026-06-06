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

    # Data source: "hybrid" = SEC EDGAR fundamentals + Yahoo/yfinance market data (recommended),
    # "edgar" = SEC only, "free" = yfinance only, "fixture" = offline snapshots.
    data_provider: str = "hybrid"

    # SEC EDGAR requires a descriptive User-Agent with a contact, sent on EVERY sec.gov request.
    sec_user_agent: str = "Tearsheet/1.0 (ed7sheeran@gmail.com)"

    # Market-data source for the hybrid. yfinance is free but blocked from datacenter IPs; set a
    # free Twelve Data key (https://twelvedata.com, 800 calls/day) for reliable prices in the cloud.
    twelvedata_api_key: str | None = None
    twelvedata_base_url: str = "https://api.twelvedata.com"

    # Optional local LLM (Ollama) as a free synthesis fallback when no Anthropic key is set.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None  # e.g. "llama3.1" — set to enable the Ollama fallback

    # If a live fetch returns essentially nothing (e.g. Yahoo rate-limit) AND this is true,
    # fall back to a fixture for the same ticker when one exists — clearly labelled as sample.
    fixture_fallback: bool = True

    # Anthropic model used for synthesis when a key is present.
    anthropic_model: str = "claude-opus-4-8"

    # Optional keys — see .env.example. Absent keys degrade gracefully.
    anthropic_api_key: str | None = None
    fred_api_key: str | None = None

    # CORS. In production set FRONTEND_ORIGIN to your exact Netlify URL — the public build
    # allows ONLY that origin (never "*"). `cors_origins` is the local-dev fallback list.
    frontend_origin: str | None = None
    cors_origins: str = "http://localhost:3000"

    # Public build is RESEARCH-ONLY. Any broker/trading/execution routes are guarded by this
    # flag and stay OFF in production. Never enable on a public deploy.
    enable_trading: bool = False

    @property
    def allowed_origins(self) -> list[str]:
        if self.frontend_origin:
            # exact-origin lock for production (comma-separated allowed if you have a preview domain)
            return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Back-compat alias.
    @property
    def cors_origin_list(self) -> list[str]:
        return self.allowed_origins


settings = Settings()
