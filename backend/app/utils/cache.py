"""On-disk TTL cache. yfinance is unofficial and rate-limits aggressively, so we cache
every successful retrieval and serve from disk within the TTL. JSON-serializable values only.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

# Cache dir lives at repo-root/.cache (gitignored).
_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _path_for(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    safe = "".join(c if c.isalnum() else "_" for c in key)[:48]
    return _CACHE_DIR / f"{safe}_{digest}.json"


def get(key: str, ttl_seconds: float) -> Any | None:
    """Return cached value if present and fresh, else None."""
    path = _path_for(key)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
        if time.time() - raw["_ts"] > ttl_seconds:
            return None
        return raw["value"]
    except Exception:
        return None


def set(key: str, value: Any) -> None:
    path = _path_for(key)
    try:
        path.write_text(json.dumps({"_ts": time.time(), "value": value}))
    except Exception:
        # Caching is best-effort; never let a cache write break a request.
        pass


def cached(key: str, ttl_seconds: float, producer: Callable[[], Any]) -> Any:
    """Return cached value or call `producer()`, cache, and return it."""
    hit = get(key, ttl_seconds)
    if hit is not None:
        return hit
    value = producer()
    if value is not None:
        set(key, value)
    return value
