"""Assembles the /dcf response from the engine: assumptions, projection, outputs,
sensitivity matrix, reliability flags, and upside vs current price."""

from __future__ import annotations

from app.config import settings
from app.models.schemas import CompanyPayload
from app.services import dcf_engine as eng
from app.services.macro import risk_free_rate
from app.utils.financial_math import safe_div


def build_dcf(payload: CompanyPayload) -> dict:
    rf = risk_free_rate()
    a, warnings = eng.build_assumptions(payload, risk_free=rf)
    current = payload.price.current

    if a is None:
        return {
            "ticker": payload.ticker,
            "source": payload.source,
            "reliable": False,
            "flags": [{"level": "error", "msg": m} for m in warnings],
            "reason": "; ".join(warnings),
            "current_price": current,
            "warnings": payload.warnings,
        }

    result = eng.run_dcf(a)
    flags = eng.reliability_flags(payload, a)
    sens = eng.sensitivity_matrix(a)
    intrinsic = result["intrinsic_per_share"]
    upside = safe_div(
        (intrinsic - current) if (intrinsic is not None and current is not None) else None,
        current,
    )
    has_error = any(f["level"] == "error" for f in flags)

    return {
        "ticker": payload.ticker,
        "source": payload.source,
        "reliable": not has_error,
        "current_price": current,
        "assumptions": eng.assumptions_public(a),
        "assumption_notes": a.notes,
        "risk_free_source": "FRED DGS10" if rf is not None and settings.fred_api_key else "fallback 4.3%",
        "projection": result["rows"],
        "outputs": {
            "wacc": result["wacc"],
            "terminal_growth": result["terminal_growth"],
            "pv_explicit": result["pv_explicit"],
            "terminal_value": result["terminal_value"],
            "pv_terminal_value": result["pv_terminal_value"],
            "enterprise_value": result["enterprise_value"],
            "equity_value": result["equity_value"],
            "intrinsic_per_share": intrinsic,
            "upside_vs_price": upside,
        },
        "sensitivity": sens,
        "flags": flags,
        "warnings": payload.warnings + warnings,
        "disclaimer": "Model output with stated assumptions — not a recommendation or price target.",
    }
