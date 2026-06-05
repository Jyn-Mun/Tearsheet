"""Macro inputs from FRED (optional). The only macro input the model uses is the 10y
Treasury (DGS10) as the risk-free rate. If no FRED key is configured, callers fall back to a
documented constant — the DCF still runs, it just states the fallback."""

from __future__ import annotations

from app.config import settings
from app.utils import cache

_TTL = 60 * 60 * 6  # 6h


def risk_free_rate() -> float | None:
    """Latest 10y Treasury yield as a decimal (e.g. 0.043), or None if FRED unavailable."""
    if not settings.fred_api_key:
        return None
    cached = cache.get("fred:DGS10", _TTL)
    if cached is not None:
        return cached
    try:
        import httpx

        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "DGS10",
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": "10",
        }
        r = httpx.get(url, params=params, timeout=10.0)
        r.raise_for_status()
        for obs in r.json().get("observations", []):
            val = obs.get("value")
            if val not in (".", "", None):
                rate = float(val) / 100.0
                cache.set("fred:DGS10", rate)
                return rate
    except Exception:
        return None
    return None
