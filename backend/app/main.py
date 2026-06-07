"""FastAPI entry point: app construction, CORS, and router wiring.

PUBLIC BUILD IS RESEARCH-ONLY. Only the read-only research routers below are mounted. Any
broker / trading / execution routes must live behind `settings.enable_trading` (default False)
and are never included in a public deploy — see the guarded block at the bottom.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import (
    analysis,
    analytics,
    company,
    dcf,
    events,
    financials,
    health,
    interpret,
)


def _log_active_providers() -> None:
    """Print the resolved data sources at startup so the active routing is verifiable from the
    Render logs. Uses print() (stdout) so it shows regardless of the log-handler config."""
    dp = settings.data_provider.lower()
    ds = settings.data_source.lower()
    market = {"alpaca": "Alpaca", "twelvedata": "Twelve Data",
              "yfinance": "Yahoo/yfinance"}.get(ds, ds)
    if dp == "hybrid":
        fundamentals, prices = "SEC EDGAR", market
    elif dp == "edgar":
        fundamentals, prices = "SEC EDGAR", "NONE (EDGAR has no prices)"
    elif dp == "free":
        fundamentals, prices = "Yahoo/yfinance", "Yahoo/yfinance"
    else:  # fixture
        fundamentals = prices = "fixture (recorded sample)"
    # ETF history (SPY + sector ETFs) uses the keyed market source when one is configured.
    etfs = market if (dp != "fixture" and ds in ("alpaca", "twelvedata")) else prices

    print(f"[startup] DATA_PROVIDER={dp} DATA_SOURCE={ds}", flush=True)
    print(f"[startup] fundamentals -> {fundamentals} | prices/history (stocks) -> {prices} | "
          f"ETF history (SPY/sector) -> {etfs}", flush=True)
    if dp in ("hybrid", "free") and ds == "yfinance":
        print("[startup] WARNING: prices route to yfinance, which Yahoo blocks from datacenter IPs "
              "(Render) — set DATA_SOURCE=alpaca for live prices/history.", flush=True)

    # Verify the Alpaca keys are actually loaded at runtime (presence only — NEVER the values).
    if ds == "alpaca":
        kid, sec = settings.alpaca_api_key_id, settings.alpaca_api_secret_key
        print(f"[startup] Alpaca keys loaded: id={'YES' if kid else 'NO (MISSING)'} "
              f"secret={'YES' if sec else 'NO (MISSING)'} | feed={settings.alpaca_feed} | "
              f"serve_from_cache_only={settings.serve_from_cache_only}", flush=True)
        if not (kid and sec):
            print("[startup] WARNING: Alpaca selected but a key is missing — every price call will "
                  "no-op (200 with null prices). Set ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY "
                  "(or APCA_API_KEY_ID / APCA_API_SECRET_KEY).", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.logging_config import setup_logging

    setup_logging()  # make tearsheet INFO logs (incl. per-fetch Alpaca lines) visible on the host
    _log_active_providers()
    # Start the in-process pre-fetch scheduler (no-op unless ENABLE_PREFETCH=true). It warms the
    # cache so public requests are served from stored data — never hitting upstream live.
    from app.services.prefetch import start_scheduler

    start_scheduler()
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# CORS: an explicit allow-list (FRONTEND_ORIGIN) PLUS a regex for rotating preview deployments
# (FRONTEND_ORIGIN_REGEX, default https://*.vercel.app) — never "*". An origin is allowed if it is
# in the list OR matches the regex. GET-only, no credentials needed (public data, no cookies/auth).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
print(f"[startup] CORS allow_origins={settings.allowed_origins} "
      f"allow_origin_regex={settings.allowed_origin_regex!r}", flush=True)

# --- read-only research routers (the entire public surface) ---
app.include_router(health.router)
app.include_router(company.router)
app.include_router(financials.router)
app.include_router(dcf.router)
app.include_router(analysis.router)
app.include_router(events.router)
app.include_router(interpret.router)
app.include_router(analytics.router)

# --- trading routes: OFF by default; never enabled on the public build ---
if settings.enable_trading:  # pragma: no cover - intentionally disabled in production
    # Example only — no broker/execution routers exist in this repo. If you ever add Alpaca/
    # IBKR/execution endpoints, mount them HERE so they only appear when ENABLE_TRADING=true
    # (local/private use), and they stay excluded from the public Render deploy.
    raise RuntimeError("Trading routes are not part of the research-only public build.")


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"app": settings.app_name, "docs": "/docs", "health": "/health"}
