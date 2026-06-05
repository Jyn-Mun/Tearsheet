"""/analysis/{ticker}: grounded, falsifiable, two-sided thesis (Module 1 reasoning layer).

Enforces the hard invariants at runtime: every bull/bear point must carry a falsifier, and the
output must contain no buy/sell/hold/target language. Violations are surfaced (not silently
dropped) so the eval harness and UI can see them.
"""

from __future__ import annotations

from app.models.schemas import CompanyPayload
from app.services.guards import find_advice_terms, missing_falsifiers
from app.services.synthesizer import get_synthesizer


def build_analysis(payload: CompanyPayload) -> dict:
    analysis = get_synthesizer().analysis(payload)

    advice = find_advice_terms(analysis)
    missing = missing_falsifiers(analysis)

    return {
        "ticker": payload.ticker,
        "source": payload.source,
        "as_of": payload.as_of,
        "analysis": analysis,
        "invariants": {
            "no_advice": {"passed": not advice, "violations": advice},
            "falsifiers_present": {"passed": not missing, "violations": missing},
        },
        "warnings": payload.warnings,
        "disclaimer": "Model output with stated assumptions · research tool, not financial advice · "
                      "no buy/sell/hold, no price target.",
    }
