"""FastAPI entry point: app construction, CORS, and router wiring.

PUBLIC BUILD IS RESEARCH-ONLY. Only the read-only research routers below are mounted. Any
broker / trading / execution routes must live behind `settings.enable_trading` (default False)
and are never included in a public deploy — see the guarded block at the bottom.
"""

from __future__ import annotations

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

app = FastAPI(title=settings.app_name, version=settings.app_version)

# CORS: exact-origin lock. In production FRONTEND_ORIGIN pins this to your Netlify URL only —
# never "*". GET-only, no credentials needed (public data, no cookies/auth).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

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
