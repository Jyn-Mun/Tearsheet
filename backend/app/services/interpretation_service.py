"""Module 3 — Interpretation / "So-What" Synthesis (PRD Addendum §D).

Consumes the outputs of DCF, valuation, news sentiment, events, and current price, and produces
an integrated read: per-signal meaning, reverse-DCF implied expectations ("what's priced in"),
and a coherence map that NAMES conflicts rather than averaging them into a bland verdict.
It interprets; it never recommends.
"""

from __future__ import annotations

from app.models.schemas import CompanyPayload
from app.services import dcf_engine as eng
from app.services.dcf_service import build_dcf
from app.services.guards import find_advice_terms
from app.services.macro import risk_free_rate
from app.services.valuation_service import build_valuation
from app.utils.financial_math import safe_div

CONSTRUCTIVE, CAUTIOUS, NEUTRAL = "constructive", "cautious", "neutral"


def _own_pe_percentile(payload: CompanyPayload) -> tuple[float | None, float | None]:
    """Approximate where the current P/E sits in its own ~history, using trailing EPS held flat
    against the daily price series. Returns (current_pe, percentile 0-1)."""
    inc = payload.financials.income
    shares = payload.key_metrics.shares_outstanding
    if not inc or not shares or not payload.price.history:
        return None, None
    eps_ttm = safe_div(inc[0].net_income, shares)
    if not eps_ttm or eps_ttm <= 0:
        return None, None
    series = [p.close / eps_ttm for p in payload.price.history]
    current = payload.price.current
    cur_pe = (current / eps_ttm) if current else series[-1]
    below = sum(1 for v in series if v <= cur_pe)
    return cur_pe, below / len(series)


def _reverse_dcf(payload: CompanyPayload) -> dict:
    rf = risk_free_rate()
    a, _ = eng.build_assumptions(payload, risk_free=rf)
    price = payload.price.current
    if a is None or price is None:
        return {"available": False, "reason": "insufficient data for a reverse DCF"}
    implied_growth = eng.solve_implied_growth(a, price)
    return {
        "available": implied_growth is not None,
        "current_price": price,
        "base_case_start_growth": a.start_growth,
        "implied_start_growth": implied_growth,
        "terminal_growth": a.terminal_growth,
        "ebit_margin_assumed": a.ebit_margin,
        "wacc": a.wacc,
        "reading": (
            f"At today's price the market implies ~{implied_growth*100:.0f}% near-term revenue "
            f"growth (vs a ~{a.start_growth*100:.0f}% trailing-based base case), fading to "
            f"{a.terminal_growth*100:.1f}% terminal."
            if implied_growth is not None
            else "No implied growth solves within a plausible range — valuation may rest on "
                 "margin/optionality the model doesn't capture."
        ),
    }


def build_interpretation(payload: CompanyPayload) -> dict:
    price = payload.price.current
    dcf = build_dcf(payload)
    val = build_valuation(payload, _provider_for(payload))
    reverse = _reverse_dcf(payload)

    per_signal: dict[str, dict] = {}

    # --- DCF signal (read both ways; the gap is ambiguous by design) ---
    upside = dcf.get("outputs", {}).get("upside_vs_price") if dcf.get("reliable") else None
    if upside is None:
        per_signal["dcf"] = {"reading": "DCF unreliable or unavailable for this name.",
                             "direction": NEUTRAL, "basis": dcf.get("reason") or "see DCF flags"}
    else:
        direction = CONSTRUCTIVE if upside > 0.15 else CAUTIOUS if upside < -0.15 else NEUTRAL
        per_signal["dcf"] = {
            "reading": (
                f"Base-case intrinsic implies {upside*100:+.0f}% vs price. "
                + ("Either the market prices slower growth/higher risk than the model, or the "
                   "model's assumptions are optimistic." if upside > 0
                   else "The market prices more optimism than the base case — growth/margin "
                        "expectations are embedded in the price.")
            ),
            "direction": direction,
            "basis": reverse.get("reading"),
        }

    # --- Multiples signal (vs peer median and own history) ---
    pe = val["multiples"].get("pe_ttm")
    peer_med = (val["peers"]["median"] or {}).get("pe_ttm")
    cur_pe, pe_pct = _own_pe_percentile(payload)
    mult_dir = NEUTRAL
    basis_bits = []
    if pe is not None and peer_med:
        ratio = pe / peer_med
        mult_dir = CAUTIOUS if ratio > 1.1 else CONSTRUCTIVE if ratio < 0.9 else NEUTRAL
        basis_bits.append(f"P/E {pe:.1f}x vs peer median {peer_med:.1f}x ({(ratio-1)*100:+.0f}%)")
    if pe_pct is not None:
        basis_bits.append(f"~{pe_pct*100:.0f}th percentile of its own ~price history")
    per_signal["multiples"] = {
        "reading": (
            ("Premium to peers — the multiple embeds above-peer expectations." if mult_dir == CAUTIOUS
             else "Discount to peers — the multiple embeds below-peer expectations." if mult_dir == CONSTRUCTIVE
             else "Roughly in line with peers.")
            if peer_med else "Peer multiples unavailable in the current data source; own-history shown."
        ),
        "direction": mult_dir,
        "basis": "; ".join(basis_bits) or "insufficient multiples data",
    }

    # --- Narrative / sentiment signal ---
    from app.services.synthesizer import get_synthesizer
    sentiment = (get_synthesizer().news_summary(payload).get("sentiment")
                 if payload.news else "neutral")
    narr_dir = {"positive": CONSTRUCTIVE, "negative": CAUTIOUS}.get(sentiment, NEUTRAL)
    per_signal["narrative"] = {
        "reading": f"Headline sentiment reads {sentiment}.",
        "direction": narr_dir,
        "basis": f"{len(payload.news)} headlines; sentiment={sentiment}",
    }

    # --- Recent price/behaviour signal ---
    closes = [p.close for p in payload.price.history]
    mom = (closes[-1] / closes[-22] - 1) if len(closes) >= 22 and closes[-22] else None
    beh_dir = NEUTRAL
    if mom is not None:
        beh_dir = CONSTRUCTIVE if mom > 0.05 else CAUTIOUS if mom < -0.05 else NEUTRAL
    per_signal["price_behaviour"] = {
        "reading": (f"~1-month price momentum {mom*100:+.0f}%." if mom is not None
                    else "Insufficient price history for momentum."),
        "direction": beh_dir,
        "basis": f"last close {price} vs ~21 sessions prior" if mom is not None else "n/a",
    }

    # --- Coherence map ---
    dirs = [s["direction"] for s in per_signal.values()]
    non_neutral = set(d for d in dirs if d != NEUTRAL)
    coherence = "conflicting" if {CONSTRUCTIVE, CAUTIOUS} <= non_neutral else "coherent"

    integrated, key_unknown = _integrated_read(per_signal, coherence, reverse)

    result = {
        "ticker": payload.ticker,
        "source": payload.source,
        "current_price": price,
        "per_signal": per_signal,
        "implied_expectations": reverse,
        "coherence": coherence,
        "integrated_read": integrated,
        "key_unknown": key_unknown,
        "disclaimer": "Interpretation of computed signals · not a recommendation, target, or 'should'.",
        "warnings": payload.warnings,
    }
    result["advice_terms_found"] = find_advice_terms(
        {"per_signal": per_signal, "integrated_read": integrated, "key_unknown": key_unknown}
    )
    return result


def _integrated_read(per_signal: dict, coherence: str, reverse: dict) -> tuple[str, str]:
    dcf_d = per_signal["dcf"]["direction"]
    mult_d = per_signal["multiples"]["direction"]
    narr_d = per_signal["narrative"]["direction"]
    beh_d = per_signal["price_behaviour"]["direction"]

    if coherence == "coherent":
        sames = [k for k, v in per_signal.items() if v["direction"] != NEUTRAL]
        lead = per_signal[sames[0]]["direction"] if sames else NEUTRAL
        read = (
            f"Signals broadly cohere ({lead}). The consolidated read holds only while that picture "
            "stays intact — what would break it is the falsifier embedded in each signal's basis."
            if sames else "Signals are mostly neutral; no strong consolidated picture."
        )
        key = "Whether the next earnings print confirms or breaks the current trajectory."
        return read, key

    # conflicting — name the disagreement explicitly (that's the insight)
    cheap_side = "undemanding" if dcf_d == CONSTRUCTIVE else "demanding"
    mult_side = "a peer premium" if mult_d == CAUTIOUS else "a peer discount" if mult_d == CONSTRUCTIVE else "in line with peers"
    price_side = "falling" if beh_d == CAUTIOUS else "rising" if beh_d == CONSTRUCTIVE else "flat"
    read = (
        f"DCF implied-growth looks {cheap_side} and narrative is {per_signal['narrative']['reading'].lower()} "
        f"yet the multiple sits at {mult_side} and the price is {price_side} — the divergence suggests the "
        "move may be driven by macro/rate repricing or positioning rather than a change in the company's "
        "fundamentals. The thing to resolve is which of those is actually moving the stock."
    )
    key = "Whether the gap is a macro/rate repricing (price, not value) or a genuine change in the cash-flow outlook (value)."
    return read, key


def _provider_for(payload: CompanyPayload):
    # Valuation needs a provider to fetch peers; reuse the configured one.
    from app.providers import get_provider

    return get_provider()
