"""/news/{ticker}: headlines + AI bullet summary + sentiment + key risks, each linking its source."""

from __future__ import annotations

from app.models.schemas import CompanyPayload
from app.services.guards import find_advice_terms
from app.services.synthesizer import get_synthesizer


def build_news(payload: CompanyPayload) -> dict:
    headlines = [
        {
            "title": n.title,
            "publisher": n.publisher,
            "url": n.url,
            "published": n.published,
            "summary": n.summary,
        }
        for n in payload.news
    ]
    synth = get_synthesizer()
    if not payload.news:
        return {
            "ticker": payload.ticker,
            "source": payload.source,
            "headlines": [],
            "summary": None,
            "ai_enabled": synth.ai_enabled,
            "message": "No recent headlines.",
            "warnings": payload.warnings,
        }

    summary = synth.news_summary(payload)
    return {
        "ticker": payload.ticker,
        "source": payload.source,
        "headlines": headlines,
        "summary": summary,
        "ai_enabled": synth.ai_enabled,
        "advice_terms_found": find_advice_terms(summary),  # must be [] — surfaced for transparency
        "warnings": payload.warnings,
        "disclaimer": "AI summary of public headlines · not financial advice.",
    }
