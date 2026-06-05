"""Module 4 — Move Explanation Engine (PRD Addendum §E).

Decomposes a session's price move into market / sector / idiosyncratic components, classifies it
systematic vs sector vs stock-specific, matches same-day news/macro as CANDIDATE causes (flagged
correlation-not-causation), classifies the driver transient/structural/ambiguous, and reports
thesis impact against the falsifiers from /analysis. Never predicts the path, never advises.
"""

from __future__ import annotations

from app.models.schemas import CompanyPayload
from app.providers.base import DataProvider

_INDEX = "SPY"
_SECTOR_ETF = {
    "Technology": "SMH",  # semis proxy in fixtures; real run can map sector→ETF
    "Semiconductors": "SMH",
}


def _returns(closes: list[float]) -> list[float]:
    out = []
    for i in range(1, len(closes)):
        if closes[i] is None or closes[i - 1] in (None, 0):
            out.append(0.0)
        else:
            out.append(closes[i] / closes[i - 1] - 1)
    return out


def _aligned_returns(a_dates, a_closes, b_dates, b_closes):
    """Daily returns for series A and B aligned on common dates."""
    b_map = {d: c for d, c in zip(b_dates, b_closes)}
    common = [(d, a_closes[i]) for i, d in enumerate(a_dates) if d in b_map]
    a_r, b_r = [], []
    for i in range(1, len(common)):
        d0, a0 = common[i - 1]
        d1, a1 = common[i]
        b0, b1 = b_map[d0], b_map[d1]
        if a0 and b0:
            a_r.append(a1 / a0 - 1)
            b_r.append(b1 / b0 - 1)
    return a_r, b_r


def _beta(stock_r: list[float], index_r: list[float]) -> float | None:
    import numpy as np

    if len(stock_r) < 30:
        return None
    s, m = np.array(stock_r), np.array(index_r)
    var = m.var()
    if var == 0:
        return None
    return float(np.cov(s, m)[0, 1] / var)


def _return_on(dates: list[str], closes: list[float], target_date: str | None) -> tuple[str | None, float | None]:
    """Return (date, session return) for target_date (default: last session)."""
    if len(closes) < 2:
        return None, None
    idx = len(closes) - 1
    if target_date:
        match = [i for i, d in enumerate(dates) if d == target_date]
        if match:
            idx = match[0]
    if idx == 0 or closes[idx] is None or closes[idx - 1] in (None, 0):
        return (dates[idx] if dates else None), None
    return dates[idx], closes[idx] / closes[idx - 1] - 1


def build_move(payload: CompanyPayload, provider: DataProvider, target_date: str | None = None) -> dict:
    dates = [p.date for p in payload.price.history]
    closes = [p.close for p in payload.price.history]
    if len(closes) < 30:
        return {"ticker": payload.ticker, "available": False,
                "reason": "insufficient price history to attribute a move", "warnings": payload.warnings}

    move_date, total = _return_on(dates, closes, target_date)
    if total is None:
        return {"ticker": payload.ticker, "available": False,
                "reason": "no price move available for that date", "warnings": payload.warnings}

    index = provider.retrieve(_INDEX)
    sector_tkr = _SECTOR_ETF.get(payload.profile.sector or "") or _SECTOR_ETF.get(payload.profile.industry or "")
    sector = provider.retrieve(sector_tkr) if sector_tkr else None

    # Beta of stock vs index over the aligned history.
    s_r, m_r = _aligned_returns(dates, closes, [p.date for p in index.price.history],
                                [p.close for p in index.price.history])
    beta = _beta(s_r, m_r) or (payload.price.beta or 1.0)

    idx_date, index_ret = _return_on([p.date for p in index.price.history],
                                     [p.close for p in index.price.history], move_date)
    market_component = beta * index_ret if index_ret is not None else None

    sector_component = None
    if sector is not None:
        _, sector_ret = _return_on([p.date for p in sector.price.history],
                                   [p.close for p in sector.price.history], move_date)
        if sector_ret is not None and index_ret is not None:
            # sector's own idiosyncratic part beyond the market (approx, sector beta ~1)
            sector_component = sector_ret - index_ret

    idio = total
    if market_component is not None:
        idio -= market_component
    if sector_component is not None:
        idio -= sector_component

    # Classify by dominant component.
    comps = {"market": market_component, "sector": sector_component, "stock_specific": idio}
    present = {k: v for k, v in comps.items() if v is not None}
    dominant = max(present, key=lambda k: abs(present[k])) if present else "stock_specific"
    classification = {"market": "systematic", "sector": "sector", "stock_specific": "stock_specific"}[dominant]

    candidates = _candidate_causes(payload, move_date)
    driver_type, key_disambiguator = _driver_type(classification, idio, total, candidates)
    thesis_impact = _thesis_impact(payload, classification, idio)

    def _pct(x):
        return None if x is None else round(x, 4)

    from app.services.guards import find_advice_terms
    out = {
        "ticker": payload.ticker,
        "source": payload.source,
        "available": True,
        "date": move_date,
        "total_return": _pct(total),
        "beta_used": round(beta, 2),
        "attribution": {
            "market": _pct(market_component),
            "sector": _pct(sector_component),
            "idiosyncratic": _pct(idio),
            "note": "Approximate decomposition (beta-based); components may not sum exactly due to "
                    "the sector approximation.",
        },
        "classification": classification,
        "candidate_causes": candidates,
        "driver_type": driver_type,
        "thesis_impact": thesis_impact,
        "key_disambiguator": key_disambiguator,
        "disclaimer": "An estimate of drivers, not a forecast · correlation, not proven causation · "
                      "not financial advice.",
        "warnings": payload.warnings,
    }
    out["advice_terms_found"] = find_advice_terms({k: out[k] for k in
                                                   ("thesis_impact", "key_disambiguator", "candidate_causes")})
    return out


def _candidate_causes(payload: CompanyPayload, move_date: str | None) -> list[dict]:
    """Same-day headlines as candidate explanations — explicitly correlation, not causation."""
    causes = []
    for n in payload.news:
        d = (n.published or "")[:10]
        if move_date and d == move_date:
            causes.append({"type": "news", "headline": n.title, "source_url": n.url,
                           "flag": "correlation, not proven causation"})
    if not causes and payload.news:
        causes.append({"type": "news", "headline": payload.news[0].title,
                       "source_url": payload.news[0].url,
                       "flag": "nearest available headline; correlation, not causation"})
    return causes


def _driver_type(classification: str, idio: float | None, total: float, candidates: list[dict]) -> tuple[str, str]:
    if classification in ("systematic", "sector"):
        return ("likely_transient",
                "Whether the macro/sector driver (e.g. the rate path) persists — 'transient' depends on it.")
    if classification == "stock_specific" and idio is not None and abs(idio) > 0.03:
        return ("likely_structural",
                "Whether the company-specific news changes the forward cash-flow outlook (re-underwrite) "
                "or is noise.")
    return ("ambiguous", "Whether the move reflects new fundamental information or just price/positioning.")


def _thesis_impact(payload: CompanyPayload, classification: str, idio: float | None) -> dict:
    """Tie the move to the falsifiable thesis points (from /analysis)."""
    from app.services.analysis_service import build_analysis

    analysis = build_analysis(payload)["analysis"]
    falsifiers = [p.get("falsifier") for side in ("bull_case", "bear_case")
                  for p in analysis.get(side, []) if p.get("falsifier")]
    triggered = classification == "stock_specific" and idio is not None and abs(idio) > 0.03
    return {
        "triggers_any_falsifier": triggered,
        "reasoning": (
            "Move is mostly market/sector — it triggers none of the thesis's company-specific "
            "falsifiers; this is price moving, not value, unless the macro regime itself is the thesis."
            if not triggered else
            "Move has a material stock-specific component — check whether it crosses a thesis falsifier; "
            "if so, the case needs revisiting."
        ),
        "falsifiers_to_check": falsifiers[:4],
    }
