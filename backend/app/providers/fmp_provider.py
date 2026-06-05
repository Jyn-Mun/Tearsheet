"""FMPProvider — live data from Financial Modeling Prep (free API key).

Why this exists: yfinance/Yahoo rate-limits by IP and is unusable from some networks (e.g. shared
sandboxes). FMP authenticates per-key, so a free key gives reliable real data from anywhere. This
is the DataProvider "swap point" in action — a new class implementing the same interface, no
changes to any service or to the UI.

Free tier: real quotes, full income/balance/cash-flow statements (3-5y), TTM ratios + key metrics,
2y daily price history, earnings surprises, and company news. ~250 calls/day — so we cache
aggressively (30-min TTL). Every call is defensive: failures add a warning and degrade to n/a,
never crash, never invent.
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

_CACHE_TTL = 60 * 30  # 30 min — stay well under the free daily call budget.


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
        if k in d and d[k] is not None:
            return d[k]
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FMPProvider(DataProvider):
    name = "Financial Modeling Prep (live)"

    def __init__(self) -> None:
        self._key = settings.fmp_api_key
        self._base = settings.fmp_base_url

    # --------------------------------------------------------------- http

    def _get(self, path: str, params: dict | None = None) -> Any:
        import httpx

        params = dict(params or {})
        params["apikey"] = self._key
        try:
            r = httpx.get(f"{self._base}/{path}", params=params, timeout=15.0)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "Error Message" in data:
                return None
            return data
        except Exception:
            return None

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

    def _build(self, payload: CompanyPayload, ticker: str) -> None:
        url = f"https://financialmodelingprep.com/financial-summary/{ticker}"
        prov = Provenance(source=self.name, source_url=url, retrieved_at=_now())

        quote = self._get(f"quote/{ticker}")
        profile = self._get(f"profile/{ticker}")
        q = quote[0] if isinstance(quote, list) and quote else {}
        pf = profile[0] if isinstance(profile, list) and profile else {}

        if not q and not pf:
            payload.warnings.append(
                f"No live data returned for {ticker} (check the ticker, your FMP key, or daily limit)."
            )

        self._fill_profile(payload, pf, q, prov)
        self._fill_price_metrics(payload, q, pf, ticker, prov)
        self._fill_statements(payload, ticker, prov)
        self._fill_earnings(payload, ticker, prov)
        self._fill_news(payload, ticker, prov)

    def _fill_profile(self, payload, pf, q, prov) -> None:
        payload.profile = CompanyProfile(
            name=_first(pf, "companyName") or _first(q, "name"),
            exchange=_first(pf, "exchangeShortName") or _first(q, "exchange"),
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
        # Price history (2y daily) — also the source for sparkline / events / move attribution.
        history: list[PricePoint] = []
        hist = self._get(f"historical-price-full/{ticker}", {"timeseries": 504})
        rows = hist.get("historical") if isinstance(hist, dict) else None
        if isinstance(rows, list):
            for row in reversed(rows):  # FMP returns newest-first; we want oldest-first
                c = _f(row.get("close"))
                d = row.get("date")
                if c is not None and d:
                    history.append(PricePoint(date=d[:10], close=c))

        current = _f(_first(q, "price"))
        prev = _f(_first(q, "previousClose"))
        if current is None and history:
            current = history[-1].close
        change_abs = _f(_first(q, "change"))
        if change_abs is None and current is not None and prev is not None:
            change_abs = current - prev
        chg_pct = _f(_first(q, "changesPercentage"))
        change_pct = (chg_pct / 100.0) if chg_pct is not None else (
            (change_abs / prev) if (change_abs is not None and prev) else None)

        payload.price = PriceData(
            current=current,
            previous_close=prev,
            change_abs=change_abs,
            change_pct=change_pct,
            fifty_two_week_high=_f(_first(q, "yearHigh")),
            fifty_two_week_low=_f(_first(q, "yearLow")),
            market_cap=_f(_first(q, "marketCap")) or _f(_first(pf, "mktCap")),
            beta=_f(_first(pf, "beta")),
            history=history,
        )
        payload.provenance["price"] = prov

        # TTM ratios + key metrics
        ratios = self._get(f"ratios-ttm/{ticker}")
        km = self._get(f"key-metrics-ttm/{ticker}")
        r = ratios[0] if isinstance(ratios, list) and ratios else {}
        k = km[0] if isinstance(km, list) and km else {}
        payload.key_metrics = KeyMetrics(
            pe_ttm=_f(_first(q, "pe")) or _f(_first(r, "peRatioTTM", "priceEarningsRatioTTM")),
            forward_pe=None,
            ev_ebitda=_f(_first(k, "enterpriseValueOverEBITDATTM") or _first(r, "enterpriseValueMultipleTTM")),
            ps=_f(_first(r, "priceToSalesRatioTTM", "priceSalesRatioTTM")),
            pb=_f(_first(r, "priceToBookRatioTTM", "priceBookValueRatioTTM")),
            dividend_yield=_f(_first(r, "dividendYieldTTM", "dividendYielTTM")),
            gross_margin=_f(_first(r, "grossProfitMarginTTM")),
            operating_margin=_f(_first(r, "operatingProfitMarginTTM")),
            net_margin=_f(_first(r, "netProfitMarginTTM")),
            roe=_f(_first(r, "returnOnEquityTTM")),
            roic=_f(_first(k, "roicTTM")),
            fcf_yield=_f(_first(k, "freeCashFlowYieldTTM")),
            shares_outstanding=_f(_first(q, "sharesOutstanding")) or _f(_first(k, "sharesOutstandingTTM")),
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )
        if r or k or q:
            payload.provenance["key_metrics"] = prov

    def _fill_statements(self, payload, ticker, prov) -> None:
        inc = self._get(f"income-statement/{ticker}", {"period": "annual", "limit": 5})
        bal = self._get(f"balance-sheet-statement/{ticker}", {"period": "annual", "limit": 5})
        cf = self._get(f"cash-flow-statement/{ticker}", {"period": "annual", "limit": 5})
        fin = Financials()

        if isinstance(inc, list):
            for r in inc:
                fin.income.append(IncomeRow(
                    fiscal_year=_int(r.get("calendarYear")) or _yr(r.get("date")),
                    period_end=(r.get("date") or "")[:10] or None,
                    revenue=_f(r.get("revenue")), cost_of_revenue=_f(r.get("costOfRevenue")),
                    gross_profit=_f(r.get("grossProfit")), operating_income=_f(r.get("operatingIncome")),
                    ebitda=_f(r.get("ebitda")), pretax_income=_f(r.get("incomeBeforeTax")),
                    tax_provision=_f(r.get("incomeTaxExpense")), net_income=_f(r.get("netIncome")),
                    interest_expense=_f(r.get("interestExpense")),
                ))
        if isinstance(bal, list):
            for r in bal:
                ca, cl = _f(r.get("totalCurrentAssets")), _f(r.get("totalCurrentLiabilities"))
                fin.balance.append(BalanceRow(
                    fiscal_year=_int(r.get("calendarYear")) or _yr(r.get("date")),
                    period_end=(r.get("date") or "")[:10] or None,
                    total_assets=_f(r.get("totalAssets")), total_liabilities=_f(r.get("totalLiabilities")),
                    cash_and_equivalents=_f(r.get("cashAndCashEquivalents")), total_debt=_f(r.get("totalDebt")),
                    stockholders_equity=_f(r.get("totalStockholdersEquity")),
                    current_assets=ca, current_liabilities=cl,
                    working_capital=(ca - cl) if (ca is not None and cl is not None) else None,
                ))
        if isinstance(cf, list):
            for r in cf:
                fin.cashflow.append(CashflowRow(
                    fiscal_year=_int(r.get("calendarYear")) or _yr(r.get("date")),
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
        data = self._get(f"earnings-surprises/{ticker}")
        if not isinstance(data, list):
            return
        recs: list[EarningsRecord] = []
        for r in data:
            actual = _f(_first(r, "actualEarningResult"))
            est = _f(_first(r, "estimatedEarning"))
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
        data = self._get("stock_news", {"tickers": ticker, "limit": 12})
        if not isinstance(data, list):
            return
        items = [
            NewsItem(title=n.get("title") or "(untitled)", publisher=n.get("site"),
                     url=n.get("url"), published=(n.get("publishedDate") or None),
                     summary=(n.get("text") or "")[:300] or None)
            for n in data if n.get("title")
        ]
        payload.news = items
        if items:
            payload.provenance["news"] = prov


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
