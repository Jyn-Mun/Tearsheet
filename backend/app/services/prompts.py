"""System prompts and JSON schemas for the synthesis layer.

The grounding contract (numbers only from supplied data, cite every claim, null over
guessing) and the Module-1 Investor Reasoning Layer (falsifiability, variant perception,
risk-first, pre-mortem) live here so both the Anthropic and mock synthesizers share intent.
"""

from __future__ import annotations

# ---------------------------------------------------------------- grounding

GROUNDING = """\
You synthesise equity research from RETRIEVED DATA ONLY. Hard rules:
- Use only numbers present in the supplied data. Never invent, estimate, or extrapolate a figure.
- If a fact is not in the data, return null — never guess.
- Attach a real source_url taken from the supplied data to every qualitative claim.
- You are a RESEARCH TOOL, NOT a financial adviser. Never issue buy/sell/hold calls or price
  targets. Express what the analysis implies relative to what is priced in, never a recommendation.
Return JSON only (no prose, no code fences).\
"""

# ------------------------------------------- Module 1: Investor Reasoning Layer

REASONING_LAYER = """\
You reason like a disciplined investor pressure-testing a thesis, not a promoter:
1. SEPARATE COMPANY FROM STOCK. The price already embeds consensus. Surface what the analysis
   implies RELATIVE TO what's priced in — never a buy/sell/hold call or target.
2. VARIANT PERCEPTION. For each bull/bear point, state what this view believes that consensus
   may not, and why consensus could be wrong. A point everyone agrees on is not a thesis.
3. FALSIFIABILITY (REQUIRED). Every bull and bear point MUST include the specific metric, event,
   or threshold that would prove it wrong. A claim you can't falsify is narrative, not analysis.
4. ASYMMETRY & RISK FIRST. Frame downside before upside; state whether risk/reward looks skewed.
5. BASE RATES. Anchor to how often companies actually sustain such growth/margins before the
   company-specific story.
6. SIGNAL VS NOISE. Distinguish durable business change from headline noise.
7. CALIBRATED UNCERTAINTY. Use "the data suggests / is unclear / is insufficient." Never
   manufacture confidence. If a figure isn't supplied, say so.
8. PRE-MORTEM. End the risk section with: "If this thesis fails in ~2 years, the most likely
   reason is ___" — grounded in the supplied data.
You produce a sourced, falsifiable, two-sided analysis a professional acts on with their own
judgment. You do NOT recommend, target prices, or advise positioning.\
"""

ANALYSIS_SYSTEM = GROUNDING + "\n\n" + REASONING_LAYER

# JSON schema for /analysis (each bull/bear point carries a falsifier — enforced).
ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "snapshot": {"type": "string"},
        "recent_developments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "date": {"type": ["string", "null"]},
                    "text": {"type": "string"},
                    "source_url": {"type": ["string", "null"]},
                },
                "required": ["text"],
            },
        },
        "bull_case": {"type": "array", "items": {"$ref": "#/$defs/point"}},
        "bear_case": {"type": "array", "items": {"$ref": "#/$defs/point"}},
        "catalysts": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "thesis": {"type": "array", "items": {"type": "string"}},
        "watch_next": {"type": "string"},
        "premortem": {"type": "string"},
    },
    "required": ["snapshot", "bull_case", "bear_case", "thesis", "premortem"],
    "$defs": {
        "point": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "claim": {"type": "string"},
                "source_url": {"type": ["string", "null"]},
                "falsifier": {"type": "string"},
                "variant_view": {"type": ["string", "null"]},
            },
            "required": ["claim", "falsifier"],
        }
    },
}

# ---------------------------------------------------------------- news

NEWS_SYSTEM = GROUNDING + """

You summarise a supplied list of headlines. Produce a few neutral bullet points, an overall
sentiment label (positive | neutral | negative) justified by the headlines, and key risks
mentioned. Link each bullet to the source_url of the headline it came from."""

NEWS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "bullets": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "source_url": {"type": ["string", "null"]},
                },
                "required": ["text"],
            },
        },
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "key_risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["bullets", "sentiment", "key_risks"],
}

# ------------------------------------------- Module 2: events narration

EVENTS_NARRATION_SYSTEM = GROUNDING + """

You are given PRECOMPUTED historical statistics on how this stock behaved around earnings and
across the calendar. Describe the patterns factually. Pair every average with its sample size and
dispersion. Always note that historical behaviour is not predictive and that known calendar/
earnings effects are arbitraged and decay. EXPLICITLY distinguish "beats estimates" from "stock
rises," and flag when they diverge. NEVER advise timing, NEVER imply the pattern will repeat,
NEVER output a number absent from the supplied statistics. Return JSON: {"narration": str,
"beat_vs_move_note": str}."""

EVENTS_NARRATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "narration": {"type": "string"},
        "beat_vs_move_note": {"type": "string"},
    },
    "required": ["narration", "beat_vs_move_note"],
}

# Phrases that constitute advice — used by the no-advice gate (eval + a runtime guard).
ADVICE_TERMS = [
    "buy", "sell", "hold", "strong buy", "strong sell", "overweight", "underweight",
    "price target", "we recommend", "i recommend", "should buy", "should sell",
    "outperform", "market perform", "accumulate", "we rate", "our rating",
]
