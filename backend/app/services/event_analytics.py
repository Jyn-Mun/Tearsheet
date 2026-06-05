"""Module 2 — Event & Behaviour Analytics (PRD Addendum §C).

ALL statistics are computed deterministically here in Python; the LLM only narrates them.
Every statistic carries its sample size and dispersion; n<8 is flagged "insufficient sample".
The point of the module is to separate "beats estimates" from "stock goes up" and surface when
they diverge — replacing false memory with the measured pattern. Descriptive only: no timing
calls, no implied repetition.
"""

from __future__ import annotations

from datetime import date

from app.models.schemas import CompanyPayload
from app.utils.financial_math import pct_window_return, stats

_MIN_SAMPLE = 8
REGIME_NOTE = (
    "Descriptive, based on the available history. Historical behaviour is NOT predictive; "
    "known calendar/earnings effects are arbitraged and decay over time."
)


def _history_index_on_or_after(dates: list[str], target: str) -> int | None:
    """Index of the first trading day on/after `target` (ISO date)."""
    for i, d in enumerate(dates):
        if d >= target:
            return i
    return None


def _earnings_behaviour(payload: CompanyPayload) -> dict:
    closes = [p.close for p in payload.price.history]
    dates = [p.date for p in payload.price.history]
    pre_returns: list[float] = []
    post_returns: list[float] = []
    surprises_for_corr: list[float] = []
    post_for_corr: list[float] = []
    per_event = []
    beat = miss = inline = 0

    for rec in payload.earnings:
        surprise = rec.surprise_pct
        is_beat = None
        if surprise is not None:
            is_beat = surprise > 0.05
            if surprise > 0.05:
                beat += 1
            elif surprise < -0.05:
                miss += 1
            else:
                inline += 1

        idx = _history_index_on_or_after(dates, rec.date)
        pre = post = None
        if idx is not None:
            pre = pct_window_return(closes, idx - 5, idx - 1)
            post = pct_window_return(closes, idx + 1, idx + 5)
        if pre is not None:
            pre_returns.append(pre)
        if post is not None:
            post_returns.append(post)
        if surprise is not None and post is not None:
            surprises_for_corr.append(surprise)
            post_for_corr.append(post)

        per_event.append({
            "date": rec.date,
            "eps_estimate": rec.eps_estimate,
            "eps_actual": rec.eps_actual,
            "surprise_pct": surprise,
            "beat": is_beat,
            "pre_return": pre,
            "post_return": post,
        })

    n = len(payload.earnings)
    surprises = [r.surprise_pct for r in payload.earnings if r.surprise_pct is not None]

    def _hit_rate(rets: list[float]) -> float | None:
        return (sum(1 for r in rets if r > 0) / len(rets)) if rets else None

    corr = _pearson(surprises_for_corr, post_for_corr)

    return {
        "n_reports": n,
        "insufficient_sample": n < _MIN_SAMPLE,
        "beat_count": beat,
        "miss_count": miss,
        "inline_count": inline,
        "beat_rate": (beat / n) if n else None,
        "avg_surprise_pct": (sum(surprises) / len(surprises)) if surprises else None,
        "last_surprise_pct": payload.earnings[-1].surprise_pct if payload.earnings else None,
        "pre_window": {
            "label": "5 sessions before report (run-up)",
            **stats(pre_returns),
            "hit_rate": _hit_rate(pre_returns),
        },
        "post_window": {
            "label": "5 sessions after report (reaction)",
            **stats(post_returns),
            "hit_rate": _hit_rate(post_returns),
        },
        "surprise_vs_post_correlation": {"value": corr, "n": len(post_for_corr)},
        "per_event": per_event,
        "regime_note": REGIME_NOTE,
    }


def _seasonality(payload: CompanyPayload) -> dict:
    """Monthly and day-of-week average daily returns over the available history (descriptive)."""
    closes = [p.close for p in payload.price.history]
    dates = [p.date for p in payload.price.history]
    by_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    by_dow: dict[int, list[float]] = {d: [] for d in range(5)}
    for i in range(1, len(closes)):
        if closes[i] is None or closes[i - 1] in (None, 0):
            continue
        r = closes[i] / closes[i - 1] - 1
        try:
            d = date.fromisoformat(dates[i])
        except ValueError:
            continue
        by_month[d.month].append(r)
        if d.weekday() < 5:
            by_dow[d.weekday()].append(r)

    months = [{"month": m, **stats(v)} for m, v in by_month.items()]
    dows = [
        {"day": ["Mon", "Tue", "Wed", "Thu", "Fri"][d], **stats(v)}
        for d, v in by_dow.items()
    ]
    return {
        "monthly": months,
        "day_of_week": dows,
        "note": "Descriptive averages over ~"
                f"{max(1, len(closes) // 252)}y; NOT predictive. Each figure carries n and std.",
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    import numpy as np

    a, b = np.array(xs), np.array(ys)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def build_events(payload: CompanyPayload) -> dict:
    from app.services.synthesizer import get_synthesizer

    behaviour = _earnings_behaviour(payload)
    seasonality = _seasonality(payload)
    stats_blob = {"earnings_behaviour": behaviour, "seasonality": seasonality}

    narration = None
    if payload.earnings:
        narration = get_synthesizer().events_narration(payload.ticker, stats_blob)

    from app.services.guards import find_advice_terms

    return {
        "ticker": payload.ticker,
        "source": payload.source,
        "earnings_behaviour": behaviour,
        "seasonality": seasonality,
        "narration": narration,
        "advice_terms_found": find_advice_terms(narration) if narration else [],
        "warnings": payload.warnings,
        "disclaimer": "Descriptive historical statistics · not predictive · not financial advice · "
                      "no timing call.",
    }
