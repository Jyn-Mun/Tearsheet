"""FreeProvider — live data from Yahoo Finance via yfinance (no API key, no personal info).

yfinance is unofficial and can rate-limit or change shape, so every access is wrapped in
try/except, NaNs are coerced to None, and missing sections add a warning rather than raise.
Successful payloads are cached on disk (TTL) to limit calls to Yahoo.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.models.schemas import (
    BalanceRow,
    CashflowRow,
    CompanyPayload,
    CompanyProfile,
    EarningsRecord,
    Financials,
    IncomeRow,
    KeyMetrics,
    NewsItem,
    PriceData,
    PricePoint,
    Provenance,
)
from app.providers.base import DataProvider
from app.utils import cache

_CACHE_TTL = 60 * 30  # 30 minutes; Yahoo data is delayed/EOD anyway.


def _f(x: Any) -> float | None:
    """Coerce to float, mapping NaN / None / junk to None."""
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(df, *names: str):
    """First matching row (Series) from a statement DataFrame, trying label variants."""
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def _cell(series, col) -> float | None:
    if series is None:
        return None
    try:
        return _f(series.get(col))
    except Exception:
        return None


class FreeProvider(DataProvider):
    name = "yfinance"

    def retrieve(self, ticker: str) -> CompanyPayload:
        ticker = ticker.upper().strip()
        cached_payload = cache.get(f"payload:{ticker}", _CACHE_TTL)
        if cached_payload is not None:
            return CompanyPayload.model_validate(cached_payload)

        payload = self._build(ticker)
        cache.set(f"payload:{ticker}", payload.model_dump())
        return payload

    # ------------------------------------------------------------------ build

    def _build(self, ticker: str) -> CompanyPayload:
        import yfinance as yf  # imported lazily so the app boots without network

        payload = CompanyPayload(ticker=ticker, as_of=_now(), source=self.name)
        yurl = f"https://finance.yahoo.com/quote/{ticker}"
        prov = Provenance(source=self.name, source_url=yurl, retrieved_at=_now())

        t = yf.Ticker(ticker)

        info: dict[str, Any] = {}
        try:
            info = t.info or {}
        except Exception as e:  # noqa: BLE001
            payload.warnings.append(f"profile/metrics unavailable: {type(e).__name__}")

        if info:
            self._fill_profile(payload, info, prov)
            self._fill_metrics(payload, info, prov)

        self._fill_price(payload, t, info, prov)
        self._fill_financials(payload, t, prov)
        self._fill_earnings(payload, t, prov)
        self._fill_news(payload, t, prov)

        if not info and not payload.financials.income and payload.price.current is None:
            payload.warnings.append(
                "No data returned for this ticker — it may be unsupported, delisted, "
                "or Yahoo is rate-limiting. Try again shortly."
            )
        return payload

    # ------------------------------------------------------------ subsections

    def _fill_profile(self, payload, info, prov) -> None:
        payload.profile = CompanyProfile(
            name=info.get("longName") or info.get("shortName"),
            exchange=info.get("exchange"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            country=info.get("country"),
            summary=info.get("longBusinessSummary"),
            employees=info.get("fullTimeEmployees"),
            currency=info.get("currency") or info.get("financialCurrency"),
        )
        payload.provenance["profile"] = prov

    def _fill_metrics(self, payload, info, prov) -> None:
        payload.key_metrics = KeyMetrics(
            pe_ttm=_f(info.get("trailingPE")),
            forward_pe=_f(info.get("forwardPE")),
            ev_ebitda=_f(info.get("enterpriseToEbitda")),
            ps=_f(info.get("priceToSalesTrailing12Months")),
            pb=_f(info.get("priceToBook")),
            dividend_yield=_f(info.get("dividendYield")),
            gross_margin=_f(info.get("grossMargins")),
            operating_margin=_f(info.get("operatingMargins")),
            net_margin=_f(info.get("profitMargins")),
            roe=_f(info.get("returnOnEquity")),
            fcf_yield=None,  # derived in valuation service from FCF / market cap
            shares_outstanding=_f(info.get("sharesOutstanding")),
            total_debt=_f(info.get("totalDebt")),
            total_cash=_f(info.get("totalCash")),
            ebitda=_f(info.get("ebitda")),
        )
        payload.provenance["key_metrics"] = prov

    def _fill_price(self, payload, t, info, prov) -> None:
        current = _f(info.get("currentPrice")) or _f(info.get("regularMarketPrice"))
        prev = _f(info.get("previousClose")) or _f(info.get("regularMarketPreviousClose"))
        history: list[PricePoint] = []
        try:
            hist = t.history(period="2y", interval="1d")
            if hist is not None and not hist.empty:
                closes = hist["Close"].dropna()
                history = [
                    PricePoint(date=idx.date().isoformat(), close=_f(v))
                    for idx, v in closes.items()
                    if _f(v) is not None
                ]
                if current is None and history:
                    current = history[-1].close
                if prev is None and len(history) >= 2:
                    prev = history[-2].close
        except Exception as e:  # noqa: BLE001
            payload.warnings.append(f"price history unavailable: {type(e).__name__}")

        change_abs = (current - prev) if (current is not None and prev is not None) else None
        change_pct = (change_abs / prev) if (change_abs is not None and prev) else None

        payload.price = PriceData(
            current=current,
            previous_close=prev,
            change_abs=change_abs,
            change_pct=change_pct,
            fifty_two_week_high=_f(info.get("fiftyTwoWeekHigh")),
            fifty_two_week_low=_f(info.get("fiftyTwoWeekLow")),
            market_cap=_f(info.get("marketCap")),
            beta=_f(info.get("beta")),
            history=history,
        )
        payload.provenance["price"] = prov

    def _fill_financials(self, payload, t, prov) -> None:
        try:
            inc = t.financials
            bal = t.balance_sheet
            cf = t.cashflow
        except Exception as e:  # noqa: BLE001
            payload.warnings.append(f"financial statements unavailable: {type(e).__name__}")
            return

        fin = Financials()

        # --- income statement ---
        rev = _row(inc, "Total Revenue", "Revenue", "Operating Revenue")
        cogs = _row(inc, "Cost Of Revenue", "Cost of Revenue", "Reconciled Cost Of Revenue")
        gp = _row(inc, "Gross Profit")
        oi = _row(inc, "Operating Income", "EBIT", "Total Operating Income As Reported")
        ebitda = _row(inc, "EBITDA", "Normalized EBITDA")
        pretax = _row(inc, "Pretax Income", "Pre Tax Income")
        tax = _row(inc, "Tax Provision", "Income Tax Expense")
        ni = _row(inc, "Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations")
        intexp = _row(inc, "Interest Expense", "Interest Expense Non Operating")
        if inc is not None and not inc.empty:
            for col in inc.columns:
                fin.income.append(
                    IncomeRow(
                        fiscal_year=col.year,
                        period_end=col.date().isoformat(),
                        revenue=_cell(rev, col),
                        cost_of_revenue=_cell(cogs, col),
                        gross_profit=_cell(gp, col),
                        operating_income=_cell(oi, col),
                        ebitda=_cell(ebitda, col),
                        pretax_income=_cell(pretax, col),
                        tax_provision=_cell(tax, col),
                        net_income=_cell(ni, col),
                        interest_expense=_cell(intexp, col),
                    )
                )

        # --- balance sheet ---
        ta = _row(bal, "Total Assets")
        tl = _row(bal, "Total Liabilities Net Minority Interest", "Total Liabilities")
        cash = _row(bal, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
        debt = _row(bal, "Total Debt")
        eq = _row(bal, "Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest")
        ca = _row(bal, "Current Assets", "Total Current Assets")
        cl = _row(bal, "Current Liabilities", "Total Current Liabilities")
        wc = _row(bal, "Working Capital")
        if bal is not None and not bal.empty:
            for col in bal.columns:
                ca_v, cl_v = _cell(ca, col), _cell(cl, col)
                wc_v = _cell(wc, col)
                if wc_v is None and ca_v is not None and cl_v is not None:
                    wc_v = ca_v - cl_v
                fin.balance.append(
                    BalanceRow(
                        fiscal_year=col.year,
                        period_end=col.date().isoformat(),
                        total_assets=_cell(ta, col),
                        total_liabilities=_cell(tl, col),
                        cash_and_equivalents=_cell(cash, col),
                        total_debt=_cell(debt, col),
                        stockholders_equity=_cell(eq, col),
                        current_assets=ca_v,
                        current_liabilities=cl_v,
                        working_capital=wc_v,
                    )
                )

        # --- cash flow ---
        ocf = _row(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
        capex = _row(cf, "Capital Expenditure", "Purchase Of PPE")
        fcf = _row(cf, "Free Cash Flow")
        da = _row(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion")
        cwc = _row(cf, "Change In Working Capital")
        if cf is not None and not cf.empty:
            for col in cf.columns:
                ocf_v, capex_v = _cell(ocf, col), _cell(capex, col)
                fcf_v = _cell(fcf, col)
                if fcf_v is None and ocf_v is not None and capex_v is not None:
                    fcf_v = ocf_v + capex_v  # capex is negative in yfinance
                fin.cashflow.append(
                    CashflowRow(
                        fiscal_year=col.year,
                        period_end=col.date().isoformat(),
                        operating_cash_flow=ocf_v,
                        capital_expenditure=capex_v,
                        free_cash_flow=fcf_v,
                        depreciation_amortization=_cell(da, col),
                        change_in_working_capital=_cell(cwc, col),
                    )
                )

        payload.financials = fin
        if fin.income or fin.balance or fin.cashflow:
            payload.provenance["financials"] = prov

    def _fill_earnings(self, payload, t, prov) -> None:
        try:
            ed = t.get_earnings_dates(limit=24)
        except Exception:
            try:
                ed = t.earnings_dates
            except Exception as e:  # noqa: BLE001
                payload.warnings.append(f"earnings history unavailable: {type(e).__name__}")
                return
        if ed is None or getattr(ed, "empty", True):
            return
        est_col = next((c for c in ed.columns if "Estimate" in c), None)
        act_col = next((c for c in ed.columns if "Reported" in c), None)
        sur_col = next((c for c in ed.columns if "Surprise" in c), None)
        records: list[EarningsRecord] = []
        for idx, row in ed.iterrows():
            actual = _f(row.get(act_col)) if act_col else None
            if actual is None:
                continue  # only past reports with an actual
            try:
                date_s = idx.date().isoformat()
            except Exception:
                continue
            records.append(
                EarningsRecord(
                    date=date_s,
                    eps_estimate=_f(row.get(est_col)) if est_col else None,
                    eps_actual=actual,
                    surprise_pct=_f(row.get(sur_col)) if sur_col else None,
                )
            )
        records.sort(key=lambda r: r.date)
        payload.earnings = records
        if records:
            payload.provenance["earnings"] = prov

    def _fill_news(self, payload, t, prov) -> None:
        try:
            raw = t.news or []
        except Exception as e:  # noqa: BLE001
            payload.warnings.append(f"news unavailable: {type(e).__name__}")
            return
        items: list[NewsItem] = []
        for n in raw[:12]:
            # New yfinance shape nests under "content"; old shape is flat.
            content = n.get("content") if isinstance(n, dict) else None
            if content:
                url = None
                cu = content.get("canonicalUrl") or content.get("clickThroughUrl")
                if isinstance(cu, dict):
                    url = cu.get("url")
                prov_obj = content.get("provider") or {}
                items.append(
                    NewsItem(
                        title=content.get("title") or "(untitled)",
                        publisher=prov_obj.get("displayName") if isinstance(prov_obj, dict) else None,
                        url=url,
                        published=content.get("pubDate") or content.get("displayTime"),
                        summary=content.get("summary"),
                    )
                )
            elif isinstance(n, dict) and n.get("title"):
                ts = n.get("providerPublishTime")
                published = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    if isinstance(ts, (int, float))
                    else None
                )
                items.append(
                    NewsItem(
                        title=n["title"],
                        publisher=n.get("publisher"),
                        url=n.get("link"),
                        published=published,
                        summary=None,
                    )
                )
        payload.news = items
        if items:
            payload.provenance["news"] = prov
