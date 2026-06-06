"""Pre-fetch job — warm the on-disk cache for a fixed ticker list so the PUBLIC request path is
served entirely from stored data (one upstream call per ticker per window, not one per visitor).

Runs `live_fetch()` so it is the ONLY code allowed to call upstream when SERVE_FROM_CACHE_ONLY is
true. For each ticker it pulls the full hybrid payload (EDGAR fundamentals + market price/history)
plus the index (SPY) and the configured sector ETFs so move-attribution works from cache too.

Triggered two ways:
  - in-process scheduler (app startup, when ENABLE_PREFETCH=true) — see app/main.py lifespan;
  - standalone: `python -m scripts.prefetch` (for a Render/GitHub-Actions cron).
The ticker list is configurable via PREFETCH_TICKERS (comma-separated env).
"""

from __future__ import annotations

import time

from app.cache_policy import live_fetch
from app.config import settings
from app.providers import get_provider
from app.services.move_service import _INDEX, _SECTOR_ETF


def prefetch_once() -> dict:
    """Fetch the configured tickers (+ index + sector ETFs) live and store them in the cache."""
    provider = get_provider("live")
    tickers = settings.prefetch_ticker_list
    etfs = [_INDEX] + sorted(set(_SECTOR_ETF.values()))
    ok = fail = 0
    started = time.time()
    with live_fetch():  # the ONLY place allowed to hit upstream in cache-only mode
        for tk in tickers:
            try:
                p = provider.retrieve(tk)            # warms EDGAR + market caches
                provider.price_history(tk)           # warms history cache (charts/risk/move)
                ok += 1 if (p.financials.income or p.price.current is not None) else 0
            except Exception:
                fail += 1
        for etf in etfs:                              # warm index + sector ETF history
            try:
                provider.price_history(etf)
            except Exception:
                pass
    return {"tickers": len(tickers), "etfs": len(etfs), "ok": ok, "fail": fail,
            "seconds": round(time.time() - started, 1)}


def start_scheduler() -> None:
    """Start a daemon thread that pre-fetches now and every PREFETCH_INTERVAL_HOURS. No-op unless
    ENABLE_PREFETCH is set. Safe on Render free (runs while the instance is awake; re-warms on wake)."""
    if not settings.enable_prefetch:
        return
    import threading

    def loop() -> None:
        while True:
            try:
                prefetch_once()
            except Exception:
                pass
            time.sleep(max(0.5, settings.prefetch_interval_hours) * 3600)

    t = threading.Thread(target=loop, name="prefetch", daemon=True)
    t.start()
