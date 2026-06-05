"""The synthesis layer, behind a swappable interface.

`Synthesizer` has three high-level methods (news / analysis / events narration). Two
implementations:
  - AnthropicSynthesizer: calls Claude with a grounded prompt + JSON schema (used when a key
    is present).
  - MockSynthesizer: deterministic, grounded output built directly from the retrieved data —
    so the whole app runs with NO key, and the eval's offline checks pass. Mock output is
    clearly labelled "[mock synthesis]" and still honours the grounding + no-advice contract.

`get_synthesizer()` returns the Anthropic one iff ANTHROPIC_API_KEY is set, else the mock.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.config import settings
from app.models.schemas import CompanyPayload
from app.services import prompts


def _yahoo_url(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker}"


def _pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def _first_news_url(payload: CompanyPayload) -> str | None:
    for n in payload.news:
        if n.url:
            return n.url
    return None


class Synthesizer(ABC):
    name = "base"

    @abstractmethod
    def news_summary(self, payload: CompanyPayload) -> dict: ...

    @abstractmethod
    def analysis(self, payload: CompanyPayload) -> dict: ...

    @abstractmethod
    def events_narration(self, ticker: str, stats: dict) -> dict: ...


# --------------------------------------------------------------------- mock


class MockSynthesizer(Synthesizer):
    """Deterministic, grounded synthesis from the data — no LLM. Honest, if less insightful."""

    name = "mock"

    def news_summary(self, payload: CompanyPayload) -> dict:
        bullets = [
            {"text": f"[mock] {n.title}", "source_url": n.url}
            for n in payload.news[:5]
        ]
        # Naive sentiment from headline keywords (clearly a heuristic, not the LLM).
        text = " ".join(n.title.lower() for n in payload.news)
        pos = sum(w in text for w in ("beat", "record", "surge", "raise", "growth", "demand"))
        neg = sum(w in text for w in ("slide", "fall", "cut", "miss", "probe", "lawsuit", "drop"))
        sentiment = "positive" if pos > neg else "negative" if neg > pos else "neutral"
        return {
            "bullets": bullets,
            "sentiment": sentiment,
            "key_risks": ["Headlines are descriptive only; see Analysis for a sourced thesis."],
            "synthesizer": self.name,
        }

    def analysis(self, payload: CompanyPayload) -> dict:
        km = payload.key_metrics
        url = _first_news_url(payload) or _yahoo_url(payload.ticker)
        inc = payload.financials.income
        rev_now = inc[0].revenue if inc else None
        margin = km.operating_margin

        bull = []
        if margin is not None and margin > 0.2:
            bull.append({
                "claim": f"[mock] Operating margin of {_pct(margin)} indicates strong unit economics.",
                "source_url": url,
                "falsifier": "Operating margin compressing below 20% over the next 2–3 prints.",
                "variant_view": "Consensus may underrate margin durability if pricing power persists.",
            })
        if km.roe is not None and km.roe > 0.2:
            bull.append({
                "claim": f"[mock] Return on equity of {_pct(km.roe)} shows efficient capital use.",
                "source_url": url,
                "falsifier": "ROE falling toward the cost of equity as competition intensifies.",
                "variant_view": "Market may extrapolate today's ROE without pricing mean reversion.",
            })
        if not bull:
            bull.append({
                "claim": "[mock] Insufficient data to construct a high-conviction bull point.",
                "source_url": url,
                "falsifier": "A profitable, growing quarter would establish one.",
                "variant_view": None,
            })

        bear = []
        if km.pe_ttm is not None and km.pe_ttm > 30:
            bear.append({
                "claim": f"[mock] Trailing P/E of {km.pe_ttm:.1f}x embeds high growth expectations.",
                "source_url": url,
                "falsifier": "A re-rating lower if growth decelerates below what the multiple implies.",
                "variant_view": "Bulls assume the multiple is justified by durable growth; that's the debate.",
            })
        bear.append({
            "claim": "[mock] Single-source (Yahoo) data limits provenance granularity vs filings.",
            "source_url": _yahoo_url(payload.ticker),
            "falsifier": "Adding the EDGAR provider would resolve figures to specific filings.",
            "variant_view": None,
        })

        premortem = (
            "[mock] If this thesis fails in ~2 years, the most likely reason in the supplied data is "
            + ("multiple compression as growth normalises." if (km.pe_ttm or 0) > 30
               else "margin erosion reducing the cash flows the value rests on.")
        )
        return {
            "snapshot": f"[mock synthesis] {payload.profile.name or payload.ticker} — "
                        f"{payload.profile.sector or 'n/a'} / {payload.profile.industry or 'n/a'}. "
                        f"Latest revenue: {rev_now:,.0f} {payload.profile.currency or ''}." if rev_now
                        else f"[mock synthesis] {payload.profile.name or payload.ticker}.",
            "recent_developments": [
                {"date": n.published, "text": f"[mock] {n.title}", "source_url": n.url}
                for n in payload.news[:3]
            ],
            "bull_case": bull,
            "bear_case": bear,
            "catalysts": ["[mock] Next earnings print", "[mock] Sector/macro repricing"],
            "risks": ["[mock] Valuation risk", "[mock] Data-source fragility"],
            "thesis": [
                "[mock] This is a deterministic placeholder thesis built from retrieved metrics.",
                "[mock] Every point above ships a falsifier per the reasoning contract.",
                "[mock] No numbers appear that aren't in the retrieved payload.",
                "[mock] Output stays at interpretation; it expresses no recommendation or target.",
                "[mock] Add an ANTHROPIC_API_KEY for genuine LLM reasoning.",
            ],
            "watch_next": "[mock] Watch the next earnings print and any change to the growth path.",
            "premortem": premortem,
            "synthesizer": self.name,
        }

    def events_narration(self, ticker: str, stats: dict) -> dict:
        eb = stats.get("earnings_behaviour", {})
        n = eb.get("n_reports", 0)
        beats = eb.get("beat_count", 0)
        post = eb.get("post_window", {})
        up = post.get("hit_rate")
        note = (
            f"[mock] Beat estimates in {beats}/{n} reports, yet the stock rose in only "
            f"{_pct(up) if up is not None else 'n/a'} of post-earnings windows — 'beats' and "
            f"'stock up' are different things and here they diverge."
            if n else "[mock] Insufficient earnings history to characterise behaviour."
        )
        return {
            "narration": f"[mock] Descriptive earnings/seasonality stats for {ticker} (n={n}). "
                         "Historical behaviour is not predictive; known effects are arbitraged and decay.",
            "beat_vs_move_note": note,
            "synthesizer": self.name,
        }


# ----------------------------------------------------------------- anthropic


class AnthropicSynthesizer(Synthesizer):
    """Grounded synthesis via Claude (claude-opus-4-8). Used only when a key is configured."""

    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def _complete_json(self, system: str, user: str, schema: dict, effort: str = "medium") -> dict:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        data["synthesizer"] = self.name
        return data

    def news_summary(self, payload: CompanyPayload) -> dict:
        headlines = [
            {"title": n.title, "publisher": n.publisher, "url": n.url, "published": n.published}
            for n in payload.news
        ]
        user = "Summarise these headlines.\nDATA:\n" + json.dumps(headlines, indent=2)
        return self._complete_json(prompts.NEWS_SYSTEM, user, prompts.NEWS_SCHEMA, effort="low")

    def analysis(self, payload: CompanyPayload) -> dict:
        # Supply only the retrieved payload; the prompt forbids using anything else.
        user = (
            "Produce a sourced, falsifiable, two-sided analysis from ONLY this retrieved data. "
            "Every bull/bear point needs a falsifier. End risks with the pre-mortem.\nDATA:\n"
            + json.dumps(payload.model_dump(), indent=2, default=str)
        )
        return self._complete_json(prompts.ANALYSIS_SYSTEM, user, prompts.ANALYSIS_SCHEMA, effort="high")

    def events_narration(self, ticker: str, stats: dict) -> dict:
        user = (
            f"Narrate these precomputed statistics for {ticker}. Distinguish beats from up-moves.\n"
            "STATS:\n" + json.dumps(stats, indent=2, default=str)
        )
        return self._complete_json(
            prompts.EVENTS_NARRATION_SYSTEM, user, prompts.EVENTS_NARRATION_SCHEMA, effort="low"
        )


_SYNTH: Synthesizer | None = None


def get_synthesizer() -> Synthesizer:
    global _SYNTH
    if _SYNTH is None:
        _SYNTH = AnthropicSynthesizer() if settings.anthropic_api_key else MockSynthesizer()
    return _SYNTH
