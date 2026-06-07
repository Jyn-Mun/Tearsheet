"""FreeProvider — live data from Yahoo Finance via yfinance (no API key, no personal info).

yfinance is unofficial and can rate-limit or change shape, so every access is wrapped in
try/except, NaNs are coerced to None, and missing sections add a warning rather than raise.
Successful payloads are cached on disk (TTL) to limit calls to Yahoo.
"""

from __future__ import annotations

import logging
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

log = logging.getLogger("tearsheet")

# yfinance logs its own noisy errors directly ("possibly delisted; no price data found", currency
# repair tracebacks, etc.) even when we catch the exception. Silence its logger so a rate-limited
# fetch produces ONE concise line from us, not a wall of yfinance output.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

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


_PRICE_TTL = 60 * 5  # ~5 minutes for prices/quotes (delayed/EOD anyway)


def _hist_period() -> str:
    """yfinance `period` string honoring the configured history cap (memory guard)."""
    from app.config import settings

    days = settings.max_history_days
    if days <= 35:
        return "1mo"
    if days <= 100:
        return "3mo"
    if days <= 200:
        return "6mo"
    if days <= 400:
        return "1y"
    if days <= 760:
        return "2y"
    return "5y"


class FreeProvider(DataProvider):
    name = "yfinance"

    # One Ticker object per symbol, reused across calls (process-lifetime).
    _tickers: dict[str, Any] = {}

    def _ticker(self, symbol: str):
        import yfinance as yf

        if symbol not in self._tickers:
            # Route through a curl_cffi browser-impersonating session when available — helps with
            # Yahoo's bot checks. This is the LOCAL-DEV/fallback path only (prod uses a keyed API).
            session = None
            try:
                from curl_cffi import requests as cffi_requests

                session = cffi_requests.Session(impersonate="chrome")
            except Exception:
                session = None
            self._tickers[symbol] = yf.Ticker(symbol, session=session) if session else yf.Ticker(symbol)
        return self._tickers[symbol]

    @staticmethod
    def _yf(fn, *, tries: int = 3, base: float = 1.5):
        """Call a yfinance accessor with backoff on transient/rate-limit errors."""
        import time

        last = None
        for i in range(tries):
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(base * (2 ** i))
        if last:
            raise last

    def retrieve(self, ticker: str) -> CompanyPayload:
        ticker = ticker.upper().strip()
        cached_payload = cache.get(f"payload:{ticker}", _CACHE_TTL)
        if cached_payload is not None:
            return CompanyPayload.model_validate(cached_payload)

        payload = self._build(ticker)
        cache.set(f"payload:{ticker}", payload.model_dump())
        return payload

    # --------------------------------------------------- market-data only (for the hybrid)

    def market_data(self, ticker: str) -> dict:
        """Just price + market metrics + news from yfinance (no financials) — for EDGAR+Yahoo.
        Cached ~5 min on disk. Returns {"price": PriceData, "news": [NewsItem], "warnings": [...]}.
        """
        from app.cache_policy import read_ttl, should_fetch_live

        ticker = ticker.upper().strip()
        cached = cache.get(f"yf:market:{ticker}", read_ttl(_PRICE_TTL))
        if cached is not None:
            return {
                "price": PriceData.model_validate(cached["price"]),
                "news": [NewsItem.model_validate(n) for n in cached["news"]],
                "warnings": cached.get("warnings", []),
            }
        if not should_fetch_live():
            return {"price": PriceData(), "news": [], "warnings": ["price not yet pre-fetched"]}
        payload = CompanyPayload(ticker=ticker, as_of=_now(), source=self.name)
        prov = Provenance(source=self.name, source_url=f"https://finance.yahoo.com/quote/{ticker}",
                          retrieved_at=_now())
        t = self._ticker(ticker)
        info: dict[str, Any] = {}
        try:
            info = self._yf(lambda: t.info) or {}
        except Exception as e:  # noqa: BLE001
            payload.warnings.append(f"market data unavailable (Yahoo): {type(e).__name__}")
        self._fill_price(payload, t, info, prov)
        self._fill_news(payload, t, prov)
        if not payload.news:
            self._fill_news_rss(payload, ticker)
        out = {"price": payload.price, "news": payload.news, "warnings": payload.warnings}
        cache.set(f"yf:market:{ticker}", {
            "price": payload.price.model_dump(),
            "news": [n.model_dump() for n in payload.news],
            "warnings": payload.warnings,
        })
        return out

    def price_history(self, ticker: str) -> list[PricePoint]:
        from app.cache_policy import read_ttl, should_fetch_live

        ticker = ticker.upper().strip()
        cached = cache.get(f"yf:hist:{ticker}", read_ttl(_PRICE_TTL))
        if cached is not None:
            return [PricePoint(**p) for p in cached]
        if not should_fetch_live():
            return []
        pts: list[PricePoint] = []
        try:
            t = self._ticker(ticker)
            hist = self._yf(lambda: t.history(period=_hist_period(), interval="1d"))
            # Guard hard: only iterate a non-empty DataFrame that actually has a Close column.
            # On a rate-limited/delisted response yfinance can hand back empty or unexpected data
            # (this is the source of the internal "'str' object has no attribute 'name'" crash) —
            # we must never call .date()/.items() on that.
            if hist is None or getattr(hist, "empty", True) or "Close" not in getattr(hist, "columns", []):
                raise ValueError("empty/unexpected history")
            # Pull only the Close column, then drop the whole DataFrame so it doesn't sit in
            # RAM for the rest of the call.
            closes = hist["Close"].dropna()
            del hist
            for idx, v in closes.items():
                fv = _f(v)
                # idx must be a Timestamp (has .date()); skip anything yfinance returns that isn't.
                if fv is not None and hasattr(idx, "date"):
                    pts.append(PricePoint(date=idx.date().isoformat(), close=fv))
            del closes
        except Exception as e:  # noqa: BLE001
            log.warning("yfinance history unavailable for %s (%s); serving empty", ticker, type(e).__name__)
            pts = []
        # Cache even an empty result (short TTL) so a blocked Yahoo doesn't re-trigger backoff
        # on every render; it'll retry after the 5-min window.
        cache.set(f"yf:hist:{ticker}", [p.model_dump() for p in pts])
        return pts

    def _fill_news_rss(self, payload, ticker: str) -> None:
        """Free finance RSS fallback when yfinance returns no headlines."""
        import xml.etree.ElementTree as ET

        import httpx

        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        try:
            r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            items = []
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                if not title:
                    continue
                items.append(NewsItem(title=title, publisher="Yahoo Finance RSS",
                                      url=(it.findtext("link") or None),
                                      published=(it.findtext("pubDate") or None), summary=None))
                if len(items) >= 10:
                    break
            if items:
                payload.news = items
                payload.provenance["news"] = Provenance(source="Yahoo Finance RSS", source_url=url,
                                                        retrieved_at=_now())
        except Exception:
            pass

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
            hist = t.history(period=_hist_period(), interval="1d")
            # Same hard guard as price_history(): a rate-limited/delisted response can be empty or
            # malformed, which trips yfinance's internal ".name" crash — never iterate it blindly.
            if hist is None or getattr(hist, "empty", True) or "Close" not in getattr(hist, "columns", []):
                raise ValueError("empty/unexpected history")
            closes = hist["Close"].dropna()
            del hist  # keep only the Close series; release the full OHLCV frame
            history = [
                PricePoint(date=idx.date().isoformat(), close=_f(v))
                for idx, v in closes.items()
                if _f(v) is not None and hasattr(idx, "date")
            ]
            del closes
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

        # We've extracted every value we need into `fin` (small dataclasses). Drop the heavy
        # pandas DataFrames now so they're garbage-collected instead of lingering for the rest of
        # the request — statement frames can be several MB each.
        del inc, bal, cf
        import gc

        gc.collect()

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
