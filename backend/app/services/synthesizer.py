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


AI_DISABLED_NOTE = (
    "AI narrative disabled — add an ANTHROPIC_API_KEY (or run a local Ollama model) to enable "
    "real synthesis. All numeric sections (financials, multiples, DCF, price, news) work without it."
)


class Synthesizer(ABC):
    name = "base"
    ai_enabled = False  # True only when a real LLM (Anthropic/Ollama) is producing the text

    @abstractmethod
    def news_summary(self, payload: CompanyPayload) -> dict: ...

    @abstractmethod
    def analysis(self, payload: CompanyPayload) -> dict: ...

    @abstractmethod
    def events_narration(self, ticker: str, stats: dict) -> dict: ...


# --------------------------------------------------------------------- mock


class MockSynthesizer(Synthesizer):
    """No-LLM fallback. Produces a clean, grounded RULE-BASED draft from the retrieved figures
    (every point still data-derived and falsifiable), and flags ai_enabled=False so the UI can
    show an honest 'AI narrative disabled' note. No '[mock]' filler text."""

    name = "rule-based"
    ai_enabled = False

    def news_summary(self, payload: CompanyPayload) -> dict:
        # No LLM: don't fabricate a summary. Return headlines + a heuristic sentiment, labelled.
        text = " ".join(n.title.lower() for n in payload.news)
        pos = sum(w in text for w in ("beat", "record", "surge", "raise", "growth", "demand", "upgrade"))
        neg = sum(w in text for w in ("slide", "fall", "cut", "miss", "probe", "lawsuit", "drop", "downgrade"))
        sentiment = "positive" if pos > neg else "negative" if neg > pos else "neutral"
        return {
            "bullets": [],
            "sentiment": sentiment,
            "sentiment_basis": "keyword heuristic (no AI key)",
            "key_risks": [],
            "ai_enabled": False,
            "note": AI_DISABLED_NOTE,
            "synthesizer": self.name,
        }

    def analysis(self, payload: CompanyPayload) -> dict:
        km = payload.key_metrics
        url = _first_news_url(payload) or _yahoo_url(payload.ticker)
        inc = payload.financials.income
        rev_now = inc[0].revenue if inc else None
        cur = payload.profile.currency or ""

        bull, bear = [], []
        if km.operating_margin is not None and km.operating_margin > 0.2:
            bull.append({
                "claim": f"Operating margin of {_pct(km.operating_margin)} indicates strong unit economics.",
                "source_url": url,
                "falsifier": "Operating margin compressing below 20% over the next 2–3 reports.",
                "variant_view": "Consensus may underrate margin durability if pricing power persists.",
            })
        if km.roe is not None and km.roe > 0.2:
            bull.append({
                "claim": f"Return on equity of {_pct(km.roe)} shows efficient use of capital.",
                "source_url": url,
                "falsifier": "ROE falling toward the cost of equity as competition intensifies.",
                "variant_view": "The market may extrapolate today's ROE without pricing mean reversion.",
            })
        if not bull:
            bull.append({
                "claim": "Profitability/returns are not strong enough in the filings to anchor a bull point.",
                "source_url": url,
                "falsifier": "A profitable, growing quarter would establish one.",
                "variant_view": None,
            })
        if km.pe_ttm is not None and km.pe_ttm > 30:
            bear.append({
                "claim": f"Trailing P/E of {km.pe_ttm:.1f}x embeds high growth expectations.",
                "source_url": url,
                "falsifier": "A de-rating if growth decelerates below what the multiple implies.",
                "variant_view": "Bulls assume the multiple is justified by durable growth — that's the debate.",
            })
        bear.append({
            "claim": "Without an AI key, this draft is rule-based and may miss qualitative drivers.",
            "source_url": url,
            "falsifier": "Enabling AI synthesis would add narrative depth beyond the metrics.",
            "variant_view": None,
        })

        premortem = (
            "If this thesis fails in ~2 years, the most likely reason in the filings is "
            + ("multiple compression as growth normalises." if (km.pe_ttm or 0) > 30
               else "margin erosion reducing the cash flows the value rests on.")
        )
        snapshot = (
            f"{payload.profile.name or payload.ticker} — {payload.profile.sector or 'n/a'} / "
            f"{payload.profile.industry or 'n/a'}."
            + (f" Latest revenue {rev_now:,.0f} {cur}." if rev_now else "")
        )
        return {
            "snapshot": snapshot,
            "recent_developments": [
                {"date": n.published, "text": n.title, "source_url": n.url} for n in payload.news[:3]
            ],
            "bull_case": bull,
            "bear_case": bear,
            "catalysts": ["Next earnings report", "Sector / macro repricing"],
            "risks": ["Valuation risk", "Execution risk"],
            "thesis": [
                "Rule-based draft built from the retrieved filings — every point ships a falsifier.",
                "No numbers appear that aren't in the retrieved payload.",
                "No recommendation or price target is expressed.",
            ],
            "watch_next": "Watch the next earnings report and any change to the revenue growth path.",
            "premortem": premortem,
            "ai_enabled": False,
            "note": AI_DISABLED_NOTE,
            "synthesizer": self.name,
        }

    def events_narration(self, ticker: str, stats: dict) -> dict:
        eb = stats.get("earnings_behaviour", {})
        n = eb.get("n_reports", 0)
        beats = eb.get("beat_count", 0)
        up = eb.get("post_window", {}).get("hit_rate")
        note = (
            f"Beat estimates in {beats}/{n} reports, yet the stock rose in only "
            f"{_pct(up) if up is not None else 'n/a'} of post-earnings windows — 'beats' and "
            f"'stock up' are different things, and here they diverge."
            if n else "Insufficient earnings history to characterise behaviour."
        )
        return {
            "narration": f"Descriptive earnings/seasonality statistics for {ticker} (n={n}). "
                         "Historical behaviour is not predictive; known effects are arbitraged and decay.",
            "beat_vs_move_note": note,
            "ai_enabled": False,
            "synthesizer": self.name,
        }


# ----------------------------------------------------------------- anthropic


class AnthropicSynthesizer(Synthesizer):
    """Grounded synthesis via Claude (claude-opus-4-8). Used only when a key is configured."""

    name = "anthropic"
    ai_enabled = True

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


class OllamaSynthesizer(Synthesizer):
    """Free local-LLM synthesis via Ollama (http://localhost:11434), behind the same interface.
    Enabled when `OLLAMA_MODEL` is set and no Anthropic key is present."""

    name = "ollama"
    ai_enabled = True

    def __init__(self) -> None:
        self._model = settings.ollama_model
        self._base = settings.ollama_base_url

    def _complete_json(self, system: str, user: str, schema: dict) -> dict:
        import httpx

        prompt = f"{system}\n\n{user}\n\nReturn ONLY valid JSON matching the required fields."
        r = httpx.post(
            f"{self._base}/api/generate",
            json={"model": self._model, "prompt": prompt, "format": "json", "stream": False,
                  "options": {"temperature": 0.4}},
            timeout=120.0,
        )
        r.raise_for_status()
        text = r.json().get("response", "").strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        data["synthesizer"] = self.name
        data["ai_enabled"] = True
        return data

    def news_summary(self, payload: CompanyPayload) -> dict:
        headlines = [{"title": n.title, "url": n.url, "published": n.published} for n in payload.news]
        return self._complete_json(prompts.NEWS_SYSTEM,
                                   "Summarise these headlines.\nDATA:\n" + json.dumps(headlines),
                                   prompts.NEWS_SCHEMA)

    def analysis(self, payload: CompanyPayload) -> dict:
        return self._complete_json(
            prompts.ANALYSIS_SYSTEM,
            "Produce a sourced, falsifiable, two-sided analysis from ONLY this data. Every bull/bear "
            "point needs a falsifier; end risks with the pre-mortem.\nDATA:\n"
            + json.dumps(payload.model_dump(), default=str),
            prompts.ANALYSIS_SCHEMA)

    def events_narration(self, ticker: str, stats: dict) -> dict:
        return self._complete_json(
            prompts.EVENTS_NARRATION_SYSTEM,
            f"Narrate these statistics for {ticker}; distinguish beats from up-moves.\nSTATS:\n"
            + json.dumps(stats, default=str),
            prompts.EVENTS_NARRATION_SCHEMA)


_SYNTH: Synthesizer | None = None


def get_synthesizer() -> Synthesizer:
    """Anthropic (if key) → Ollama (if OLLAMA_MODEL set) → rule-based mock. Keys read from env only."""
    global _SYNTH
    if _SYNTH is None:
        if settings.anthropic_api_key:
            _SYNTH = AnthropicSynthesizer()
        elif settings.ollama_model:
            _SYNTH = OllamaSynthesizer()
        else:
            _SYNTH = MockSynthesizer()
    return _SYNTH
