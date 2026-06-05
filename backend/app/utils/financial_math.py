"""Pure financial helpers. No I/O, fully unit-testable. Reused by valuation + DCF + events."""

from __future__ import annotations

import math
from statistics import mean, median, pstdev


def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def cagr(begin: float | None, end: float | None, years: int) -> float | None:
    """Compound annual growth rate. None if inputs invalid (e.g. non-positive begin)."""
    if begin is None or end is None or years <= 0 or begin <= 0 or end <= 0:
        return None
    return (end / begin) ** (1.0 / years) - 1.0


def yoy(series_newest_first: list[float | None]) -> list[float | None]:
    """Year-over-year growth for a newest-first series; returns same length, oldest year None."""
    out: list[float | None] = []
    for i, v in enumerate(series_newest_first):
        prev = series_newest_first[i + 1] if i + 1 < len(series_newest_first) else None
        out.append(safe_div((v - prev) if (v is not None and prev is not None) else None, prev))
    return out


def discount_factor(rate: float, period: float) -> float:
    return 1.0 / ((1.0 + rate) ** period)


def present_value(cashflows: list[float], rate: float, start_period: int = 1) -> float:
    """PV of a list of cashflows discounted at `rate`, first cashflow at `start_period`."""
    return sum(cf * discount_factor(rate, start_period + i) for i, cf in enumerate(cashflows))


def gordon_terminal_value(final_fcf: float, g: float, wacc: float) -> float | None:
    """Gordon-growth terminal value at the end of the projection. None if WACC <= g (guard)."""
    if wacc <= g:
        return None
    return final_fcf * (1.0 + g) / (wacc - g)


def linear_fade(start: float, end: float, n: int) -> list[float]:
    """n values fading linearly from `start` (year 1) to `end` (year n)."""
    if n <= 1:
        return [end]
    return [start + (end - start) * (i / (n - 1)) for i in range(n)]


def stats(values: list[float]) -> dict:
    """Descriptive stats with sample size — the building block for event analytics."""
    vals = [v for v in values if v is not None and not math.isnan(v)]
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "std": None, "min": None, "max": None}
    return {
        "n": n,
        "mean": mean(vals),
        "median": median(vals),
        "std": pstdev(vals) if n > 1 else 0.0,
        "min": min(vals),
        "max": max(vals),
    }


def pct_window_return(closes: list[float], start_idx: int, end_idx: int) -> float | None:
    """Cumulative return from close[start_idx] to close[end_idx]."""
    if start_idx < 0 or end_idx >= len(closes) or start_idx >= len(closes):
        return None
    a, b = closes[start_idx], closes[end_idx]
    if a is None or b is None or a == 0:
        return None
    return b / a - 1.0
