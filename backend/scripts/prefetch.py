"""Standalone pre-fetch runner — for a Render Cron Job or a GitHub Actions schedule.

    python -m scripts.prefetch

Warms the on-disk cache for the configured PREFETCH_TICKERS so the public API serves stored data.
"""

from __future__ import annotations

from app.services.prefetch import prefetch_once

if __name__ == "__main__":
    result = prefetch_once()
    print(f"prefetched {result['ok']}/{result['tickers']} tickers + {result['etfs']} ETFs "
          f"in {result['seconds']}s (fail={result['fail']})")
