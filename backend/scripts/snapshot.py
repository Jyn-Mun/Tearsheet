"""Bake REAL FMP data for a basket of tickers into the app's offline snapshot fixtures.

This powers the deployed site's Offline mode (and the Live mode's fallback): real point-in-time
data that always works, with no per-request API calls or limits. Run it once (and occasionally
to refresh) with your FMP key set. It writes app/providers/fixtures/*.json.

- Stocks → full FMP retrieve() payload (all panels work offline).
- ETFs   → price-only minimal payload (enough for move-attribution's index/sector series).

Cost: ~9 calls per stock + 1 per ETF. The default basket (~15 stocks + ~13 ETFs) ≈ 150 calls,
under the free 250/day budget. Empty results (rate-limit/coverage) are skipped, never overwriting
good data.

Usage (backend/, venv active, FMP_API_KEY set):
    python -m scripts.snapshot                 # default basket
    python -m scripts.snapshot AAPL MSFT SPY   # specific tickers
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.providers.fmp_provider import FMPProvider

OUT = Path(__file__).resolve().parents[1] / "app" / "providers" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

# Real basket: sector spread + AMD/AVGO/INTC (tech peers) + JPM (financial-sector DCF flag).
STOCKS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "INTC",
          "JPM", "JNJ", "XOM", "WMT", "COST"]
# Index + SPDR sector ETFs + semis (for move attribution offline).
ETFS = ["SPY", "XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLC", "XLU", "XLRE", "SMH"]

SNAPSHOT_SOURCE = "snapshot (recorded real data)"


def _stamp(payload_dict: dict) -> dict:
    payload_dict["source"] = f"{SNAPSHOT_SOURCE} · {datetime.now(timezone.utc).date().isoformat()}"
    payload_dict.setdefault("warnings", []).insert(
        0, "Recorded real-data snapshot (point-in-time) — not live. Use Live mode for current data."
    )
    return payload_dict


def snapshot_stock(prov: FMPProvider, ticker: str) -> bool:
    p = prov.retrieve(ticker)
    if p.price.current is None and not p.financials.income:
        print(f"  skip {ticker}: no data (rate-limit/coverage)")
        return False
    (OUT / f"{ticker}.json").write_text(json.dumps(_stamp(p.model_dump()), indent=2))
    print(f"  wrote {ticker}.json (price {p.price.current}, {len(p.financials.income)}y financials, "
          f"{len(p.price.history)} px)")
    return True


def snapshot_etf(prov: FMPProvider, ticker: str) -> bool:
    hist = prov.price_history(ticker)
    if not hist:
        print(f"  skip {ticker}: no history")
        return False
    closes = [h.close for h in hist]
    payload = {
        "ticker": ticker, "as_of": datetime.now(timezone.utc).isoformat(), "source": "x",
        "profile": {"name": f"{ticker} (ETF)", "sector": "Index/ETF"},
        "price": {
            "current": closes[-1], "previous_close": closes[-2] if len(closes) > 1 else None,
            "change_abs": round(closes[-1] - closes[-2], 2) if len(closes) > 1 else None,
            "change_pct": round(closes[-1] / closes[-2] - 1, 4) if len(closes) > 1 and closes[-2] else None,
            "market_cap": None, "beta": 1.0, "history": [h.model_dump() for h in hist],
        },
        "key_metrics": {}, "financials": {"income": [], "balance": [], "cashflow": []},
        "earnings": [], "news": [], "provenance": {}, "warnings": [],
    }
    (OUT / f"{ticker}.json").write_text(json.dumps(_stamp(payload), indent=2))
    print(f"  wrote {ticker}.json ({len(hist)} px)")
    return True


def main() -> int:
    if not settings.fmp_api_key:
        print("✗ FMP_API_KEY not set — add it to backend/.env first.")
        return 1
    prov = FMPProvider()
    args = [a.upper() for a in sys.argv[1:]]
    stocks = [t for t in (args or STOCKS) if t not in ETFS]
    etfs = [t for t in (args or ETFS) if t in ETFS] if args else ETFS

    print(f"Snapshotting {len(stocks)} stocks + {len(etfs)} ETFs → {OUT}")
    n = 0
    for t in stocks:
        n += snapshot_stock(prov, t)
    for t in etfs:
        n += snapshot_etf(prov, t)
    print(f"\n✓ Wrote {n} snapshot fixtures. Offline mode now serves real data for them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
