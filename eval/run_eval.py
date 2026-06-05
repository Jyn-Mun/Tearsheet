#!/usr/bin/env python3
"""Tearsheet evaluation harness.

Runs the agent on each case and scores:
  1. Factual accuracy   — do retrieved facts match expectations? (exact for hard facts)
  2. Citation validity  — does every analysis claim carry a source whose domain resolves to an
                          expected real domain (not a hallucinated URL)?
  3. Hallucination      — flag any number in the output not present in the retrieved payload.
  4. DCF correctness    — independently recompute the DCF and assert outputs match within
                          tolerance; assert the WACC>g guard fires on bad inputs.
Plus the Addendum §H gates:
  5. No-advice          — HARD gate: any buy/sell/hold/target language fails the suite.
  6. Falsifiers         — every bull/bear point ships a falsifier.
  7. Bias correction    — /events reports the beat record AND the beat!=up divergence.
  8. Attribution        — a broad-selloff session attributes the majority to market/sector.
  9. Conflict surfacing — a constructed conflicting case returns coherence: conflicting.

Methodology: runs IN-PROCESS against the FixtureProvider (deterministic, no network, no API key
needed — the synthesizer falls back to its grounded mock). The same checks run unchanged against
the live yfinance provider or an EDGAR provider; only the fixtures differ. Soft-fact grading would
use an LLM grader when ANTHROPIC_API_KEY is set; offline we use exact/numeric checks only.

Run:  python eval/run_eval.py     (from the repo root, with the backend venv active)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Force the offline fixture provider for deterministic, network-free, key-free evaluation.
# (Must be set before importing app modules, which read settings at import time.)
os.environ["DATA_PROVIDER"] = "fixture"

from app.models.schemas import CompanyPayload, IncomeRow  # noqa: E402
from app.providers.fixture_provider import FixtureProvider  # noqa: E402
from app.services import dcf_engine as eng  # noqa: E402
from app.services.analysis_service import build_analysis  # noqa: E402
from app.services.dcf_service import build_dcf  # noqa: E402
from app.services.event_analytics import build_events  # noqa: E402
from app.services.guards import find_advice_terms, missing_falsifiers  # noqa: E402
from app.services.interpretation_service import build_interpretation  # noqa: E402
from app.services.move_service import build_move  # noqa: E402

# Eval runs against the engineered test fixtures (deterministic worked examples),
# independent of the app's deploy-snapshot fixtures.
PROVIDER = FixtureProvider(ROOT / "backend" / "tests" / "fixtures")
TESTSET = json.loads((ROOT / "eval" / "testset.json").read_text())
EXPECTED_DOMAINS = set(TESTSET["expected_source_domains"])


# ----------------------------------------------------------------- helpers

def _numbers(text: str) -> list[float]:
    """Extract numeric tokens from free text (ignoring years and tiny integers)."""
    out = []
    for tok in re.findall(r"-?\d[\d,]*\.?\d*", text or ""):
        try:
            v = float(tok.replace(",", ""))
        except ValueError:
            continue
        if 1900 <= v <= 2100 and v == int(v):
            continue  # year
        if abs(v) <= 12 and v == int(v):
            continue  # small ordinals/counts
        out.append(v)
    return out


def _payload_number_strings(payload: CompanyPayload) -> set[str]:
    """Plausible string representations of every number in the payload, for grounding checks."""
    s: set[str] = set()
    d = payload.model_dump()

    def walk(x):
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            for r in (x, round(x, 1), round(x, 2), round(x * 100, 1), round(x * 100, 2)):
                s.add(f"{r:.0f}")
                s.add(f"{r:.1f}")
                s.add(f"{r:.2f}")
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(d)
    return s


def _hallucinated_numbers(payload: CompanyPayload, output_text: str) -> list[float]:
    allowed = _payload_number_strings(payload)
    bad = []
    for v in _numbers(output_text):
        reps = {f"{v:.0f}", f"{v:.1f}", f"{v:.2f}", f"{round(v,1):.1f}", f"{round(v):.0f}"}
        if not (reps & allowed):
            bad.append(v)
    return bad


def _domains_ok(analysis: dict) -> tuple[int, int]:
    """(#claims with a valid expected-domain source, #total claims)."""
    ok = total = 0
    for side in ("bull_case", "bear_case"):
        for pt in analysis.get(side, []):
            total += 1
            url = pt.get("source_url")
            if url:
                host = urlparse(url).hostname or ""
                if any(host == d or host.endswith("." + d) for d in EXPECTED_DOMAINS):
                    ok += 1
    return ok, total


# ----------------------------------------------------------------- scoring

class Tally:
    def __init__(self):
        self.fact_pass = self.fact_total = 0
        self.cite_ok = self.cite_total = 0
        self.halluc = self.halluc_total = 0
        self.dcf_pass = self.dcf_total = 0
        self.falsif_pass = self.falsif_total = 0
        self.attrib_pass = self.attrib_total = 0
        self.no_advice_ok = True
        self.advice_hits: list[str] = []
        self.failures: list[str] = []

    def pct(self, a, b):
        return f"{(100 * a / b):.0f}%" if b else "n/a"


T = Tally()


def case_facts(case):
    p = PROVIDER.retrieve(case["ticker"])
    for k, want in case["expected_facts"].items():
        T.fact_total += 1
        got = getattr(p.profile, k, None)
        if got == want:
            T.fact_pass += 1
        else:
            T.failures.append(f"{case['id']}: {k} expected {want!r} got {got!r}")


def case_citations(case):
    a = build_analysis(PROVIDER.retrieve(case["ticker"]))["analysis"]
    ok, total = _domains_ok(a)
    T.cite_ok += ok
    T.cite_total += total
    if ok < total:
        T.failures.append(f"{case['id']}: {total - ok} claim(s) without a valid source domain")


def case_grounding(case):
    p = PROVIDER.retrieve(case["ticker"])
    a = build_analysis(p)["analysis"]
    text = " ".join(
        [a.get("snapshot", ""), a.get("premortem", "")]
        + [pt.get("claim", "") for side in ("bull_case", "bear_case") for pt in a.get(side, [])]
    )
    T.halluc_total += 1
    bad = _hallucinated_numbers(p, text)
    if bad:
        T.halluc += 1
        T.failures.append(f"{case['id']}: numbers not in payload: {bad}")


def case_grounding_violation(case):
    """Negative control: a fabricated number MUST be detected (proves the check works)."""
    p = PROVIDER.retrieve("NVDA")
    T.halluc_total += 1
    bad = _hallucinated_numbers(p, "Revenue will be 999999.7 next year.")
    if not bad:
        T.failures.append(f"{case['id']}: hallucination check FAILED to flag a fabricated number")
    # (this is a control; we do not increment T.halluc — detecting it is success)


def case_falsifiers(case):
    a = build_analysis(PROVIDER.retrieve(case["ticker"]))["analysis"]
    for side in ("bull_case", "bear_case"):
        for pt in a.get(side, []):
            T.falsif_total += 1
            if pt.get("falsifier", "").strip():
                T.falsif_pass += 1
    missing = missing_falsifiers(a)
    if missing:
        T.failures.append(f"{case['id']}: missing falsifiers: {missing}")


def case_events_bias(case):
    eb = build_events(PROVIDER.retrieve(case["ticker"]))["earnings_behaviour"]
    exp = case["expect"]
    T.fact_total += 1
    if eb["beat_rate"] >= exp["min_beat_rate"] and eb["post_window"]["hit_rate"] <= exp["max_post_up_rate"]:
        T.fact_pass += 1
    else:
        T.failures.append(f"{case['id']}: beat_rate={eb['beat_rate']:.2f} post_up={eb['post_window']['hit_rate']:.2f}")


def case_events_insufficient(case):
    eb = build_events(PROVIDER.retrieve(case["ticker"]))["earnings_behaviour"]
    T.fact_total += 1
    if eb["insufficient_sample"]:
        T.fact_pass += 1
    else:
        T.failures.append(f"{case['id']}: expected insufficient_sample flag")


def case_attribution(case):
    p = PROVIDER.retrieve(case["ticker"])
    mv = build_move(p, PROVIDER, target_date=case["date"])
    exp = case["expect"]
    T.attrib_total += 1
    a = mv["attribution"]
    majority_systematic = abs(a["market"]) + abs(a["sector"] or 0) > abs(a["idiosyncratic"])
    if mv["classification"] == exp["classification"] and mv["driver_type"] == exp["driver"] and majority_systematic:
        T.attrib_pass += 1
    else:
        T.failures.append(f"{case['id']}: class={mv['classification']} driver={mv['driver_type']}")


def case_dcf_recompute(case):
    p = PROVIDER.retrieve(case["ticker"])
    a, _ = eng.build_assumptions(p, risk_free=0.043)
    res = eng.run_dcf(a)
    T.dcf_total += 1
    # independent recompute of EV from the projection rows
    pv = sum(r["pv_fcf"] for r in res["rows"])
    ev_ok = abs(pv + (res["pv_terminal_value"] or 0) - res["enterprise_value"]) < 1.0
    rev_ok = abs(res["rows"][0]["revenue"] - a.base_revenue * (1 + res["rows"][0]["growth"])) < 1.0
    if ev_ok and rev_ok:
        T.dcf_pass += 1
    else:
        T.failures.append(f"{case['id']}: DCF recompute mismatch")


def case_dcf_guard(case):
    p = CompanyPayload(ticker="BANKX", as_of="", source="test")
    p.profile.sector = "Financial Services"
    p.financials.income = [IncomeRow(fiscal_year=2025, revenue=1e9, operating_income=-5e7, net_income=-8e7)]
    p.price.current = 10.0
    p.key_metrics.shares_outstanding = 1e8
    d = build_dcf(p)
    T.dcf_total += 1
    a, _ = eng.build_assumptions(p, risk_free=0.043)
    guard = a is None or eng.run_dcf(a, wacc_override=0.02, terminal_growth_override=0.03)["terminal_value"] is None
    if (d["reliable"] is False) and guard:
        T.dcf_pass += 1
    else:
        T.failures.append(f"{case['id']}: guard did not fire (reliable={d['reliable']})")


def case_interpret_conflict(case):
    # Construct a payload where DCF-implied growth is undemanding but the multiple is a peer premium.
    p = PROVIDER.retrieve("NVDA").model_copy(deep=True)
    p.ticker = "CONFLICTX"
    p.price.current = 60.0           # cheap vs intrinsic -> DCF constructive (undemanding implied growth)
    p.key_metrics.pe_ttm = 80.0      # rich multiple
    # make recent momentum negative
    for i, pt in enumerate(p.price.history[-22:]):
        pt.close = p.price.history[-22].close * (1 - 0.002 * i)
    it = build_interpretation(p, PROVIDER)
    T.attrib_total += 1
    if it["coherence"] == "conflicting":
        T.attrib_pass += 1
    else:
        T.failures.append(f"{case['id']}: expected conflicting, got {it['coherence']}")


def case_no_advice(case):
    """HARD gate across every synthesised endpoint."""
    p = PROVIDER.retrieve(case["ticker"])
    outputs = {
        "analysis": build_analysis(p),
        "events": build_events(p),
        "interpret": build_interpretation(p, PROVIDER),
        "move": build_move(p, PROVIDER, target_date="2026-06-05"),
    }
    for name, out in outputs.items():
        hits = find_advice_terms(out)
        if hits:
            T.no_advice_ok = False
            T.advice_hits += [f"{name}:{h}" for h in hits]
            T.failures.append(f"{case['id']}/{name}: advice language {hits}")


DISPATCH = {
    "facts": case_facts,
    "citations": case_citations,
    "grounding": case_grounding,
    "grounding_violation": case_grounding_violation,
    "falsifiers": case_falsifiers,
    "events_bias": case_events_bias,
    "events_insufficient": case_events_insufficient,
    "attribution": case_attribution,
    "dcf_recompute": case_dcf_recompute,
    "dcf_guard": case_dcf_guard,
    "interpret_conflict": case_interpret_conflict,
    "no_advice": case_no_advice,
}


def main() -> int:
    for case in TESTSET["cases"]:
        fn = DISPATCH.get(case["type"])
        if fn:
            try:
                fn(case)
            except Exception as e:  # noqa: BLE001
                T.failures.append(f"{case['id']}: EXCEPTION {type(e).__name__}: {e}")

    accuracy_pass = T.fact_pass
    accuracy_total = T.fact_total

    print("\n" + "=" * 78)
    print("TEARSHEET EVAL")
    print("=" * 78)
    if T.failures:
        print("Failures:")
        for f in T.failures:
            print("  ✗ " + f)
    else:
        print("All checks passed.")

    no_advice = "PASS" if T.no_advice_ok else f"FAIL {T.advice_hits}"
    summary = (
        f"Accuracy: {T.pct(accuracy_pass, accuracy_total)} "
        f"({accuracy_pass}/{accuracy_total}) · "
        f"Citation validity: {T.pct(T.cite_ok, T.cite_total)} ({T.cite_ok}/{T.cite_total}) · "
        f"Hallucinations: {T.halluc}/{T.halluc_total} · "
        f"DCF checks: {T.dcf_pass}/{T.dcf_total} · "
        f"No-advice gate: {no_advice} · "
        f"Falsifiers: {T.falsif_pass}/{T.falsif_total} · "
        f"Attribution/conflict: {T.attrib_pass}/{T.attrib_total}"
    )
    print("-" * 78)
    print(summary)
    print("=" * 78)

    # Exit non-zero if the hard gate fails or any check failed.
    return 0 if (T.no_advice_ok and not T.failures) else 1


if __name__ == "__main__":
    sys.exit(main())
