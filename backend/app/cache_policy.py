"""Cache policy — the switch that lets the PUBLIC request path serve only stored data while the
PRE-FETCH job is allowed to call upstream live.

`should_fetch_live()` is checked by every provider before any external HTTP call:
  - normal mode (serve_from_cache_only = False): always allowed → TTL cache still shields
    upstream (one call per ticker per window, shared by all visitors).
  - cache-only mode (serve_from_cache_only = True): live calls are DENIED on the request path —
    providers return cached data or nothing. Only code running inside `live_fetch()` (the
    pre-fetch job) may call upstream, so visitor requests never touch Yahoo/Alpaca live.
"""

from __future__ import annotations

import contextlib
import contextvars

from app.config import settings

_force_live: contextvars.ContextVar[bool] = contextvars.ContextVar("force_live", default=False)


def should_fetch_live() -> bool:
    """True if a provider is allowed to make an upstream call right now."""
    return (not settings.serve_from_cache_only) or _force_live.get()


@contextlib.contextmanager
def live_fetch():
    """Used ONLY by the pre-fetch job: permit upstream calls even in cache-only mode."""
    token = _force_live.set(True)
    try:
        yield
    finally:
        _force_live.reset(token)


def read_ttl(short_seconds: float) -> float:
    """How stale cached data may be when read on the request path. In cache-only mode we serve
    whatever the last pre-fetch stored (older than the live TTL is fine — it bridges prefetch
    cycles); in normal mode we use the short live TTL."""
    if settings.serve_from_cache_only:
        return max(short_seconds, settings.prefetch_interval_hours * 3600 * 1.5)
    return short_seconds
