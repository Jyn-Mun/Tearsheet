"""Runtime guards enforcing the addendum's hard invariants on synthesised output:
no-advice language, and a falsifier on every bull/bear point. Reused by the eval harness.

The no-advice check is NEGATION-AWARE: it flags advice language only when it is actually being
given, not when it is being disclaimed ("no buy/sell/hold", "not a recommendation"). A naive
substring match produces false positives on legitimate disclaimers, so we tokenise and skip any
advice term preceded (within a small window) by a negation cue.
"""

from __future__ import annotations

import re

from app.services.prompts import ADVICE_TERMS

_NEGATIONS = {"no", "not", "never", "without", "isn", "aren", "don", "doesn", "wont", "nor", "neither", "non"}
_WINDOW = 5  # tokens to look back for a negation cue


def find_advice_terms(obj) -> list[str]:
    """Return advice phrases that appear as actual advice (not negated/disclaimed)."""
    text = _stringify(obj).lower().replace("/", " ")
    tokens = re.findall(r"[a-z]+", text)
    hits: set[str] = set()
    for term in ADVICE_TERMS:
        term_tokens = term.split()
        for i in range(len(tokens) - len(term_tokens) + 1):
            if tokens[i:i + len(term_tokens)] == term_tokens:
                window = tokens[max(0, i - _WINDOW):i]
                if not any(w in _NEGATIONS for w in window):
                    hits.add(term)
                    break
    return sorted(hits)


def missing_falsifiers(analysis: dict) -> list[str]:
    """Return labels of bull/bear points lacking a non-empty falsifier."""
    bad = []
    for side in ("bull_case", "bear_case"):
        for i, pt in enumerate(analysis.get(side, [])):
            if not (isinstance(pt, dict) and pt.get("falsifier", "").strip()):
                bad.append(f"{side}[{i}]")
    return bad


def _stringify(obj) -> str:
    import json

    return json.dumps(obj, default=str)
