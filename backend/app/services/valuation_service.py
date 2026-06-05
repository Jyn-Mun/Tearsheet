"""Valuation tab: multiples (with derived ROIC / FCF-yield) and a sector-based approximate
peer table with peer median. Peers are explicitly labelled an approximation (PRD §5.4).
"""

from __future__ import annotations

from statistics import median

from app.models.schemas import CompanyPayload
from app.providers.base import DataProvider
from app.utils.financial_math import safe_div

# Curated sector → representative peer tickers (approximation; v1 heuristic).
_SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": ["NVDA", "AMD", "AVGO", "INTC", "QCOM", "MSFT", "AAPL"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "Consumer Defensive": ["WMT", "PG", "KO", "PEP", "COST"],
    "Healthcare": ["JNJ", "UNH", "LLY", "PFE", "MRK"],
    "Financial Services": ["JPM", "BAC", "WFC", "GS", "MS"],
    "Industrials": ["CAT", "GE", "BA", "HON", "UNP"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
}


def _effective_tax_rate(payload: CompanyPayload) -> float | None:
    inc = payload.financials.income
    if not inc:
        return None
    r = inc[0]
    rate = safe_div(r.tax_provision, r.pretax_income)
    if rate is None or rate < 0 or rate > 0.6:
        return None
    return rate


def derive_roic(payload: CompanyPayload) -> float | None:
    inc = payload.financials.income
    bal = payload.financials.balance
    if not inc or not bal:
        return None
    ebit = inc[0].operating_income
    if ebit is None:
        return None
    tax = _effective_tax_rate(payload)
    tax = 0.21 if tax is None else tax
    nopat = ebit * (1 - tax)
    debt = bal[0].total_debt or 0.0
    equity = bal[0].stockholders_equity
    cash = bal[0].cash_and_equivalents or 0.0
    if equity is None:
        return None
    invested = (debt + equity) - cash
    return safe_div(nopat, invested)


def derive_fcf_yield(payload: CompanyPayload) -> float | None:
    cf = payload.financials.cashflow
    mcap = payload.price.market_cap
    if not cf or mcap is None:
        return None
    return safe_div(cf[0].free_cash_flow, mcap)


def _multiples(payload: CompanyPayload) -> dict:
    km = payload.key_metrics
    return {
        "pe_ttm": km.pe_ttm,
        "forward_pe": km.forward_pe,
        "ev_ebitda": km.ev_ebitda,
        "ps": km.ps,
        "pb": km.pb,
        "fcf_yield": derive_fcf_yield(payload),
        "roic": derive_roic(payload),
        "dividend_yield": km.dividend_yield,
    }


def build_valuation(payload: CompanyPayload, provider: DataProvider) -> dict:
    subject = _multiples(payload)
    sector = payload.profile.sector
    peers = _build_peers(payload, provider, sector)

    return {
        "ticker": payload.ticker,
        "source": payload.source,
        "sector": sector,
        "multiples": subject,
        "peers": peers,
        "peer_note": "Sector-based approximation: peers selected by sector and market-cap "
        "proximity from a curated list, not a formal comp set.",
        "provenance": (payload.provenance.get("key_metrics").model_dump()
                       if payload.provenance.get("key_metrics") else None),
        "warnings": payload.warnings,
    }


def _build_peers(payload: CompanyPayload, provider: DataProvider, sector: str | None) -> dict:
    candidates = [
        t for t in _SECTOR_PEERS.get(sector or "", [])
        if t.upper() != payload.ticker.upper()
    ]
    rows: list[dict] = []
    subject_mcap = payload.price.market_cap
    for tk in candidates:
        try:
            p = provider.retrieve(tk)
        except Exception:
            continue
        if p.price.current is None and not p.key_metrics.pe_ttm:
            continue  # peer data unavailable (rate-limited / no fixture)
        rows.append({
            "ticker": tk,
            "name": p.profile.name,
            "market_cap": p.price.market_cap,
            "pe_ttm": p.key_metrics.pe_ttm,
            "ev_ebitda": p.key_metrics.ev_ebitda,
            "ps": p.key_metrics.ps,
            "pb": p.key_metrics.pb,
        })
        if len(rows) >= 6:
            break

    # Sort by market-cap proximity to the subject when available.
    if subject_mcap:
        rows.sort(key=lambda r: abs((r["market_cap"] or 0) - subject_mcap))

    med = {
        k: _median([r[k] for r in rows])
        for k in ("pe_ttm", "ev_ebitda", "ps", "pb")
    }
    return {
        "rows": rows,
        "median": med,
        "count": len(rows),
        "note": None if rows else "Peer data unavailable in the current data source "
        "(live fetch limited or no fixtures); subject multiples still shown.",
    }


def _median(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return median(vals) if vals else None
