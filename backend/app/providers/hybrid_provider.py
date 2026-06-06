"""HybridProvider — SEC EDGAR fundamentals + Yahoo Finance (yfinance) market data.

EDGAR gives authoritative, unlimited, all-filer (US + foreign) fundamentals; yfinance adds the
market data EDGAR lacks (price, market cap, 52-week range, beta, history, news). Multiples are
COMPUTED in code from EDGAR statements × the yfinance price — no vendor feed:
  P/E       = price / (net income / diluted shares)
  P/S       = market cap / revenue
  P/B       = market cap / (total assets − total liabilities)
  EV/EBITDA = (market cap + total debt − cash) / (operating income + D&A)
  margins   = gross/operating/net from EDGAR; ROIC if derivable.

Graceful degradation: EDGAR is always available, so a search always returns the fundamentals.
If Yahoo is unavailable (rate-limit/block), price-dependent fields are n/a with a note; everything
price-independent (financials, margins, DCF intrinsic value) still renders. No paid feeds.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.models.schemas import CompanyPayload, PricePoint, Provenance
from app.providers.base import DataProvider
from app.providers.alpaca_provider import AlpacaProvider
from app.providers.edgar_provider import EdgarProvider
from app.providers.free_provider import FreeProvider
from app.providers.twelvedata_provider import TwelveDataProvider


def _safe_div(a, b):
    return (a / b) if (a is not None and b not in (None, 0)) else None


def _market_source():
    """Pick the market-data source from DATA_SOURCE (prod = keyed API; dev = yfinance)."""
    src = settings.data_source.lower()
    if src == "alpaca":
        return AlpacaProvider(), "Alpaca"
    if src == "twelvedata":
        return TwelveDataProvider(), "Twelve Data"
    return FreeProvider(), "Yahoo Finance"  # yfinance — local dev only (IP-blocked in the cloud)


class HybridProvider(DataProvider):
    """EDGAR fundamentals + a pluggable market-data source (Alpaca / Twelve Data / yfinance),
    selected by DATA_SOURCE. EDGAR has no blocking; the market source is keyed in production so it
    works from a shared cloud IP."""

    def __init__(self) -> None:
        self._edgar = EdgarProvider()
        self._market, market_name = _market_source()
        self.name = f"SEC EDGAR + {market_name}"

    def retrieve(self, ticker: str) -> CompanyPayload:
        ticker = ticker.upper().strip()
        payload = self._edgar.retrieve(ticker)                  # fundamentals (free, unlimited)
        payload.source = self.name
        payload.warnings = [w for w in payload.warnings if "no live price" not in w]

        # Price-INDEPENDENT metrics from EDGAR always populate.
        self._edgar_metrics(payload)

        # Market data (price, 52w, history, news) from the configured market source.
        try:
            md = self._market.market_data(ticker)
        except Exception:
            md = None
        if md and md["price"].current is not None:
            payload.price = md["price"]
            payload.news = md["news"]
            # Market cap isn't in the free quote — compute it from price × EDGAR diluted shares.
            if payload.price.market_cap is None and payload.key_metrics.shares_outstanding:
                payload.price.market_cap = payload.price.current * payload.key_metrics.shares_outstanding
            payload.provenance["price"] = Provenance(
                source=self._market.name, source_url=None,
                retrieved_at=datetime.now(timezone.utc).isoformat())
            self._price_multiples(payload)
        else:
            payload.warnings.insert(
                0,
                f"Live price/market data unavailable from {self._market.name} (rate-limit or network). "
                "SEC filing fundamentals are shown; switch to Offline for a fully-loaded sample company.",
            )
            if md and md.get("news"):
                payload.news = md["news"]
        return payload

    # -------------------------------------------------------------- metrics

    def _edgar_metrics(self, payload) -> None:
        km = payload.key_metrics
        inc = payload.financials.income
        bal = payload.financials.balance
        if inc:
            r0 = inc[0]
            km.gross_margin = _safe_div(r0.gross_profit, r0.revenue)
            km.operating_margin = _safe_div(r0.operating_income, r0.revenue)
            km.net_margin = _safe_div(r0.net_income, r0.revenue)
            if bal:
                km.roe = _safe_div(r0.net_income, bal[0].stockholders_equity)

    def _price_multiples(self, payload) -> None:
        """All multiples computed from EDGAR fundamentals × the Yahoo price."""
        km = payload.key_metrics
        price = payload.price.current
        mcap = payload.price.market_cap
        inc = payload.financials.income
        bal = payload.financials.balance
        shares = km.shares_outstanding
        if inc:
            r0 = inc[0]
            if mcap:
                km.ps = _safe_div(mcap, r0.revenue)
                if r0.ebitda:
                    net_debt = (km.total_debt or 0) - (km.total_cash or 0)
                    km.ev_ebitda = _safe_div(mcap + net_debt, r0.ebitda)
            eps = _safe_div(r0.net_income, shares)
            km.pe_ttm = _safe_div(price, eps) if (price and eps and eps > 0) else None
        if bal and mcap:
            b0 = bal[0]
            book = (b0.total_assets - b0.total_liabilities) if (
                b0.total_assets is not None and b0.total_liabilities is not None) else b0.stockholders_equity
            km.pb = _safe_div(mcap, book)
        cf = payload.financials.cashflow
        if cf and mcap:
            km.fcf_yield = _safe_div(cf[0].free_cash_flow, mcap)

    # -------------------------------------------------------------- lightweight (peers/ETFs)

    def peer_snapshot(self, ticker: str) -> dict:
        return self._market.peer_snapshot(ticker)

    def price_history(self, ticker: str) -> list[PricePoint]:
        return self._market.price_history(ticker)
