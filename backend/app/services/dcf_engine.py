"""Transparent unlevered-FCF DCF (PRD §7). Every assumption and intermediate line is exposed.

The engine is pure math over an explicit `DcfAssumptions` object; a separate builder derives
sensible defaults from the normalized payload. A reverse-DCF solver (used by the interpretation
module) reuses the same `run_dcf` to find the growth/margin the current price implies.

Guardrails: WACC must exceed terminal g; unprofitable / negative-FCF / financial-sector names
are flagged unreliable rather than printing a confident number.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from app.models.schemas import CompanyPayload
from app.utils.financial_math import (
    cagr,
    discount_factor,
    gordon_terminal_value,
    linear_fade,
    safe_div,
)

# --- defaults / assumptions documented inline (no magic numbers) ---
DEFAULT_HORIZON = 10
DEFAULT_TERMINAL_GROWTH = 0.025  # 2.5% — roughly long-run nominal GDP
DEFAULT_ERP = 0.05  # equity risk premium assumption (stated)
DEFAULT_RISK_FREE = 0.043  # fallback 10y if FRED key absent (documented)
DEFAULT_BETA = 1.0
DEFAULT_TAX_RATE = 0.21
DEFAULT_DEBT_SPREAD = 0.015  # over rf when interest/debt not derivable


@dataclass
class DcfAssumptions:
    horizon: int
    base_revenue: float
    start_growth: float          # year-1 growth, fades to terminal_growth
    terminal_growth: float
    ebit_margin: float           # held flat at trailing margin
    tax_rate: float
    da_pct_rev: float
    capex_pct_rev: float
    nwc_pct_rev: float           # incremental NWC as % of revenue *change*
    # WACC build (all inputs explicit)
    risk_free: float
    beta: float
    erp: float
    pretax_cost_of_debt: float
    equity_value: float          # market cap (E)
    debt_value: float            # total debt (D)
    net_debt: float
    shares_outstanding: float
    # provenance / notes for each assumption
    notes: dict = field(default_factory=dict)

    # ---- derived WACC pieces ----
    @property
    def cost_of_equity(self) -> float:
        return self.risk_free + self.beta * self.erp

    @property
    def after_tax_cost_of_debt(self) -> float:
        return self.pretax_cost_of_debt * (1 - self.tax_rate)

    @property
    def equity_weight(self) -> float:
        denom = self.equity_value + self.debt_value
        return self.equity_value / denom if denom else 1.0

    @property
    def debt_weight(self) -> float:
        return 1.0 - self.equity_weight

    @property
    def wacc(self) -> float:
        return (
            self.equity_weight * self.cost_of_equity
            + self.debt_weight * self.after_tax_cost_of_debt
        )


def run_dcf(a: DcfAssumptions, wacc_override: float | None = None,
            terminal_growth_override: float | None = None,
            ebit_margin_override: float | None = None,
            start_growth_override: float | None = None) -> dict:
    """Run the projection and return EV, equity value, intrinsic/share, and every line.

    Overrides let the sensitivity grid and reverse-DCF solver perturb single inputs without
    rebuilding assumptions.
    """
    wacc = wacc_override if wacc_override is not None else a.wacc
    g = terminal_growth_override if terminal_growth_override is not None else a.terminal_growth
    margin = ebit_margin_override if ebit_margin_override is not None else a.ebit_margin
    start_g = start_growth_override if start_growth_override is not None else a.start_growth

    growth_path = linear_fade(start_g, g, a.horizon)
    rows = []
    prev_rev = a.base_revenue
    pv_sum = 0.0
    for yr in range(1, a.horizon + 1):
        g_t = growth_path[yr - 1]
        rev = prev_rev * (1 + g_t)
        ebit = rev * margin
        nopat = ebit * (1 - a.tax_rate)
        da = rev * a.da_pct_rev
        capex = rev * a.capex_pct_rev  # positive magnitude
        d_nwc = (rev - prev_rev) * a.nwc_pct_rev
        ufcf = nopat + da - capex - d_nwc
        df = discount_factor(wacc, yr)
        pv = ufcf * df
        pv_sum += pv
        rows.append({
            "year": yr,
            "growth": g_t,
            "revenue": rev,
            "ebit": ebit,
            "nopat": nopat,
            "da": da,
            "capex": -capex,
            "delta_nwc": -d_nwc,
            "ufcf": ufcf,
            "discount_factor": df,
            "pv_fcf": pv,
        })
        prev_rev = rev

    final_fcf = rows[-1]["ufcf"]
    tv = gordon_terminal_value(final_fcf, g, wacc)
    pv_tv = tv * discount_factor(wacc, a.horizon) if tv is not None else None
    ev = pv_sum + (pv_tv or 0.0) if tv is not None else None
    equity = (ev - a.net_debt) if ev is not None else None
    intrinsic = safe_div(equity, a.shares_outstanding) if equity is not None else None

    return {
        "rows": rows,
        "wacc": wacc,
        "terminal_growth": g,
        "pv_explicit": pv_sum,
        "terminal_value": tv,
        "pv_terminal_value": pv_tv,
        "enterprise_value": ev,
        "equity_value": equity,
        "intrinsic_per_share": intrinsic,
        "guard_wacc_gt_g": wacc > g,
    }


# --------------------------------------------------------------- defaults builder


def _avg_pct_of_revenue(numerators: list[float | None], revenues: list[float | None]) -> float | None:
    ratios = [
        n / r for n, r in zip(numerators, revenues)
        if n is not None and r not in (None, 0)
    ]
    return sum(ratios) / len(ratios) if ratios else None


def build_assumptions(payload: CompanyPayload, risk_free: float | None = None) -> tuple[DcfAssumptions | None, list[str]]:
    """Derive default assumptions from trailing actuals. Returns (assumptions, warnings).
    Returns (None, reasons) when there isn't enough data to model.
    """
    warnings: list[str] = []
    inc = payload.financials.income
    cf = payload.financials.cashflow
    bal = payload.financials.balance
    if not inc or inc[0].revenue is None:
        return None, ["No revenue data available — cannot build a DCF."]

    revenues = [r.revenue for r in inc]  # newest first
    base_revenue = revenues[0]

    # Historical revenue CAGR (oldest→newest)
    years_span = len(revenues) - 1
    hist_cagr = cagr(revenues[-1], revenues[0], years_span) if years_span >= 1 else None
    if hist_cagr is None:
        hist_cagr = 0.05
        warnings.append("Historical CAGR not derivable; defaulted start growth to 5%.")
    # cap an explosive trailing CAGR for a defensible start point
    start_growth = max(min(hist_cagr, 0.35), -0.10)

    # Trailing EBIT margin
    ebit_margin = safe_div(inc[0].operating_income, base_revenue)
    if ebit_margin is None or ebit_margin <= 0:
        warnings.append("Operating margin missing/negative — DCF unreliable for this name.")
        ebit_margin = ebit_margin or 0.0

    # Tax rate from latest filing, else default
    tax_rate = safe_div(inc[0].tax_provision, inc[0].pretax_income)
    if tax_rate is None or tax_rate < 0 or tax_rate > 0.5:
        tax_rate = DEFAULT_TAX_RATE

    # D&A / capex / NWC as % of revenue from trailing actuals
    da_pct = _avg_pct_of_revenue([c.depreciation_amortization for c in cf], revenues) or 0.03
    capex_pct = _avg_pct_of_revenue(
        [abs(c.capital_expenditure) if c.capital_expenditure is not None else None for c in cf],
        revenues,
    ) or 0.04
    nwc_pct = 0.03  # incremental NWC as % of revenue change — conservative default
    if bal and bal[0].working_capital is not None and base_revenue:
        wc_ratio = bal[0].working_capital / base_revenue
        nwc_pct = max(min(wc_ratio, 0.25), 0.0)

    # WACC inputs
    rf = risk_free if risk_free is not None else DEFAULT_RISK_FREE
    beta = payload.price.beta or DEFAULT_BETA
    market_cap = payload.price.market_cap or (
        (payload.price.current or 0) * (payload.key_metrics.shares_outstanding or 0)
    )
    total_debt = (bal[0].total_debt if bal else None) or payload.key_metrics.total_debt or 0.0
    cash = (bal[0].cash_and_equivalents if bal else None) or payload.key_metrics.total_cash or 0.0
    net_debt = total_debt - cash

    # Pre-tax cost of debt: interest / debt if available, else rf + spread
    pretax_kd = safe_div(inc[0].interest_expense, total_debt)
    if pretax_kd is None or pretax_kd <= 0 or pretax_kd > 0.2:
        pretax_kd = rf + DEFAULT_DEBT_SPREAD

    shares = payload.key_metrics.shares_outstanding or safe_div(market_cap, payload.price.current)
    if not shares:
        return None, ["Shares outstanding unavailable — cannot derive per-share value."]

    a = DcfAssumptions(
        horizon=DEFAULT_HORIZON,
        base_revenue=base_revenue,
        start_growth=start_growth,
        terminal_growth=DEFAULT_TERMINAL_GROWTH,
        ebit_margin=ebit_margin,
        tax_rate=tax_rate,
        da_pct_rev=da_pct,
        capex_pct_rev=capex_pct,
        nwc_pct_rev=nwc_pct,
        risk_free=rf,
        beta=beta,
        erp=DEFAULT_ERP,
        pretax_cost_of_debt=pretax_kd,
        equity_value=market_cap,
        debt_value=total_debt,
        net_debt=net_debt,
        shares_outstanding=shares,
        notes={
            "start_growth": f"trailing {years_span}y revenue CAGR (capped), fading to terminal",
            "terminal_growth": "assumption ~2.5% (long-run nominal GDP); g < WACC enforced",
            "ebit_margin": "held at trailing operating margin",
            "tax_rate": "latest effective rate" if tax_rate != DEFAULT_TAX_RATE else "default 21%",
            "risk_free": "FRED DGS10 if key present, else 4.3% fallback",
            "beta": "Yahoo beta if available, else 1.0",
            "erp": "assumption 5.0%",
            "cost_of_debt": "interest/total debt if derivable, else rf + 1.5% spread",
            "da_pct_rev": f"{da_pct:.1%} of revenue (trailing avg)",
            "capex_pct_rev": f"{capex_pct:.1%} of revenue (trailing avg)",
            "nwc_pct_rev": f"{nwc_pct:.1%} of revenue change",
        },
    )
    return a, warnings


# --------------------------------------------------------------- reliability + grid


def reliability_flags(payload: CompanyPayload, a: DcfAssumptions) -> list[dict]:
    flags = []
    if a.wacc <= a.terminal_growth:
        flags.append({"level": "error", "msg": "WACC ≤ terminal growth — model invalid (guard fired)."})
    if a.ebit_margin <= 0:
        flags.append({"level": "error", "msg": "Company is unprofitable on an operating basis — DCF unreliable."})
    cf = payload.financials.cashflow
    if cf and cf[0].free_cash_flow is not None and cf[0].free_cash_flow < 0:
        flags.append({"level": "warn", "msg": "Latest free cash flow is negative — projection is speculative."})
    if (payload.profile.sector or "") == "Financial Services":
        flags.append({"level": "warn", "msg": "Financial-sector business — an unlevered FCF DCF is not the right tool; treat with caution."})
    return flags


def sensitivity_matrix(a: DcfAssumptions) -> dict:
    """Intrinsic value across WACC (±1.5% in 0.5% steps) × terminal growth (1.5%–3.5%)."""
    base_wacc = a.wacc
    waccs = [round(base_wacc + d, 4) for d in (-0.015, -0.010, -0.005, 0.0, 0.005, 0.010, 0.015)]
    growths = [0.015, 0.020, 0.025, 0.030, 0.035]
    grid = []
    for w in waccs:
        row = []
        for g in growths:
            res = run_dcf(a, wacc_override=w, terminal_growth_override=g)
            row.append(res["intrinsic_per_share"])
        grid.append(row)
    return {"waccs": waccs, "growths": growths, "intrinsic": grid}


def solve_implied_growth(a: DcfAssumptions, target_price: float,
                         lo: float = -0.5, hi: float = 1.0, iters: int = 60) -> float | None:
    """Reverse DCF: bisect the start growth (fading to terminal) so intrinsic == target_price.
    Returns the implied year-1 revenue growth, or None if no solution in range.
    """
    def intrinsic_at(start_g: float) -> float | None:
        return run_dcf(a, start_growth_override=start_g)["intrinsic_per_share"]

    f_lo, f_hi = intrinsic_at(lo), intrinsic_at(hi)
    if f_lo is None or f_hi is None:
        return None
    # need target bracketed
    if (f_lo - target_price) * (f_hi - target_price) > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        f_mid = intrinsic_at(mid)
        if f_mid is None:
            return None
        if abs(f_mid - target_price) < target_price * 1e-4:
            return mid
        if (f_lo - target_price) * (f_mid - target_price) <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def assumptions_public(a: DcfAssumptions) -> dict:
    """Serializable view of assumptions incl. derived WACC pieces (for the UI/eval)."""
    d = asdict(a)
    d.update({
        "cost_of_equity": a.cost_of_equity,
        "after_tax_cost_of_debt": a.after_tax_cost_of_debt,
        "equity_weight": a.equity_weight,
        "debt_weight": a.debt_weight,
        "wacc": a.wacc,
    })
    return d
