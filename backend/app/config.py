"""Application settings, loaded from environment / .env (never from the repo)."""

from __future__ import annotations

from pydantic import AliasChoices, Field
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

    # Market-data source for the hybrid: "alpaca" (prod, keyed, cloud-safe), "twelvedata" (keyed),
    # or "yfinance" (LOCAL DEV ONLY — Yahoo scraping, blocked from datacenter IPs).
    data_source: str = "yfinance"

    # Resilience: when true, the request path NEVER calls upstream live — it serves only data the
    # pre-fetch job has stored in the cache. Pair with ENABLE_PREFETCH in production.
    serve_from_cache_only: bool = False

    # Pre-fetch job: warm the cache for a fixed ticker list a few times a day so all visitors are
    # served from stored data. Runs in-process when ENABLE_PREFETCH is true.
    enable_prefetch: bool = False
    prefetch_interval_hours: float = 6.0
    # Keep this list SHORT on the 512MB free tier — the prefetch job warms one ticker at a time,
    # but a long list means more cached payloads and a longer warm cycle. ~10 is plenty.
    prefetch_tickers: str = "AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,V,UNH"

    @property
    def prefetch_ticker_list(self) -> list[str]:
        return [t.strip().upper() for t in self.prefetch_tickers.split(",") if t.strip()]

    # Memory guard: cap how much daily price history we ever fetch/keep. ~1 trading year (252
    # bars) covers the 52-week range, beta, and 200-day MA with margin; "max" history would hold
    # thousands of points per ticker in RAM and in every cached payload. Bump only if you need
    # longer charts and have the headroom.
    max_history_days: int = 400  # calendar days requested upstream (~252 trading days)

    # Alpaca market data (free real-time-ish US equities; IEX feed on the free plan). Keyed API,
    # so it is NOT IP-blocked like Yahoo. Keys from env only. Accept BOTH our ALPACA_* names and
    # Alpaca's own SDK convention APCA_API_KEY_ID / APCA_API_SECRET_KEY — setting the latter on the
    # host is a common reason the keys appear "missing" and every price call silently no-ops.
    alpaca_api_key_id: str | None = Field(
        default=None, validation_alias=AliasChoices("ALPACA_API_KEY_ID", "APCA_API_KEY_ID"))
    alpaca_api_secret_key: str | None = Field(
        default=None, validation_alias=AliasChoices("ALPACA_API_SECRET_KEY", "APCA_API_SECRET_KEY"))
    alpaca_data_url: str = "https://data.alpaca.markets"
    # Alpaca data feed. FREE tier = "iex" (SIP requires a paid subscription and returns empty on
    # free). Every market-data call sends this explicitly. Set to "sip" only if you upgrade.
    alpaca_feed: str = "iex"

    # Twelve Data (alternative keyed market source; 800 calls/day free).
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

    # CORS. Set FRONTEND_ORIGIN to your exact production URL(s) — comma-separated for more than one
    # (e.g. "https://tearsheet-kappa.vercel.app,https://www.example.com"). `cors_origins` is the
    # local-dev fallback used only when FRONTEND_ORIGIN is unset.
    frontend_origin: str | None = None
    cors_origins: str = "http://localhost:3000"
    # Regex matched (in ADDITION to the list above) against the full Origin header, so rotating
    # preview deployments aren't blocked. Defaults to any https://*.vercel.app host (covers Vercel
    # production + preview URLs). Override via FRONTEND_ORIGIN_REGEX; set it empty ("") to disable.
    frontend_origin_regex: str | None = None

    # Public build is RESEARCH-ONLY. Any broker/trading/execution routes are guarded by this
    # flag and stay OFF in production. Never enable on a public deploy.
    enable_trading: bool = False

    @property
    def allowed_origins(self) -> list[str]:
        if self.frontend_origin:
            # exact-origin allow-list for production (comma-separated for >1 domain)
            return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_origin_regex(self) -> str | None:
        """Regex for dynamic preview origins, matched against the whole Origin header. Defaults to
        any *.vercel.app host; FRONTEND_ORIGIN_REGEX overrides it, and an empty string disables it."""
        if self.frontend_origin_regex is not None:
            return self.frontend_origin_regex.strip() or None
        return r"https://[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.vercel\.app"

    # Back-compat alias.
    @property
    def cors_origin_list(self) -> list[str]:
        return self.allowed_origins


settings = Settings()
