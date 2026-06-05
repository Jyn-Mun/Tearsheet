"""DCF numeric correctness: independent recompute, the WACC>g guard, and the reverse-DCF roundtrip."""

import math

from app.services import dcf_engine as eng


def test_projection_matches_independent_recompute(nvda):
    a, _ = eng.build_assumptions(nvda, risk_free=0.043)
    res = eng.run_dcf(a)
    # Recompute year 1 by hand from the assumptions.
    g1 = res["rows"][0]["growth"]
    rev1 = a.base_revenue * (1 + g1)
    ebit1 = rev1 * a.ebit_margin
    nopat1 = ebit1 * (1 - a.tax_rate)
    ufcf1 = nopat1 + rev1 * a.da_pct_rev - rev1 * a.capex_pct_rev - (rev1 - a.base_revenue) * a.nwc_pct_rev
    assert math.isclose(res["rows"][0]["revenue"], rev1, rel_tol=1e-9)
    assert math.isclose(res["rows"][0]["ufcf"], ufcf1, rel_tol=1e-9)
    # EV = sum of discounted FCFs + PV(TV)
    assert math.isclose(res["enterprise_value"], res["pv_explicit"] + res["pv_terminal_value"], rel_tol=1e-9)


def test_wacc_gt_g_guard_fires(nvda):
    a, _ = eng.build_assumptions(nvda, risk_free=0.043)
    bad = eng.run_dcf(a, wacc_override=0.02, terminal_growth_override=0.03)  # WACC < g
    assert bad["terminal_value"] is None
    assert bad["intrinsic_per_share"] is None
    assert bad["guard_wacc_gt_g"] is False


def test_reverse_dcf_roundtrips(nvda):
    a, _ = eng.build_assumptions(nvda, risk_free=0.043)
    target = nvda.price.current
    implied = eng.solve_implied_growth(a, target)
    assert implied is not None
    # Plugging the implied start growth back in should reproduce the target price within tolerance.
    intrinsic = eng.run_dcf(a, start_growth_override=implied)["intrinsic_per_share"]
    assert math.isclose(intrinsic, target, rel_tol=2e-3)


def test_sensitivity_matrix_shape(nvda):
    a, _ = eng.build_assumptions(nvda, risk_free=0.043)
    sens = eng.sensitivity_matrix(a)
    assert len(sens["waccs"]) == 7 and len(sens["growths"]) == 5
    assert len(sens["intrinsic"]) == 7 and all(len(r) == 5 for r in sens["intrinsic"])
