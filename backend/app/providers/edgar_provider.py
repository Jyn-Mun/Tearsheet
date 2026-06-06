"""EdgarProvider — live fundamentals from SEC EDGAR (free, no key, unlimited, authoritative).

EDGAR is the system of record: real figures straight from 10-K/10-Q XBRL. No IP blocks, no daily
limit. The trade-off: EDGAR is **filings-only** — it has NO price, market cap, multiples, news, or
price history (those aren't in SEC filings). Those fields come back as None (n/a) and the warnings
say so; price-dependent panels (multiples, events, move attribution) degrade gracefully.

Endpoints (all require a descriptive User-Agent with a contact — see settings.sec_user_agent):
  - ticker→CIK : https://www.sec.gov/files/company_tickers.json
  - profile    : https://data.sec.gov/submissions/CIK##########.json
  - XBRL facts : https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models.schemas import (
    BalanceRow, CashflowRow, CompanyPayload, CompanyProfile, Financials,
    IncomeRow, KeyMetrics, PriceData, Provenance,
)
from app.providers.base import DataProvider
from app.utils import cache

_TICKERS_TTL = 60 * 60 * 24        # daily — the ticker→CIK map rarely changes
_FACTS_TTL = 60 * 60 * 12         # 12h — filings don't change intraday
_BASE_SUB = "https://data.sec.gov"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(url: str) -> Any:
    import httpx

    try:
        r = httpx.get(url, headers={"User-Agent": settings.sec_user_agent,
                                    "Accept-Encoding": "gzip, deflate"}, timeout=20.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# Coarse SIC → sector (EDGAR has SIC, not GICS sectors). Best-effort labelling.
def _sector_from_sic(sic: str | None) -> str | None:
    if not sic or not sic.isdigit():
        return None
    n = int(sic)
    if 1000 <= n < 1500 or 2900 <= n < 3000:
        return "Energy"
    if 6000 <= n < 6800:
        return "Financial Services"
    if 8000 <= n < 8100 or 2830 <= n < 2840:
        return "Healthcare"
    if n in (3571, 3572, 3674) or 7370 <= n < 7380:
        return "Technology"
    if 4800 <= n < 4900:
        return "Communication Services"
    if 4900 <= n < 5000:
        return "Utilities"
    if 5200 <= n < 6000:
        return "Consumer Cyclical"
    if 2000 <= n < 2100 or 2080 <= n < 2090:
        return "Consumer Defensive"
    if 1500 <= n < 4000:
        return "Industrials"
    return None


# Field → candidate XBRL tag names, per taxonomy. First match wins.
_US_TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "tax": ["IncomeTaxExpenseBenefit"],
    "interest": ["InterestExpense", "InterestExpenseNonoperating"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
           "DepreciationAndAmortization"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "lt_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "cur_debt": ["LongTermDebtCurrent", "DebtCurrent"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
}

_IFRS_TAGS = {
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers"],
    "cogs": ["CostOfSales"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["ProfitLossFromOperatingActivities", "OperatingProfitLoss"],
    "net_income": ["ProfitLoss"],
    "pretax": ["ProfitLossBeforeTax"],
    "tax": ["IncomeTaxExpenseContinuingOperations", "IncomeTaxExpenseBenefit"],
    "interest": ["FinanceCosts", "InterestExpense"],
    "da": ["DepreciationAndAmortisationExpense",
           "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "cash": ["CashAndCashEquivalents"],
    "equity": ["Equity", "EquityAttributableToOwnersOfParent"],
    "current_assets": ["CurrentAssets"],
    "current_liabilities": ["CurrentLiabilities"],
    "lt_debt": ["NoncurrentBorrowings", "BorrowingsNoncurrent"],
    "cur_debt": ["CurrentBorrowings", "BorrowingsCurrent"],
    "ocf": ["CashFlowsFromUsedInOperatingActivities"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
}


class EdgarProvider(DataProvider):
    name = "SEC EDGAR (filings)"

    def __init__(self) -> None:
        self._cik_map: dict[str, str] | None = None

    # ----------------------------------------------------------- cik map

    def _load_cik_map(self) -> dict[str, str]:
        if self._cik_map is not None:
            return self._cik_map
        cached = cache.get("edgar:tickers", _TICKERS_TTL)
        if cached is None:
            data = _get(_TICKERS_URL) or {}
            cached = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                      for v in data.values()} if data else {}
            if cached:
                cache.set("edgar:tickers", cached)
        self._cik_map = cached
        return cached

    # ----------------------------------------------------------- retrieve

    def retrieve(self, ticker: str) -> CompanyPayload:
        ticker = ticker.upper().strip()
        payload = CompanyPayload(ticker=ticker, as_of=_now(), source=self.name)
        payload.price = PriceData()  # EDGAR has no market data
        payload.warnings.append(
            "EDGAR provides SEC-filing fundamentals only — no live price, market cap, multiples, "
            "news, or price history. Price-dependent panels show n/a."
        )

        cik = self._load_cik_map().get(ticker)
        if not cik:
            payload.warnings.insert(0, f"No SEC CIK found for {ticker} (US-listed filers only).")
            return payload

        cached = cache.get(f"edgar:facts:{cik}", _FACTS_TTL)
        facts = cached if cached is not None else _get(
            f"{_BASE_SUB}/api/xbrl/companyfacts/CIK{cik}.json")
        if facts and cached is None:
            cache.set(f"edgar:facts:{cik}", facts)
        sub = _get(f"{_BASE_SUB}/submissions/CIK{cik}.json") or {}

        prov = Provenance(source=self.name,
                          source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                          retrieved_at=_now())
        self._fill_profile(payload, sub, facts, prov)
        if facts:
            self._fill_financials(payload, facts, prov)
            self._fill_shares(payload, facts, prov)
        else:
            payload.warnings.insert(0, f"No XBRL company facts available for {ticker}.")
        return payload

    def _fill_profile(self, payload, sub, facts, prov) -> None:
        name = sub.get("name") or (facts or {}).get("entityName")
        exchanges = sub.get("exchanges") or []
        payload.profile = CompanyProfile(
            name=name,
            exchange=exchanges[0] if exchanges else None,
            sector=_sector_from_sic(sub.get("sic")),
            industry=sub.get("sicDescription"),
            country="United States",
            summary=(f"SIC {sub.get('sic')} · {sub.get('sicDescription')}. "
                     "Profile from SEC submissions; figures from XBRL filings." if sub.get("sic") else None),
            employees=None,
            currency="USD",
        )
        payload.key_metrics = KeyMetrics()
        if name:
            payload.provenance["profile"] = prov

    # ----------------------------------------------------------- XBRL extraction

    def _annual(self, facts: dict, tags: list[str], taxonomy: str, forms: tuple[str, ...]) -> dict[int, float]:
        """{fiscal_year: value} for the first matching tag, annual figures.

        Keyed by the PERIOD-END year (XBRL's `fy` reflects the filing, not the period, so the same
        value recurs across filings as a comparative). Durational facts (income/cash-flow) are
        restricted to ~full-year periods; instant facts (balance) use the period end. `forms` is the
        annual report form(s): ("10-K",) for US domestic, ("20-F",) for foreign filers. Prefer the
        annual form, then latest-filed.
        """
        from datetime import date

        def ok_form(e: dict) -> bool:
            return any(str(e.get("form", "")).startswith(f) for f in forms)

        def rank(e: dict) -> tuple:
            return (ok_form(e), str(e.get("filed", "")))

        # Merge ACROSS all candidate tags (a company can switch tags between years — e.g. NVDA
        # reports recent revenue under `Revenues` but older years under
        # `RevenueFromContractWithCustomerExcludingAssessedTax`). For each fiscal year, keep the
        # entry with the best rank (annual form, then latest-filed) regardless of which tag it's in.
        node_root = facts.get("facts", {}).get(taxonomy, {})
        best: dict[int, dict] = {}
        for tag in tags:
            node = node_root.get(tag)
            if not node:
                continue
            units = node.get("units", {})
            arr = units.get("USD") or units.get("GBP") or units.get("EUR") or (
                next(iter(units.values()), []) if units else [])
            for e in arr:
                if not ok_form(e):
                    continue  # annual report only (excludes interim 10-Q / 6-K)
                end = e.get("end")
                if not end:
                    continue
                start = e.get("start")
                if start:  # durational — keep ~full-year periods only
                    try:
                        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                    except ValueError:
                        continue
                    if days < 350 or days > 380:
                        continue
                try:
                    fy = int(end[:4])
                except ValueError:
                    continue
                if fy not in best or rank(e) > rank(best[fy]):
                    best[fy] = e
        return {fy: best[fy]["val"] for fy in best}

    def _fill_financials(self, payload, facts, prov) -> None:
        # US domestic filers report us-gaap in 10-K; foreign filers report ifrs-full in 20-F.
        root = facts.get("facts", {})
        if root.get("us-gaap"):
            tax, forms, t = "us-gaap", ("10-K",), _US_TAGS
        elif root.get("ifrs-full"):
            tax, forms, t = "ifrs-full", ("20-F",), _IFRS_TAGS
            payload.warnings.insert(0, "Foreign filer (IFRS / 20-F) — some line items may map "
                                       "differently or be unavailable.")
        else:
            payload.warnings.insert(0, "No us-gaap or ifrs-full XBRL facts available.")
            return

        # Detect the reporting currency from the actual units (foreign filers use GBP/EUR/…).
        cur = self._detect_currency(root.get(tax, {}), t)
        if cur:
            payload.profile.currency = cur

        def g(field: str) -> dict:
            return self._annual(facts, t.get(field, []), tax, forms)

        rev, cogs, gp, oi, ni = g("revenue"), g("cogs"), g("gross_profit"), g("operating_income"), g("net_income")
        pretax, taxp, interest, da = g("pretax"), g("tax"), g("interest"), g("da")
        assets, liab, cash, equity = g("assets"), g("liabilities"), g("cash"), g("equity")
        cur_assets, cur_liab = g("current_assets"), g("current_liabilities")
        lt_debt, cur_debt = g("lt_debt"), g("cur_debt")
        ocf, capex = g("ocf"), g("capex")
        tax = taxp  # keep downstream variable name

        years = sorted(set(rev) | set(ni) | set(assets), reverse=True)[:5]
        fin = Financials()
        for fy in years:
            ebit = oi.get(fy)
            da_v = da.get(fy)
            fin.income.append(IncomeRow(
                fiscal_year=fy, period_end=None,
                revenue=rev.get(fy), cost_of_revenue=cogs.get(fy), gross_profit=gp.get(fy),
                operating_income=ebit, ebitda=(ebit + da_v) if (ebit is not None and da_v is not None) else None,
                pretax_income=pretax.get(fy), tax_provision=tax.get(fy), net_income=ni.get(fy),
                interest_expense=interest.get(fy),
            ))
            ca, cl = cur_assets.get(fy), cur_liab.get(fy)
            debt = None
            if lt_debt.get(fy) is not None or cur_debt.get(fy) is not None:
                debt = (lt_debt.get(fy) or 0) + (cur_debt.get(fy) or 0)
            fin.balance.append(BalanceRow(
                fiscal_year=fy, period_end=None,
                total_assets=assets.get(fy), total_liabilities=liab.get(fy),
                cash_and_equivalents=cash.get(fy), total_debt=debt,
                stockholders_equity=equity.get(fy), current_assets=ca, current_liabilities=cl,
                working_capital=(ca - cl) if (ca is not None and cl is not None) else None,
            ))
            capex_v = capex.get(fy)
            ocf_v = ocf.get(fy)
            fcf = (ocf_v - capex_v) if (ocf_v is not None and capex_v is not None) else None
            fin.cashflow.append(CashflowRow(
                fiscal_year=fy, period_end=None,
                operating_cash_flow=ocf_v,
                capital_expenditure=(-capex_v) if capex_v is not None else None,  # SEC reports magnitude
                free_cash_flow=fcf, depreciation_amortization=da.get(fy), change_in_working_capital=None,
            ))
        payload.financials = fin
        # derive total_debt/total_cash into key_metrics for the DCF
        if fin.balance:
            payload.key_metrics.total_debt = fin.balance[0].total_debt
            payload.key_metrics.total_cash = fin.balance[0].cash_and_equivalents
        if fin.income or fin.balance:
            payload.provenance["financials"] = prov

    @staticmethod
    def _detect_currency(tax_root: dict, tagmap: dict) -> str | None:
        known = {"USD", "GBP", "EUR", "JPY", "CHF", "CAD", "AUD", "CNY", "HKD", "SEK"}
        for field in ("revenue", "assets", "net_income"):
            for tag in tagmap.get(field, []):
                node = tax_root.get(tag)
                if node:
                    for u in node.get("units", {}):
                        if u in known:
                            return u
        return None

    def _fill_shares(self, payload, facts, prov) -> None:
        dei = facts.get("facts", {}).get("dei", {})
        node = dei.get("EntityCommonStockSharesOutstanding")
        if not node:
            return
        arr = node.get("units", {}).get("shares", [])
        latest = None
        for e in arr:
            if latest is None or str(e.get("end", "")) > str(latest.get("end", "")):
                latest = e
        if latest:
            payload.key_metrics.shares_outstanding = float(latest["val"])
