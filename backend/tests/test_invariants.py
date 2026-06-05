"""The hard invariants: no-advice gate (negation-aware), falsifiers, beat!=up, move attribution."""

from app.services.analysis_service import build_analysis
from app.services.event_analytics import build_events
from app.services.guards import find_advice_terms, missing_falsifiers
from app.services.move_service import build_move


def test_no_advice_gate_negation_aware():
    # Disclaimers must pass; real advice must be caught.
    assert find_advice_terms("This is not a buy, sell, or hold recommendation; no price target.") == []
    hits = find_advice_terms("We recommend buy with a price target of 250.")
    assert "buy" in hits and "price target" in hits and "we recommend" in hits


def test_analysis_invariants_pass(nvda):
    out = build_analysis(nvda)
    assert out["invariants"]["no_advice"]["passed"]
    assert out["invariants"]["falsifiers_present"]["passed"]
    assert not missing_falsifiers(out["analysis"])


def test_events_beat_not_equal_up(nvda):
    eb = build_events(nvda)["earnings_behaviour"]
    assert eb["n_reports"] >= 8 and not eb["insufficient_sample"]
    # The fixture beats almost always but the stock often sells the news.
    assert eb["beat_rate"] >= 0.8
    assert eb["post_window"]["hit_rate"] < 0.6  # beats != up
    # every statistic carries a sample size
    assert eb["post_window"]["n"] is not None


def test_events_insufficient_sample_flagged(provider):
    # An ETF fixture has no earnings -> n=0 -> insufficient.
    eb = build_events(provider.retrieve("SPY"))["earnings_behaviour"]
    assert eb["insufficient_sample"]


def test_move_attribution_broad_selloff(nvda, provider):
    mv = build_move(nvda, provider, target_date="2026-06-05")
    assert mv["available"]
    a = mv["attribution"]
    # Market + sector dominate; idiosyncratic is the minority -> systematic, transient.
    assert abs(a["market"]) + abs(a["sector"]) > abs(a["idiosyncratic"])
    assert mv["classification"] == "systematic"
    assert mv["driver_type"] == "likely_transient"
    assert mv["thesis_impact"]["triggers_any_falsifier"] is False
    assert find_advice_terms(mv) == []
