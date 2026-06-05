"""FMPProvider — live data from Financial Modeling Prep's `/stable/` API (free API key).

Why this exists: yfinance/Yahoo rate-limits by IP and is unusable from some networks (e.g. shared
sandboxes). FMP authenticates per-key, so a free key gives reliable real data from anywhere. This
is the DataProvider "swap point" in action — a new class implementing the same interface, with no
changes to any service or to the UI.

Free tier (verified): real quotes, full income/balance/cash-flow statements (3-5y), TTM ratios +
key metrics, 2y daily price history, earnings surprises. News is a paid endpoint, so it degrades to
empty with a note. ~250 calls/day — so we cache aggressively (30-min TTL). Every call is defensive:
failures add a warning and degrade to n/a, never crash, never invent.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models.schemas import (
    BalanceRow, CashflowRow, CompanyPayload, CompanyProfile, EarningsRecord,
    Financials, IncomeRow, KeyMetrics, NewsItem, PriceData, PricePoint, Provenance,
)
from app.providers.base import DataProvider
from app.utils import cache

_CACHE_TTL = 60 * 60 * 6  # 6h — research data is daily; long TTL conserves the ~250/day free budget.


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return None if (math.isnan(v) or math.isinf(v)) else v
    except (TypeError, ValueError):
        return None


def _first(d: dict, *keys: str) -> Any:
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _int(x: Any) -> int | None:
    try:
        return int(str(x).replace(",", "")) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _yr(date_str: Any) -> int:
    try:
        return int(str(date_str)[:4])
    except (TypeError, ValueError):
        return 0


class FMPProvider(DataProvider):
    name = "Financial Modeling Prep (live)"

    def __init__(self) -> None:
        self._key = settings.fmp_api_key
        self._base = settings.fmp_base_url

    # --------------------------------------------------------------- http

    def _get(self, endpoint: str, **params: Any) -> Any:
        import httpx

        params["apikey"] = self._key
        try:
            r = httpx.get(f"{self._base}/{endpoint}", params=params, timeout=15.0)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and ("Error Message" in data or "Restricted Endpoint" in str(data)):
                return None
            return data
        except Exception:
            return None

    def _row(self, endpoint: str, **params: Any) -> dict:
        data = self._get(endpoint, **params)
        return data[0] if isinstance(data, list) and data else {}

    # --------------------------------------------------------------- retrieve

    def retrieve(self, ticker: str) -> CompanyPayload:
        ticker = ticker.upper().strip()
        payload = CompanyPayload(ticker=ticker, as_of=_now(), source=self.name)
        if not self._key:
            payload.warnings.append("FMP_API_KEY is not set — add it to backend/.env to fetch live data.")
            return payload

        cached = cache.get(f"fmp:{ticker}", _CACHE_TTL)
        if cached is not None:
            return CompanyPayload.model_validate(cached)

        self._build(payload, ticker)
        if payload.price.current is not None or payload.profile.name:
            cache.set(f"fmp:{ticker}", payload.model_dump())
        return payload

    # --- lightweight fetches (save API calls vs a full retrieve) ---

    def peer_snapshot(self, ticker: str) -> dict:
        ticker = ticker.upper().strip()
        if not self._key:
            return {"ticker": ticker, "name": None, "market_cap": None,
                    "pe_ttm": None, "ev_ebitda": None, "ps": None, "pb": None}
        cached = cache.get(f"fmp:peer:{ticker}", _CACHE_TTL)
        if cached is not None:
            return cached
        q = self._row("quote", symbol=ticker)        # name, marketCap
        r = self._row("ratios-ttm", symbol=ticker)   # pe, ps, pb
        k = self._row("key-metrics-ttm", symbol=ticker)  # ev/ebitda
        snap = {
            "ticker": ticker,
            "name": _first(q, "name"),
            "market_cap": _f(_first(q, "marketCap")),
            "pe_ttm": _f(_first(r, "priceToEarningsRatioTTM")),
            "ev_ebitda": _f(_first(k, "evToEBITDATTM")),
            "ps": _f(_first(r, "priceToSalesRatioTTM")),
            "pb": _f(_first(r, "priceToBookRatioTTM")),
        }
        if snap["name"] or snap["market_cap"]:
            cache.set(f"fmp:peer:{ticker}", snap)
        return snap

    def price_history(self, ticker: str) -> list[PricePoint]:
        ticker = ticker.upper().strip()
        if not self._key:
            return []
        cached = cache.get(f"fmp:hist:{ticker}", _CACHE_TTL)
        if cached is not None:
            return [PricePoint(**p) for p in cached]
        hist = self._get("historical-price-eod/full", symbol=ticker, limit=504)
        pts: list[PricePoint] = []
        if isinstance(hist, list):
            for row in reversed(hist):
                c = _f(row.get("close"))
                d = row.get("date")
                if c is not None and d:
                    pts.append(PricePoint(date=d[:10], close=c))
            pts = pts[-756:]
        if pts:
            cache.set(f"fmp:hist:{ticker}", [p.model_dump() for p in pts])
        return pts

    def _build(self, payload: CompanyPayload, ticker: str) -> None:
        prov = Provenance(
            source=self.name,
            source_url=f"https://financialmodelingprep.com/financial-summary/{ticker}",
            retrieved_at=_now(),
        )
        q = self._row("quote", symbol=ticker)
        pf = self._row("profile", symbol=ticker)
        if not q and not pf:
            payload.warnings.append(
                f"No live data returned for {ticker} (check the ticker, your FMP key, or daily limit)."
            )

        self._fill_profile(payload, pf, q, prov)
        self._fill_price_metrics(payload, q, pf, ticker, prov)
        self._fill_statements(payload, ticker, prov)
        self._fill_earnings(payload, ticker, prov)
        self._fill_news(payload, ticker, prov)

    # --------------------------------------------------------------- sections

    def _fill_profile(self, payload, pf, q, prov) -> None:
        payload.profile = CompanyProfile(
            name=_first(pf, "companyName") or _first(q, "name"),
            exchange=_first(pf, "exchange") or _first(q, "exchange"),
            sector=_first(pf, "sector"),
            industry=_first(pf, "industry"),
            country=_first(pf, "country"),
            summary=_first(pf, "description"),
            employees=_int(_first(pf, "fullTimeEmployees")),
            currency=_first(pf, "currency"),
        )
        if pf or q:
            payload.provenance["profile"] = prov

    def _fill_price_metrics(self, payload, q, pf, ticker, prov) -> None:
        history: list[PricePoint] = []
        hist = self._get("historical-price-eod/full", symbol=ticker, limit=504)
        if isinstance(hist, list):
            for row in reversed(hist):  # FMP returns newest-first; we want oldest-first
                c = _f(row.get("close"))
                d = row.get("date")
                if c is not None and d:
                    history.append(PricePoint(date=d[:10], close=c))
            history = history[-756:]  # keep ~3y to bound payload size (enough for beta + events)

        current = _f(_first(q, "price"))
        prev = _f(_first(q, "previousClose"))
        if current is None and history:
            current = history[-1].close
        change_abs = _f(_first(q, "change"))
        if change_abs is None and current is not None and prev is not None:
            change_abs = current - prev
        chg_pct = _f(_first(q, "changePercentage"))
        change_pct = (chg_pct / 100.0) if chg_pct is not None else (
            (change_abs / prev) if (change_abs is not None and prev) else None)

        payload.price = PriceData(
            current=current, previous_close=prev, change_abs=change_abs, change_pct=change_pct,
            fifty_two_week_high=_f(_first(q, "yearHigh")), fifty_two_week_low=_f(_first(q, "yearLow")),
            market_cap=_f(_first(q, "marketCap")) or _f(_first(pf, "marketCap")),
            beta=_f(_first(pf, "beta")), history=history,
        )
        payload.provenance["price"] = prov

        r = self._row("ratios-ttm", symbol=ticker)
        k = self._row("key-metrics-ttm", symbol=ticker)
        payload.key_metrics = KeyMetrics(
            pe_ttm=_f(_first(r, "priceToEarningsRatioTTM")),
            forward_pe=None,
            ev_ebitda=_f(_first(k, "evToEBITDATTM")),
            ps=_f(_first(r, "priceToSalesRatioTTM")),
            pb=_f(_first(r, "priceToBookRatioTTM")),
            dividend_yield=_f(_first(r, "dividendYieldTTM")),
            gross_margin=_f(_first(r, "grossProfitMarginTTM")),
            operating_margin=_f(_first(r, "operatingProfitMarginTTM", "ebitMarginTTM")),
            net_margin=_f(_first(r, "netProfitMarginTTM")),
            roe=_f(_first(k, "returnOnEquityTTM") or _first(r, "returnOnEquityTTM")),
            roic=_f(_first(k, "returnOnInvestedCapitalTTM")),
            fcf_yield=_f(_first(k, "freeCashFlowYieldTTM")),
            shares_outstanding=None,  # filled from the income statement below
            total_debt=None, total_cash=None, ebitda=None,
        )
        if r or k or q:
            payload.provenance["key_metrics"] = prov

    def _fill_statements(self, payload, ticker, prov) -> None:
        inc = self._get("income-statement", symbol=ticker, period="annual", limit=5)
        bal = self._get("balance-sheet-statement", symbol=ticker, period="annual", limit=5)
        cf = self._get("cash-flow-statement", symbol=ticker, period="annual", limit=5)
        fin = Financials()

        if isinstance(inc, list):
            for r in inc:
                fin.income.append(IncomeRow(
                    fiscal_year=_int(r.get("fiscalYear")) or _yr(r.get("date")),
                    period_end=(r.get("date") or "")[:10] or None,
                    revenue=_f(r.get("revenue")), cost_of_revenue=_f(r.get("costOfRevenue")),
                    gross_profit=_f(r.get("grossProfit")), operating_income=_f(r.get("operatingIncome")),
                    ebitda=_f(r.get("ebitda")), pretax_income=_f(r.get("incomeBeforeTax")),
                    tax_provision=_f(r.get("incomeTaxExpense")), net_income=_f(r.get("netIncome")),
                    interest_expense=_f(r.get("interestExpense")),
                ))
            # shares outstanding from the latest filing (stable quote omits it)
            if inc:
                payload.key_metrics.shares_outstanding = _f(
                    _first(inc[0], "weightedAverageShsOutDil", "weightedAverageShsOut"))
        if isinstance(bal, list):
            for r in bal:
                ca, cl = _f(r.get("totalCurrentAssets")), _f(r.get("totalCurrentLiabilities"))
                fin.balance.append(BalanceRow(
                    fiscal_year=_int(r.get("fiscalYear")) or _yr(r.get("date")),
                    period_end=(r.get("date") or "")[:10] or None,
                    total_assets=_f(r.get("totalAssets")), total_liabilities=_f(r.get("totalLiabilities")),
                    cash_and_equivalents=_f(r.get("cashAndCashEquivalents")), total_debt=_f(r.get("totalDebt")),
                    stockholders_equity=_f(r.get("totalStockholdersEquity")),
                    current_assets=ca, current_liabilities=cl,
                    working_capital=(ca - cl) if (ca is not None and cl is not None) else None,
                ))
            if bal:
                payload.key_metrics.total_debt = _f(bal[0].get("totalDebt"))
                payload.key_metrics.total_cash = _f(bal[0].get("cashAndCashEquivalents"))
        if isinstance(cf, list):
            for r in cf:
                fin.cashflow.append(CashflowRow(
                    fiscal_year=_int(r.get("fiscalYear")) or _yr(r.get("date")),
                    period_end=(r.get("date") or "")[:10] or None,
                    operating_cash_flow=_f(r.get("operatingCashFlow")),
                    capital_expenditure=_f(r.get("capitalExpenditure")),
                    free_cash_flow=_f(r.get("freeCashFlow")),
                    depreciation_amortization=_f(r.get("depreciationAndAmortization")),
                    change_in_working_capital=_f(r.get("changeInWorkingCapital")),
                ))
        payload.financials = fin
        if fin.income or fin.balance or fin.cashflow:
            payload.provenance["financials"] = prov

    def _fill_earnings(self, payload, ticker, prov) -> None:
        # Free tier caps `limit` to <=5 on this endpoint; omit it to get full history.
        data = self._get("earnings", symbol=ticker)
        if not isinstance(data, list):
            return
        recs: list[EarningsRecord] = []
        for r in data:
            actual = _f(_first(r, "epsActual"))
            est = _f(_first(r, "epsEstimated"))
            d = r.get("date")
            if actual is None or not d:
                continue
            surprise = ((actual - est) / abs(est) * 100) if (est not in (None, 0)) else None
            recs.append(EarningsRecord(date=d[:10], eps_estimate=est, eps_actual=actual,
                                       surprise_pct=round(surprise, 1) if surprise is not None else None))
        recs.sort(key=lambda x: x.date)
        payload.earnings = recs[-16:]
        if recs:
            payload.provenance["earnings"] = prov

    def _fill_news(self, payload, ticker, prov) -> None:
        # News is a paid endpoint on the free tier; degrade gracefully.
        data = self._get("news/stock", symbols=ticker, limit=12)
        if not isinstance(data, list):
            payload.warnings.append("News is not available on the FMP free tier.")
            return
        items = [
            NewsItem(title=n.get("title") or "(untitled)", publisher=n.get("site") or n.get("publisher"),
                     url=n.get("url"), published=n.get("publishedDate"),
                     summary=(n.get("text") or "")[:300] or None)
            for n in data if n.get("title")
        ]
        payload.news = items
        if items:
            payload.provenance["news"] = prov
