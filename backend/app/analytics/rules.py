"""Rule-based interpretation — a transparent, zero-LLM rules engine that turns the computed
metrics into plain-language flags. Each rule shows the inputs that fired it, so the reasoning is
fully auditable. Research tool, not advice — rules describe conditions, never recommend trades.
"""

from __future__ import annotations

from typing import Any, Callable

# A rule: id, severity, a predicate over the context, a message template, and the input keys cited.
Rule = dict[str, Any]


def _pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def _has(ctx, *keys) -> bool:
    return all(ctx.get(k) is not None for k in keys)


RULES: list[dict] = [
    {
        "id": "quality_at_undemanding_price",
        "severity": "positive",
        "when": lambda c: (_has(c, "f_score", "implied_growth", "hist_rev_cagr")
                           and c["f_score"] >= 7
                           and c["implied_growth"] < c["hist_rev_cagr"]
                           and (c.get("fcf_yield") or 0) > 0.03),
        "msg": lambda c: (f"Piotroski F={c['f_score']}/9 with FCF yield {_pct(c.get('fcf_yield'))} and "
                          f"market-implied growth ({_pct(c['implied_growth'])}) below the company's own "
                          f"history ({_pct(c['hist_rev_cagr'])}) → quality at an undemanding price."),
        "inputs": ["f_score", "fcf_yield", "implied_growth", "hist_rev_cagr"],
    },
    {
        "id": "priced_for_perfection",
        "severity": "caution",
        "when": lambda c: (_has(c, "implied_growth", "hist_rev_cagr")
                           and c["implied_growth"] > c["hist_rev_cagr"] * 1.2),
        "msg": lambda c: (f"Market-implied growth ({_pct(c['implied_growth'])}) exceeds the company's "
                          f"trailing revenue CAGR ({_pct(c['hist_rev_cagr'])}) — a lot has to go right."),
        "inputs": ["implied_growth", "hist_rev_cagr"],
    },
    {
        "id": "distress_risk",
        "severity": "caution",
        "when": lambda c: c.get("altman_zone") == "distress",
        "msg": lambda c: f"Altman Z={c.get('altman_z')} is in the distress zone (<1.81) — elevated bankruptcy risk.",
        "inputs": ["altman_z", "altman_zone"],
    },
    {
        "id": "earnings_manipulation_flag",
        "severity": "caution",
        "when": lambda c: c.get("beneish_flag") is True,
        "msg": lambda c: (f"Beneish M={c.get('beneish_m')} (> −1.78) flags possible earnings "
                          "manipulation — scrutinise receivables/accruals. (Fast-growing firms can trip this.)"),
        "inputs": ["beneish_m", "beneish_flag"],
    },
    {
        "id": "strong_fundamental_momentum",
        "severity": "positive",
        "when": lambda c: _has(c, "f_score") and c["f_score"] >= 8,
        "msg": lambda c: f"Piotroski F={c['f_score']}/9 — broad-based fundamental strength (profitability, leverage, efficiency).",
        "inputs": ["f_score"],
    },
    {
        "id": "weak_fundamentals",
        "severity": "caution",
        "when": lambda c: _has(c, "f_score") and c["f_score"] <= 2,
        "msg": lambda c: f"Piotroski F={c['f_score']}/9 — weak/deteriorating fundamentals.",
        "inputs": ["f_score"],
    },
    {
        "id": "margin_compression",
        "severity": "caution",
        "when": lambda c: _has(c, "margin_trend") and c["margin_trend"] < -0.02,
        "msg": lambda c: f"Operating margin has compressed {_pct(c['margin_trend'])} over the window.",
        "inputs": ["margin_trend"],
    },
    {
        "id": "margin_expansion",
        "severity": "positive",
        "when": lambda c: _has(c, "margin_trend") and c["margin_trend"] > 0.02,
        "msg": lambda c: f"Operating margin has expanded +{_pct(c['margin_trend'])} over the window.",
        "inputs": ["margin_trend"],
    },
    {
        "id": "leverage_rising",
        "severity": "caution",
        "when": lambda c: _has(c, "leverage_trend") and c["leverage_trend"] > 0.05,
        "msg": lambda c: f"Debt/assets has risen +{_pct(c['leverage_trend'])} over the window.",
        "inputs": ["leverage_trend"],
    },
    {
        "id": "weak_cash_conversion",
        "severity": "caution",
        "when": lambda c: _has(c, "cash_conversion") and c["cash_conversion"] < 0.6,
        "msg": lambda c: f"Cash conversion (FCF/NI) is {c['cash_conversion']:.2f} — earnings aren't fully backed by cash.",
        "inputs": ["cash_conversion"],
    },
    {
        "id": "beats_not_up",
        "severity": "info",
        "when": lambda c: (_has(c, "beat_rate", "post_up_rate") and c["beat_rate"] >= 0.7
                           and c["post_up_rate"] < 0.55 and c.get("events_n", 0) >= 8),
        "msg": lambda c: (f"Beats estimates in {_pct(c['beat_rate'],0)} of reports but rises only "
                          f"{_pct(c['post_up_rate'],0)} of the time post-print — 'beats' ≠ 'up' (n={c.get('events_n')})."),
        "inputs": ["beat_rate", "post_up_rate", "events_n"],
    },
    {
        "id": "overbought",
        "severity": "info",
        "when": lambda c: _has(c, "rsi") and c["rsi"] > 70,
        "msg": lambda c: f"RSI(14)={c['rsi']:.0f} (>70) — technically overbought.",
        "inputs": ["rsi"],
    },
    {
        "id": "oversold",
        "severity": "info",
        "when": lambda c: _has(c, "rsi") and c["rsi"] < 30,
        "msg": lambda c: f"RSI(14)={c['rsi']:.0f} (<30) — technically oversold.",
        "inputs": ["rsi"],
    },
    {
        "id": "deep_drawdown",
        "severity": "info",
        "when": lambda c: _has(c, "max_drawdown") and c["max_drawdown"] < -0.4,
        "msg": lambda c: f"Down {_pct(c['max_drawdown'])} from its 2y peak (max drawdown).",
        "inputs": ["max_drawdown"],
    },
    {
        "id": "cheap_vs_peers",
        "severity": "positive",
        "when": lambda c: _has(c, "pe_percentile") and c["pe_percentile"] <= 25,
        "msg": lambda c: f"P/E sits in the {c['pe_percentile']:.0f}th percentile of its peer set — a discount to peers.",
        "inputs": ["pe_percentile"],
    },
]


def run_rules(ctx: dict) -> dict:
    """Evaluate every rule against the context; return the ones that fired, with their inputs."""
    fired = []
    for r in RULES:
        try:
            if r["when"](ctx):
                fired.append({
                    "id": r["id"],
                    "severity": r["severity"],
                    "message": r["msg"](ctx),
                    "inputs": {k: ctx.get(k) for k in r["inputs"]},
                })
        except Exception:
            continue  # a rule that can't evaluate (missing input) simply doesn't fire
    headline = _headline(fired)
    return {
        "fired": fired,
        "count": len(fired),
        "headline": headline,
        "method": "transparent rules engine (no LLM) — each flag shows the inputs that triggered it.",
        "disclaimer": "Describes conditions in the data; not a recommendation.",
    }


def _headline(fired: list[dict]) -> str:
    if not fired:
        return "No notable rule-based flags from the available data."
    pos = [f for f in fired if f["severity"] == "positive"]
    cau = [f for f in fired if f["severity"] == "caution"]
    bits = []
    if pos:
        bits.append(pos[0]["message"])
    if cau:
        bits.append(cau[0]["message"])
    return " ".join(bits) if bits else fired[0]["message"]
