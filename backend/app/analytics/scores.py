"""Quality / health scores — pure functions over EDGAR financials. Each returns its components,
formula, and inputs so the number is fully reproducible. Degrades gracefully: a criterion or
score that lacks inputs is reported as None with a reason, never a crash.

Formulas:
  Piotroski F-Score (0–9): 9 binary tests of profitability, leverage/liquidity, efficiency.
  Altman Z-Score: Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5 (distress < 1.81, grey, safe > 2.99).
  Beneish M-Score: 8-variable earnings-manipulation model; M > −1.78 flags possible manipulation.
"""

from __future__ import annotations

from app.models.schemas import Financials
from app.utils.financial_math import cagr, safe_div


def _row(rows, i):
    return rows[i] if rows and len(rows) > i else None


def _gm(inc) -> float | None:
    return safe_div(inc.gross_profit, inc.revenue) if inc else None


# ----------------------------------------------------------------- Piotroski

def piotroski_f_score(fin: Financials) -> dict:
    """0–9. Higher = stronger fundamental momentum. Needs the latest two fiscal years."""
    i0, i1 = _row(fin.income, 0), _row(fin.income, 1)
    b0, b1 = _row(fin.balance, 0), _row(fin.balance, 1)
    c0 = _row(fin.cashflow, 0)
    crit: list[dict] = []

    def add(name: str, passed: bool | None, detail: str):
        crit.append({"name": name, "passed": passed, "detail": detail})

    roa0 = safe_div(i0.net_income, b0.total_assets) if (i0 and b0) else None
    roa1 = safe_div(i1.net_income, b1.total_assets) if (i1 and b1) else None
    add("Positive net income", (i0.net_income > 0) if (i0 and i0.net_income is not None) else None,
        "net income > 0")
    add("Positive operating cash flow", (c0.operating_cash_flow > 0) if (c0 and c0.operating_cash_flow is not None) else None,
        "OCF > 0")
    add("Rising ROA", (roa0 > roa1) if (roa0 is not None and roa1 is not None) else None,
        "ROA_t > ROA_{t-1} (NI / total assets)")
    add("Accruals (OCF > NI)", (c0.operating_cash_flow > i0.net_income) if (c0 and i0 and c0.operating_cash_flow is not None and i0.net_income is not None) else None,
        "operating cash flow > net income")
    lev0 = safe_div(b0.total_debt, b0.total_assets) if b0 else None
    lev1 = safe_div(b1.total_debt, b1.total_assets) if b1 else None
    add("Falling leverage", (lev0 < lev1) if (lev0 is not None and lev1 is not None) else None,
        "debt/assets_t < _{t-1}")
    cr0 = safe_div(b0.current_assets, b0.current_liabilities) if b0 else None
    cr1 = safe_div(b1.current_assets, b1.current_liabilities) if b1 else None
    add("Rising current ratio", (cr0 > cr1) if (cr0 is not None and cr1 is not None) else None,
        "current ratio_t > _{t-1}")
    add("No share dilution", (i0.diluted_shares <= i1.diluted_shares) if (i0 and i1 and i0.diluted_shares is not None and i1.diluted_shares is not None) else None,
        "diluted shares_t ≤ _{t-1}")
    gm0, gm1 = _gm(i0), _gm(i1)
    add("Rising gross margin", (gm0 > gm1) if (gm0 is not None and gm1 is not None) else None,
        "gross margin_t > _{t-1}")
    at0 = safe_div(i0.revenue, b0.total_assets) if (i0 and b0) else None
    at1 = safe_div(i1.revenue, b1.total_assets) if (i1 and b1) else None
    add("Rising asset turnover", (at0 > at1) if (at0 is not None and at1 is not None) else None,
        "revenue/assets_t > _{t-1}")

    computable = [c for c in crit if c["passed"] is not None]
    score = sum(1 for c in computable if c["passed"])
    return {
        "score": score,
        "max": 9,
        "computable": len(computable),
        "criteria": crit,
        "formula": "Sum of 9 binary tests (profitability ×4, leverage/liquidity ×3, efficiency ×2).",
        "interpretation": "8–9 strong · 0–2 weak" if len(computable) >= 7 else "insufficient data for a full score",
    }


# ----------------------------------------------------------------- Altman Z

def altman_z_score(fin: Financials, market_cap: float | None) -> dict:
    b0, i0 = _row(fin.balance, 0), _row(fin.income, 0)
    if not b0 or not i0 or not b0.total_assets:
        return {"z": None, "zone": None, "reason": "missing balance sheet / total assets"}
    ta = b0.total_assets
    x1 = safe_div(b0.working_capital, ta)
    x2 = safe_div(b0.retained_earnings, ta)
    x3 = safe_div(i0.operating_income, ta)
    mve = market_cap if market_cap else b0.stockholders_equity
    x4 = safe_div(mve, b0.total_liabilities)
    x5 = safe_div(i0.revenue, ta)
    parts = {"X1_wc_ta": x1, "X2_re_ta": x2, "X3_ebit_ta": x3, "X4_mve_tl": x4, "X5_sales_ta": x5}
    coef = {"X1_wc_ta": 1.2, "X2_re_ta": 1.4, "X3_ebit_ta": 3.3, "X4_mve_tl": 0.6, "X5_sales_ta": 1.0}
    if any(v is None for v in parts.values()):
        return {"z": None, "zone": None, "components": parts,
                "reason": "missing a component (e.g. retained earnings / liabilities)"}
    z = sum(coef[k] * parts[k] for k in parts)
    zone = "safe" if z > 2.99 else "distress" if z < 1.81 else "grey"
    return {
        "z": round(z, 2), "zone": zone, "components": parts,
        "used_market_cap": market_cap is not None,
        "formula": "Z = 1.2·WC/TA + 1.4·RE/TA + 3.3·EBIT/TA + 0.6·MVE/TL + 1.0·Sales/TA",
        "interpretation": "Z > 2.99 safe · 1.81–2.99 grey · < 1.81 distress"
                          + ("" if market_cap else " (book equity used for MVE — approximation)"),
    }


# ----------------------------------------------------------------- Beneish M

def beneish_m_score(fin: Financials) -> dict:
    i0, i1 = _row(fin.income, 0), _row(fin.income, 1)
    b0, b1 = _row(fin.balance, 0), _row(fin.balance, 1)
    c0 = _row(fin.cashflow, 0)
    if not all([i0, i1, b0, b1, c0]):
        return {"m": None, "flag": None, "reason": "needs two years of statements"}

    def ratio(n, d):
        return safe_div(n, d)

    dsri = safe_div(ratio(b0.receivables, i0.revenue), ratio(b1.receivables, i1.revenue))
    gmi = safe_div(_gm(i1), _gm(i0))
    aqi = safe_div(
        (1 - safe_div((b0.current_assets or 0) + (b0.ppe or 0), b0.total_assets)) if b0.total_assets else None,
        (1 - safe_div((b1.current_assets or 0) + (b1.ppe or 0), b1.total_assets)) if b1.total_assets else None,
    )
    sgi = safe_div(i0.revenue, i1.revenue)
    dep_rate0 = safe_div(fin.cashflow[0].depreciation_amortization, (fin.cashflow[0].depreciation_amortization or 0) + (b0.ppe or 0)) if (fin.cashflow and b0.ppe) else None
    dep_rate1 = safe_div(fin.cashflow[1].depreciation_amortization, (fin.cashflow[1].depreciation_amortization or 0) + (b1.ppe or 0)) if (len(fin.cashflow) > 1 and b1.ppe) else None
    depi = safe_div(dep_rate1, dep_rate0)
    sgai = safe_div(ratio(i0.sga, i0.revenue), ratio(i1.sga, i1.revenue))
    lev0 = safe_div((b0.total_liabilities), b0.total_assets)
    lev1 = safe_div((b1.total_liabilities), b1.total_assets)
    lvgi = safe_div(lev0, lev1)
    tata = safe_div((i0.net_income - c0.operating_cash_flow) if (i0.net_income is not None and c0.operating_cash_flow is not None) else None, b0.total_assets)

    comps = {"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi, "DEPI": depi,
             "SGAI": sgai, "LVGI": lvgi, "TATA": tata}
    missing = [k for k, v in comps.items() if v is None]
    if missing:
        return {"m": None, "flag": None, "components": comps,
                "reason": f"missing components: {', '.join(missing)} (needs receivables, PP&E, SG&A)"}
    m = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
         + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
    return {
        "m": round(m, 2), "flag": m > -1.78, "components": {k: round(v, 3) for k, v in comps.items()},
        "formula": "M = −4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI "
                   "− 0.172·SGAI + 4.679·TATA − 0.327·LVGI",
        "interpretation": "M > −1.78 flags possible earnings manipulation — scrutinise accruals.",
    }


# ----------------------------------------------------------------- growth / trends

def growth_and_trends(fin: Financials) -> dict:
    inc = fin.income
    cf = _row(fin.cashflow, 0)
    if not inc:
        return {}
    revs = [r.revenue for r in inc]          # newest-first
    n = len(inc) - 1
    rev_cagr = cagr(revs[-1], revs[0], n) if (n >= 1 and revs[-1] and revs[0]) else None

    def eps(r):
        return safe_div(r.net_income, r.diluted_shares)
    eps_series = [eps(r) for r in inc]
    eps_cagr = (cagr(eps_series[-1], eps_series[0], n)
                if (n >= 1 and eps_series[-1] and eps_series[0] and eps_series[-1] > 0) else None)

    op_margins = [safe_div(r.operating_income, r.revenue) for r in inc]
    margin_trend = ((op_margins[0] - op_margins[-1]) if (op_margins[0] is not None and op_margins[-1] is not None) else None)
    lev = [safe_div(b.total_debt, b.total_assets) for b in fin.balance]
    leverage_trend = ((lev[0] - lev[-1]) if (lev and lev[0] is not None and lev[-1] is not None) else None)
    cash_conversion = safe_div(cf.free_cash_flow, inc[0].net_income) if cf else None

    return {
        "revenue_cagr": rev_cagr,
        "eps_cagr": eps_cagr,
        "years": n,
        "operating_margin_latest": op_margins[0],
        "operating_margin_trend": margin_trend,
        "operating_margin_series": op_margins,
        "leverage_latest": lev[0] if lev else None,
        "leverage_trend": leverage_trend,
        "cash_conversion_fcf_ni": cash_conversion,
        "formula": {
            "cagr": "(end/begin)^(1/years) − 1",
            "margin_trend": "operating margin_latest − operating margin_oldest (Δ over the window)",
            "cash_conversion": "free cash flow / net income (latest year)",
        },
    }
