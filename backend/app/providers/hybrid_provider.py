"""HybridProvider — SEC EDGAR fundamentals + FMP price/market data.

The best of both: EDGAR gives authoritative, unlimited, all-filer (US + foreign) fundamentals;
FMP adds the price/market data EDGAR lacks (current price, market cap, history, earnings) so the
price-dependent panels work. Multiples (P/E, P/S, P/B, EV/EBITDA, margins, FCF-yield) are computed
from EDGAR statements × the FMP price — no extra FMP calls.

Graceful degradation (the key requirement): EDGAR is always available, so a search always returns
everything that can be found for free. If FMP's free daily quota is exhausted, the fundamentals
still render and the price-dependent fields carry a "resets in ~Xh" note instead of bare n/a.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.schemas import CompanyPayload, PriceData, PricePoint, Provenance
from app.providers.base import DataProvider
from app.providers.edgar_provider import EdgarProvider
from app.providers.fmp_provider import FMPProvider


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return None if (math.isnan(v) or math.isinf(v)) else v
    except (TypeError, ValueError):
        return None


def _hours_to_reset() -> int:
    now = datetime.now(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, round((reset - now).total_seconds() / 3600))


def _safe_div(a, b):
    return (a / b) if (a is not None and b not in (None, 0)) else None


class HybridProvider(DataProvider):
    name = "SEC EDGAR + FMP (hybrid)"

    def __init__(self) -> None:
        self._edgar = EdgarProvider()
        self._fmp = FMPProvider()

    def retrieve(self, ticker: str) -> CompanyPayload:
        ticker = ticker.upper().strip()
        payload = self._edgar.retrieve(ticker)          # fundamentals — always free/unlimited
        payload.source = self.name
        # EDGAR's "filings-only, no price" caveat no longer applies — we add price below.
        payload.warnings = [w for w in payload.warnings if "no live price" not in w]

        # Price-INDEPENDENT metrics come from EDGAR and always populate (even if FMP is down).
        self._edgar_metrics(payload)

        if not self._fmp._key:
            payload.warnings.insert(0, "No FMP key set — price/market data unavailable (add FMP_API_KEY).")
            return payload

        self._fmp.rate_limited = False
        q = self._fmp._row("quote", symbol=ticker)
        if not q:
            if self._fmp.rate_limited:
                h = _hours_to_reset()
                payload.warnings.insert(
                    0,
                    f"Live price/market data unavailable — FMP free daily limit reached. "
                    f"Price data resets in ~{h}h. SEC filing fundamentals are shown meanwhile; "
                    f"switch to Offline for a fully-loaded sample company.",
                )
            else:
                payload.warnings.insert(0, "Live price unavailable for this ticker from FMP.")
            return payload

        self._enrich_price(payload, ticker, q)
        self._compute_multiples(payload, q)
        try:
            self._fmp._fill_earnings(payload, ticker, Provenance(source="FMP", retrieved_at=""))
        except Exception:
            pass
        return payload

    # -------------------------------------------------------------- enrichment

    def _enrich_price(self, payload, ticker, q) -> None:
        current = _f(q.get("price"))
        prev = _f(q.get("previousClose"))
        change_abs = _f(q.get("change"))
        chg_pct = _f(q.get("changePercentage"))
        history = self._fmp.price_history(ticker)
        if current is None and history:
            current = history[-1].close
        payload.price = PriceData(
            current=current, previous_close=prev,
            change_abs=change_abs if change_abs is not None else (
                (current - prev) if (current is not None and prev is not None) else None),
            change_pct=(chg_pct / 100.0) if chg_pct is not None else None,
            fifty_two_week_high=_f(q.get("yearHigh")), fifty_two_week_low=_f(q.get("yearLow")),
            market_cap=_f(q.get("marketCap")), beta=None, history=history,
        )
        payload.provenance["price"] = Provenance(
            source="Financial Modeling Prep", source_url=f"https://financialmodelingprep.com/financial-summary/{ticker}",
            retrieved_at=datetime.now(timezone.utc).isoformat())

    def _edgar_metrics(self, payload) -> None:
        """Margins + book ROE — derivable from EDGAR alone (no price needed)."""
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

    def _compute_multiples(self, payload, q) -> None:
        """Price-based multiples from EDGAR statements × FMP price (no extra FMP calls)."""
        km = payload.key_metrics
        price = payload.price.current
        mcap = payload.price.market_cap
        inc = payload.financials.income
        bal = payload.financials.balance
        shares = km.shares_outstanding
        if inc and mcap:
            r0 = inc[0]
            km.ps = _safe_div(mcap, r0.revenue)
            eps = _safe_div(r0.net_income, shares)
            km.pe_ttm = _safe_div(price, eps) if (price and eps and eps > 0) else None
            if r0.ebitda:
                net_debt = (km.total_debt or 0) - (km.total_cash or 0)
                km.ev_ebitda = _safe_div(mcap + net_debt, r0.ebitda)
        if bal and mcap:
            km.pb = _safe_div(mcap, bal[0].stockholders_equity)
        cf = payload.financials.cashflow
        if cf and mcap:
            km.fcf_yield = _safe_div(cf[0].free_cash_flow, mcap)

    # -------------------------------------------------------------- lightweight (peers/ETFs)

    def peer_snapshot(self, ticker: str) -> dict:
        return self._fmp.peer_snapshot(ticker)  # peers need price/market data → FMP

    def price_history(self, ticker: str) -> list[PricePoint]:
        return self._fmp.price_history(ticker)
