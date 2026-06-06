"""Deterministic analytics: scores, risk metrics, rules — all reproducible, no network."""

import numpy as np

from app.analytics import risk as R
from app.analytics import scores as S
from app.analytics.rules import run_rules
from app.analytics.service import _percentile
from app.models.schemas import BalanceRow, CashflowRow, Financials, IncomeRow


def _fin():
    """Two clean years where year-0 improves on year-1 across the board (high Piotroski)."""
    inc = [
        IncomeRow(fiscal_year=2025, revenue=1000, cost_of_revenue=400, gross_profit=600,
                  operating_income=250, ebitda=300, pretax_income=240, tax_provision=48,
                  net_income=190, sga=150, diluted_shares=100),
        IncomeRow(fiscal_year=2024, revenue=850, cost_of_revenue=370, gross_profit=480,
                  operating_income=190, ebitda=235, pretax_income=185, tax_provision=40,
                  net_income=140, sga=140, diluted_shares=102),
    ]
    bal = [
        BalanceRow(fiscal_year=2025, total_assets=2000, total_liabilities=700, cash_and_equivalents=300,
                   total_debt=200, stockholders_equity=1300, current_assets=900, current_liabilities=300,
                   working_capital=600, retained_earnings=800, receivables=120, ppe=500),
        BalanceRow(fiscal_year=2024, total_assets=1800, total_liabilities=720, cash_and_equivalents=240,
                   total_debt=260, stockholders_equity=1080, current_assets=760, current_liabilities=320,
                   working_capital=440, retained_earnings=640, receivables=110, ppe=480),
    ]
    cf = [
        CashflowRow(fiscal_year=2025, operating_cash_flow=240, capital_expenditure=-60,
                    free_cash_flow=180, depreciation_amortization=50),
        CashflowRow(fiscal_year=2024, operating_cash_flow=175, capital_expenditure=-55,
                    free_cash_flow=120, depreciation_amortization=45),
    ]
    return Financials(income=inc, balance=bal, cashflow=cf)


def test_piotroski_high_quality():
    f = S.piotroski_f_score(_fin())
    assert f["computable"] == 9                 # all inputs present
    assert f["score"] >= 8                       # year-0 improves on year-1 broadly
    assert any(c["name"] == "No share dilution" and c["passed"] for c in f["criteria"])


def test_altman_safe_zone():
    z = S.altman_z_score(_fin(), market_cap=5000)
    assert z["z"] is not None and z["zone"] == "safe"
    # Z = 1.2*WC/TA + 1.4*RE/TA + 3.3*EBIT/TA + 0.6*MVE/TL + 1.0*Sales/TA
    expect = 1.2*600/2000 + 1.4*800/2000 + 3.3*250/2000 + 0.6*5000/700 + 1.0*1000/2000
    assert abs(z["z"] - round(expect, 2)) < 0.05


def test_beneish_computes_and_low():
    m = S.beneish_m_score(_fin())
    assert m["m"] is not None
    assert m["flag"] is False  # clean books → below the -1.78 threshold


def test_growth_and_trends():
    g = S.growth_and_trends(_fin())
    assert abs(g["revenue_cagr"] - (1000 / 850 - 1)) < 1e-9   # 1y CAGR = simple growth
    assert g["operating_margin_trend"] > 0                     # 25% vs 22.4%
    assert abs(g["cash_conversion_fcf_ni"] - 180 / 190) < 1e-9


def test_risk_metrics_deterministic():
    # Steady +0.1%/day series → positive Sharpe, ~0 drawdown.
    closes = list(100 * np.cumprod(np.full(300, 1.001)))
    assert R.annualized_vol(closes)["value"] is not None
    assert R.sharpe(closes)["value"] > 0
    assert R.max_drawdown(closes)["value"] >= -1e-6           # monotonic up → no drawdown
    rsi = R.rsi(closes)["value"]
    assert rsi == 100.0                                       # only gains → RSI 100
    assert R.moving_averages(closes)["golden_cross"] is True


def test_percentile_rank():
    assert _percentile(60, [10, 40, 50]) == 100.0            # subject highest
    assert _percentile(5, [10, 40, 50]) == 25.0             # subject lowest of 4


def test_rules_engine_fires_and_cites_inputs():
    ctx = {"f_score": 8, "fcf_yield": 0.05, "implied_growth": 0.05, "hist_rev_cagr": 0.10,
           "altman_zone": "safe", "beneish_flag": False, "margin_trend": 0.03}
    out = run_rules(ctx)
    ids = {f["id"] for f in out["fired"]}
    assert "quality_at_undemanding_price" in ids
    assert "strong_fundamental_momentum" in ids
    assert "margin_expansion" in ids
    # every fired rule cites the inputs that triggered it
    q = next(f for f in out["fired"] if f["id"] == "quality_at_undemanding_price")
    assert set(q["inputs"]) == {"f_score", "fcf_yield", "implied_growth", "hist_rev_cagr"}


def test_rules_caution_distress_and_manipulation():
    out = run_rules({"altman_zone": "distress", "altman_z": 1.2, "beneish_flag": True, "beneish_m": -1.0})
    ids = {f["id"] for f in out["fired"]}
    assert "distress_risk" in ids and "earnings_manipulation_flag" in ids
