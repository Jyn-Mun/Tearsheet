"""TwelveDataProvider — free, cloud-friendly market data (price + daily history).

yfinance scrapes Yahoo and is blocked from datacenter IPs (Render/AWS), so it can't serve prices
in production. Twelve Data is a key-based API that authenticates per-key (no IP blocks) with a free
tier (800 calls/day): /quote gives the latest price + 52-week range, /time_series gives daily
history. Market cap isn't in the free quote, so it's computed downstream as price × EDGAR shares.

Exposes the same market-data surface the hybrid uses: market_data() + price_history(). Cached ~5
min on disk. Degrades gracefully (rate-limit / error → empty, with a note).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models.schemas import NewsItem, PriceData, PricePoint, Provenance
from app.utils import cache

_TTL = 60 * 5  # ~5 min


def _f(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TwelveDataProvider:
    name = "Twelve Data"

    def __init__(self) -> None:
        self._key = settings.twelvedata_api_key
        self._base = settings.twelvedata_base_url
        self.rate_limited = False

    def _get(self, endpoint: str, **params: Any) -> Any:
        import httpx

        params["apikey"] = self._key
        try:
            r = httpx.get(f"{self._base}/{endpoint}", params=params, timeout=15.0)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("status") == "error":
                if str(data.get("code")) == "429":
                    self.rate_limited = True
                return None
            return data
        except Exception:
            return None

    # ------------------------------------------------------------- market data

    def market_data(self, ticker: str) -> dict:
        ticker = ticker.upper().strip()
        cached = cache.get(f"td:market:{ticker}", _TTL)
        if cached is not None:
            return {"price": PriceData.model_validate(cached["price"]),
                    "news": [NewsItem.model_validate(n) for n in cached["news"]],
                    "warnings": cached.get("warnings", [])}

        warnings: list[str] = []
        q = self._get("quote", symbol=ticker)
        history = self.price_history(ticker)
        price = PriceData(history=history)
        if q:
            cur = _f(q.get("close"))
            prev = _f(q.get("previous_close"))
            pct = _f(q.get("percent_change"))
            fw = q.get("fifty_two_week") or {}
            price = PriceData(
                current=cur, previous_close=prev,
                change_abs=_f(q.get("change")),
                change_pct=(pct / 100.0) if pct is not None else None,
                fifty_two_week_high=_f(fw.get("high")), fifty_two_week_low=_f(fw.get("low")),
                market_cap=None,  # computed downstream as price × EDGAR shares
                beta=None, history=history,
            )
        elif self.rate_limited:
            warnings.append("Twelve Data free daily/rate limit reached — price temporarily unavailable.")
        else:
            warnings.append("No price returned from Twelve Data for this ticker.")

        news = self._rss_news(ticker)
        out = {"price": price, "news": news, "warnings": warnings}
        if price.current is not None:
            cache.set(f"td:market:{ticker}", {"price": price.model_dump(),
                                              "news": [n.model_dump() for n in news], "warnings": warnings})
        return out

    def price_history(self, ticker: str) -> list[PricePoint]:
        ticker = ticker.upper().strip()
        cached = cache.get(f"td:hist:{ticker}", _TTL)
        if cached is not None:
            return [PricePoint(**p) for p in cached]
        data = self._get("time_series", symbol=ticker, interval="1day", outputsize=520, order="ASC")
        pts: list[PricePoint] = []
        values = data.get("values") if isinstance(data, dict) else None
        if isinstance(values, list):
            for row in values:  # order=ASC → already oldest-first
                c = _f(row.get("close"))
                d = row.get("datetime")
                if c is not None and d:
                    pts.append(PricePoint(date=d[:10], close=c))
        if pts:
            cache.set(f"td:hist:{ticker}", [p.model_dump() for p in pts])
        return pts

    # peer snapshot: only needs price (for multiples) — reuse quote.
    def peer_snapshot(self, ticker: str) -> dict:
        q = self._get("quote", symbol=ticker.upper().strip()) or {}
        return {"ticker": ticker.upper(), "name": q.get("name"), "market_cap": None,
                "pe_ttm": None, "ev_ebitda": None, "ps": None, "pb": None,
                "price": _f(q.get("close"))}

    def _rss_news(self, ticker: str) -> list[NewsItem]:
        """Free Yahoo RSS headlines (different host than the blocked quote API; often reachable)."""
        import httpx

        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        try:
            r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            items = []
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                if not title:
                    continue
                items.append(NewsItem(title=title, publisher="Yahoo Finance RSS",
                                      url=(it.findtext("link") or None),
                                      published=(it.findtext("pubDate") or None)))
                if len(items) >= 10:
                    break
            return items
        except Exception:
            return []
