"""Normalized, provider-agnostic schema returned by every DataProvider.

Design notes:
- Every field is Optional and defaults to None. Missing data renders as "n/a" in the UI;
  it never crashes and is never invented (the grounding contract).
- Section-level `provenance` records where each block came from (source label, url, timestamp)
  so the UI can trace any figure back to its origin.
- Statement rows are plain numbers (not wrapped per-figure) to keep downstream math clean;
  their source is the statement-level provenance entry.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    source: str  # e.g. "yfinance" or "fixture (recorded sample)"
    source_url: str | None = None
    retrieved_at: str | None = None  # ISO8601 string


class CompanyProfile(BaseModel):
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    summary: str | None = None
    employees: int | None = None
    currency: str | None = None


class PricePoint(BaseModel):
    date: str  # ISO date
    close: float


class PriceData(BaseModel):
    current: float | None = None
    previous_close: float | None = None
    change_abs: float | None = None
    change_pct: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    market_cap: float | None = None
    beta: float | None = None
    # Daily close history (most recent last). Used for sparkline, events, move attribution.
    history: list[PricePoint] = Field(default_factory=list)


class KeyMetrics(BaseModel):
    pe_ttm: float | None = None
    forward_pe: float | None = None
    ev_ebitda: float | None = None
    ps: float | None = None
    pb: float | None = None
    dividend_yield: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    roic: float | None = None
    fcf_yield: float | None = None
    shares_outstanding: float | None = None
    total_debt: float | None = None
    total_cash: float | None = None
    ebitda: float | None = None


class IncomeRow(BaseModel):
    fiscal_year: int
    period_end: str | None = None
    revenue: float | None = None
    cost_of_revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None  # EBIT
    ebitda: float | None = None
    pretax_income: float | None = None
    tax_provision: float | None = None
    net_income: float | None = None
    interest_expense: float | None = None
    sga: float | None = None              # selling, general & admin (for Beneish)
    diluted_shares: float | None = None   # weighted-avg diluted shares (for EPS / dilution)


class BalanceRow(BaseModel):
    fiscal_year: int
    period_end: str | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    cash_and_equivalents: float | None = None
    total_debt: float | None = None
    stockholders_equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    working_capital: float | None = None
    retained_earnings: float | None = None   # for Altman Z
    receivables: float | None = None         # for Beneish DSRI
    ppe: float | None = None                 # net PP&E, for Beneish AQI/DEPI


class CashflowRow(BaseModel):
    fiscal_year: int
    period_end: str | None = None
    operating_cash_flow: float | None = None
    capital_expenditure: float | None = None  # negative convention
    free_cash_flow: float | None = None
    depreciation_amortization: float | None = None
    change_in_working_capital: float | None = None


class Financials(BaseModel):
    income: list[IncomeRow] = Field(default_factory=list)
    balance: list[BalanceRow] = Field(default_factory=list)
    cashflow: list[CashflowRow] = Field(default_factory=list)


class EarningsRecord(BaseModel):
    date: str  # ISO date of the report
    eps_estimate: float | None = None
    eps_actual: float | None = None
    surprise_pct: float | None = None


class NewsItem(BaseModel):
    title: str
    publisher: str | None = None
    url: str | None = None
    published: str | None = None  # ISO datetime
    summary: str | None = None


class CompanyPayload(BaseModel):
    """The single normalized object every provider returns from `retrieve(ticker)`."""

    ticker: str
    as_of: str  # ISO datetime the payload was assembled
    source: str  # provider label, e.g. "yfinance" / "fixture (recorded sample)"
    profile: CompanyProfile = Field(default_factory=CompanyProfile)
    price: PriceData = Field(default_factory=PriceData)
    key_metrics: KeyMetrics = Field(default_factory=KeyMetrics)
    financials: Financials = Field(default_factory=Financials)
    earnings: list[EarningsRecord] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    provenance: dict[str, Provenance] = Field(default_factory=dict)
    # Non-fatal warnings (e.g. "balance sheet unavailable") for transparency.
    warnings: list[str] = Field(default_factory=list)
