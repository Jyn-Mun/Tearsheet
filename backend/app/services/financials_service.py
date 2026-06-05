"""Builds the Financials tab: 3-5y income / balance / cash-flow tables with YoY growth,
each column labelled with its fiscal period. Pure transform over the normalized payload.
"""

from __future__ import annotations

from app.models.schemas import CompanyPayload
from app.utils.financial_math import yoy


def build_financials(payload: CompanyPayload) -> dict:
    inc = payload.financials.income
    bal = payload.financials.balance
    cf = payload.financials.cashflow

    rev = [r.revenue for r in inc]
    ni = [r.net_income for r in inc]
    ebit = [r.operating_income for r in inc]

    income_table = {
        "periods": [r.period_end for r in inc],
        "fiscal_years": [r.fiscal_year for r in inc],
        "rows": [
            _line("Revenue", [r.revenue for r in inc], growth=yoy(rev)),
            _line("Cost of revenue", [r.cost_of_revenue for r in inc]),
            _line("Gross profit", [r.gross_profit for r in inc]),
            _line("Operating income (EBIT)", ebit, growth=yoy(ebit)),
            _line("EBITDA", [r.ebitda for r in inc]),
            _line("Pretax income", [r.pretax_income for r in inc]),
            _line("Tax provision", [r.tax_provision for r in inc]),
            _line("Net income", ni, growth=yoy(ni)),
        ],
    }
    balance_table = {
        "periods": [r.period_end for r in bal],
        "fiscal_years": [r.fiscal_year for r in bal],
        "rows": [
            _line("Total assets", [r.total_assets for r in bal]),
            _line("Total liabilities", [r.total_liabilities for r in bal]),
            _line("Cash & equivalents", [r.cash_and_equivalents for r in bal]),
            _line("Total debt", [r.total_debt for r in bal]),
            _line("Stockholders' equity", [r.stockholders_equity for r in bal]),
            _line("Working capital", [r.working_capital for r in bal]),
        ],
    }
    cashflow_table = {
        "periods": [r.period_end for r in cf],
        "fiscal_years": [r.fiscal_year for r in cf],
        "rows": [
            _line("Operating cash flow", [r.operating_cash_flow for r in cf]),
            _line("Capital expenditure", [r.capital_expenditure for r in cf]),
            _line("Free cash flow", [r.free_cash_flow for r in cf]),
            _line("D&A", [r.depreciation_amortization for r in cf]),
            _line("Δ Working capital", [r.change_in_working_capital for r in cf]),
        ],
    }

    prov = payload.provenance.get("financials")
    return {
        "ticker": payload.ticker,
        "source": payload.source,
        "currency": payload.profile.currency,
        "income": income_table,
        "balance": balance_table,
        "cashflow": cashflow_table,
        "provenance": prov.model_dump() if prov else None,
        "warnings": payload.warnings,
    }


def _line(label: str, values: list, growth: list | None = None) -> dict:
    row = {"label": label, "values": values}
    if growth is not None:
        row["yoy"] = growth
    return row
