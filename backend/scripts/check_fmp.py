"""Quick sanity check that your FMP key + the live provider work.

Usage (from backend/, venv active, FMP_API_KEY set in .env or the environment):
    python -m scripts.check_fmp AAPL
"""

from __future__ import annotations

import sys

from app.config import settings
from app.providers.fmp_provider import FMPProvider


def main() -> int:
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
    if not settings.fmp_api_key:
        print("✗ FMP_API_KEY is not set. Add it to backend/.env (see .env.example).")
        return 1

    p = FMPProvider().retrieve(ticker)
    print(f"source        : {p.source}")
    print(f"name          : {p.profile.name}")
    print(f"sector/ind    : {p.profile.sector} / {p.profile.industry}")
    print(f"price         : {p.price.current}  (chg {p.price.change_pct})")
    print(f"market cap    : {p.price.market_cap}")
    print(f"history pts   : {len(p.price.history)}")
    print(f"income years  : {[r.fiscal_year for r in p.financials.income]}")
    print(f"P/E · margins : pe={p.key_metrics.pe_ttm} op_margin={p.key_metrics.operating_margin}")
    print(f"earnings n    : {len(p.earnings)}")
    print(f"news          : {len(p.news)}")
    if p.warnings:
        print("warnings      :")
        for w in p.warnings:
            print("   -", w)
    ok = p.price.current is not None and bool(p.financials.income)
    print("\n" + ("✓ Live data is working." if ok else "✗ No usable data — check the ticker, key, or daily limit."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
