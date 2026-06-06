"""Analytics orchestrator — assembles the full deterministic analytics for a ticker from EDGAR
fundamentals + yfinance prices. No paid APIs, no LLM. Every section degrades gracefully when an
input is missing. The optional LLM layer (analysis_service) sits on top for prose only.
"""

from __future__ import annotations

import numpy as np

from app.analytics import risk as R
from app.analytics import scores as S
from app.analytics.rules import run_rules
from app.models.schemas import CompanyPayload
from app.providers.base import DataProvider
from app.services import dcf_engine as eng
from app.services.event_analytics import build_events
from app.services.macro import risk_free_rate
from app.services.valuation_service import _SECTOR_PEERS, derive_roic
from app.utils.financial_math import safe_div


def _margins(fin) -> dict:
    """Margins straight from EDGAR financials — provider-independent (no price needed)."""
    if not fin.income:
        return {"gross": None, "operating": None, "net": None}
    r = fin.income[0]
    return {
        "gross": safe_div(r.gross_profit, r.revenue),
        "operating": safe_div(r.operating_income, r.revenue),
        "net": safe_div(r.net_income, r.revenue),
    }


def _op_margin(p) -> float | None:
    if p.financials.income:
        r = p.financials.income[0]
        return safe_div(r.operating_income, r.revenue)
    return None


def _percentile(value: float | None, peers: list[float]) -> float | None:
    pool = [v for v in peers + ([value] if value is not None else []) if v is not None]
    if value is None or len(pool) < 3:
        return None
    return float(100.0 * np.mean([1.0 if p <= value else 0.0 for p in pool]))


def _market_implied_growth(payload: CompanyPayload) -> dict:
    price = payload.price.current
    rf = risk_free_rate()
    a, _ = eng.build_assumptions(payload, risk_free=rf)
    if a is None or price is None:
        return {"available": False, "reason": "needs revenue + current price"}
    implied = eng.solve_implied_growth(a, price)
    return {
        "available": implied is not None,
        "implied_year1_revenue_growth": implied,
        "base_case_start_growth": a.start_growth,
        "terminal_growth": a.terminal_growth,
        "reading": (f"At today's price the market implies ~{implied*100:.0f}% near-term revenue growth "
                    f"(fading to {a.terminal_growth*100:.1f}%)." if implied is not None
                    else "No implied growth solves in a plausible range — price may rest on optionality."),
        "formula": "Solve the revenue growth that makes the DCF intrinsic value equal the current price.",
    }


def _peer_relative(payload: CompanyPayload, provider: DataProvider) -> dict:
    from app.providers.edgar_provider import EdgarProvider

    edgar = EdgarProvider()                 # margins are EDGAR-only — fetch fast, no yfinance backoff
    have_market = payload.price.current is not None  # only chase peer prices if Yahoo is actually up
    sector = payload.profile.sector or ""
    candidates = [t for t in _SECTOR_PEERS.get(sector, []) if t.upper() != payload.ticker.upper()][:5]
    peer_op_margin, peer_pe, peer_fcfy, rows = [], [], [], []
    for tk in candidates:
        try:
            pe = fcfy = None
            if have_market:
                p = provider.retrieve(tk)
                om = p.key_metrics.operating_margin if p.key_metrics.operating_margin is not None else _op_margin(p)
                pe, fcfy = p.key_metrics.pe_ttm, p.key_metrics.fcf_yield
                name = p.profile.name
            else:
                pf = edgar.retrieve(tk)
                om, name = _op_margin(pf), pf.profile.name
        except Exception:
            continue
        if om is not None:
            peer_op_margin.append(om)
        if pe is not None:
            peer_pe.append(pe)
        if fcfy is not None:
            peer_fcfy.append(fcfy)
        rows.append({"ticker": tk, "name": name, "operating_margin": om, "pe_ttm": pe, "fcf_yield": fcfy})
    km = payload.key_metrics
    subj_om = km.operating_margin if km.operating_margin is not None else _op_margin(payload)
    return {
        "peer_set": [r["ticker"] for r in rows],
        "note": "Sector/SIC-based approximation from a curated list.",
        "percentiles": {
            "operating_margin": _percentile(subj_om, peer_op_margin),
            "pe_ttm": _percentile(km.pe_ttm, peer_pe),
            "fcf_yield": _percentile(km.fcf_yield, peer_fcfy),
        },
        "peer_rows": rows,
        "method": "percentile = share of (peers + subject) at or below the subject's value.",
    }


def build_analytics(payload: CompanyPayload, provider: DataProvider) -> dict:
    fin = payload.financials
    km = payload.key_metrics
    closes = [p.close for p in payload.price.history]

    # --- scores (EDGAR) ---
    piotroski = S.piotroski_f_score(fin)
    altman = S.altman_z_score(fin, payload.price.market_cap)
    beneish = S.beneish_m_score(fin)
    trends = S.growth_and_trends(fin)

    # --- valuation (computed multiples already on key_metrics) + reverse DCF ---
    valuation = {
        "multiples": {
            "pe_ttm": km.pe_ttm, "ps": km.ps, "pb": km.pb, "ev_ebitda": km.ev_ebitda,
            "fcf_yield": km.fcf_yield, "roic": derive_roic(payload), "roe": km.roe,
            "dividend_yield": km.dividend_yield,
        },
        "margins": _margins(fin),
        "market_implied_growth": _market_implied_growth(payload),
        "formula": {
            "pe": "price / (net income / diluted shares)", "ps": "market cap / revenue",
            "pb": "market cap / (assets − liabilities)",
            "ev_ebitda": "(market cap + total debt − cash) / (operating income + D&A)",
            "roic": "NOPAT / (debt + equity − cash)",
        },
    }

    # --- price / risk (yfinance) ---
    rf = risk_free_rate() or 0.043
    idx_closes = None
    try:
        idx_closes = [p.close for p in provider.price_history("SPY")] or None
    except Exception:
        idx_closes = None
    price_risk = R.all_metrics(closes, idx_closes, rf=rf) if len(closes) >= 20 else {
        "available": False, "reason": "no price history from Yahoo (rate-limit/network)"}

    # --- events (reuse the event-analytics module) ---
    events = build_events(payload)
    eb = events.get("earnings_behaviour", {})

    # --- peers ---
    peers = _peer_relative(payload, provider)

    # --- rules engine context ---
    mig = valuation["market_implied_growth"]
    ctx = {
        "f_score": piotroski["score"] if piotroski["computable"] >= 6 else None,
        "altman_z": altman.get("z"), "altman_zone": altman.get("zone"),
        "beneish_m": beneish.get("m"), "beneish_flag": beneish.get("flag"),
        "fcf_yield": km.fcf_yield,
        "implied_growth": mig.get("implied_year1_revenue_growth"),
        "hist_rev_cagr": trends.get("revenue_cagr"),
        "margin_trend": trends.get("operating_margin_trend"),
        "leverage_trend": trends.get("leverage_trend"),
        "cash_conversion": trends.get("cash_conversion_fcf_ni"),
        "rsi": (price_risk.get("rsi_14") or {}).get("value") if isinstance(price_risk, dict) else None,
        "max_drawdown": (price_risk.get("max_drawdown") or {}).get("value") if isinstance(price_risk, dict) else None,
        "beat_rate": eb.get("beat_rate"), "post_up_rate": (eb.get("post_window") or {}).get("hit_rate"),
        "events_n": eb.get("n_reports"),
        "pe_percentile": peers["percentiles"].get("pe_ttm"),
    }
    interpretation = run_rules(ctx)

    return {
        "ticker": payload.ticker,
        "source": payload.source,
        "currency": payload.profile.currency,
        "valuation": valuation,
        "scores": {"piotroski_f": piotroski, "altman_z": altman, "beneish_m": beneish, "trends": trends},
        "price_risk": price_risk,
        "events": eb,
        "peers": peers,
        "interpretation": interpretation,
        "warnings": payload.warnings,
        "disclaimer": "Deterministic analytics from free sources (SEC EDGAR + Yahoo). "
                      "Research tool, not advice — no buy/sell/hold.",
    }
