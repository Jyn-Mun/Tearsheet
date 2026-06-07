"""AlpacaProvider — keyed, cloud-safe US-equity market data (price + daily bars + news).

This is the PRODUCTION market-data source. Alpaca authenticates by API key (header), so it is NOT
IP-blocked like Yahoo/yfinance — it works fine from a shared cloud IP. Free plan uses the IEX feed
(real-time-ish), which is plenty for a research tool. Keys come from env only.

Endpoints (data.alpaca.markets):
  /v2/stocks/{sym}/snapshot           → latest trade + daily/prev-daily bar (price, prev close)
  /v2/stocks/{sym}/bars?timeframe=1Day → ~2y daily history (52w range computed from this)
  /v1beta1/news?symbols={sym}          → real headlines

Market cap isn't in the API → computed downstream as price × EDGAR shares. Every external call is
gated by cache_policy.should_fetch_live() (request path never calls upstream in cache-only mode)
and cached on disk.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.cache_policy import read_ttl, should_fetch_live
from app.config import settings
from app.models.schemas import NewsItem, PriceData, PricePoint, Provenance
from app.utils import cache

_TTL = 60 * 5  # ~5 min live freshness


def _f(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AlpacaProvider:
    name = "Alpaca"

    def __init__(self) -> None:
        self._key = settings.alpaca_api_key_id
        self._secret = settings.alpaca_api_secret_key
        self._base = settings.alpaca_data_url
        self.rate_limited = False

    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": self._key or "", "APCA-API-SECRET-KEY": self._secret or ""}

    def _get(self, url: str, **params: Any) -> Any:
        if not should_fetch_live() or not self._key:
            return None  # cache-only request path (or no key) — never call upstream live
        import httpx

        try:
            r = httpx.get(url, params=params, headers=self._headers(), timeout=15.0)
            if r.status_code == 429:
                self.rate_limited = True
                return None
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    # ------------------------------------------------------------- market data

    def market_data(self, ticker: str) -> dict:
        ticker = ticker.upper().strip()
        cached = cache.get(f"alpaca:market:{ticker}", read_ttl(_TTL))
        if cached is not None:
            return {"price": PriceData.model_validate(cached["price"]),
                    "news": [NewsItem.model_validate(n) for n in cached["news"]],
                    "warnings": cached.get("warnings", [])}

        warnings: list[str] = []
        history = self.price_history(ticker)
        closes = [p.close for p in history]
        snap = self._get(f"{self._base}/v2/stocks/{ticker}/snapshot", feed="iex")
        price = PriceData(history=history)
        if snap:
            daily = snap.get("dailyBar") or {}
            prev = snap.get("prevDailyBar") or {}
            latest = snap.get("latestTrade") or {}
            cur = _f(latest.get("p")) or _f(daily.get("c")) or (closes[-1] if closes else None)
            pc = _f(prev.get("c")) or (closes[-2] if len(closes) >= 2 else None)
            yr = closes[-252:] if len(closes) >= 30 else closes
            price = PriceData(
                current=cur, previous_close=pc,
                change_abs=(cur - pc) if (cur is not None and pc is not None) else None,
                change_pct=((cur / pc - 1) if (cur and pc) else None),
                fifty_two_week_high=max(yr) if yr else None,
                fifty_two_week_low=min(yr) if yr else None,
                market_cap=None, beta=None, history=history,
            )
        elif closes:
            price = PriceData(current=closes[-1],
                              previous_close=closes[-2] if len(closes) >= 2 else None,
                              fifty_two_week_high=max(closes[-252:]), fifty_two_week_low=min(closes[-252:]),
                              history=history)
        elif self.rate_limited:
            warnings.append("Alpaca rate limit reached — price temporarily unavailable.")

        news = self._news(ticker)
        out = {"price": price, "news": news, "warnings": warnings}
        if price.current is not None:
            cache.set(f"alpaca:market:{ticker}", {"price": price.model_dump(),
                                                  "news": [n.model_dump() for n in news], "warnings": warnings})
        return out

    def price_history(self, ticker: str) -> list[PricePoint]:
        ticker = ticker.upper().strip()
        cached = cache.get(f"alpaca:hist:{ticker}", read_ttl(_TTL))
        if cached is not None:
            return [PricePoint(**p) for p in cached]
        # Memory guard: only request as far back as max_history_days (default ~1y) instead of a
        # fixed 2y window — fewer bars per ticker in RAM and in the cached payload.
        start = (datetime.now(timezone.utc)
                 - timedelta(days=settings.max_history_days)).date().isoformat()
        data = self._get(f"{self._base}/v2/stocks/{ticker}/bars",
                         timeframe="1Day", start=start, limit=settings.max_history_days,
                         adjustment="all", feed="iex")
        pts: list[PricePoint] = []
        bars = data.get("bars") if isinstance(data, dict) else None
        if isinstance(bars, list):
            for b in bars:  # Alpaca returns oldest-first
                c = _f(b.get("c"))
                t = b.get("t")
                if c is not None and t:
                    pts.append(PricePoint(date=t[:10], close=c))
        if pts:
            cache.set(f"alpaca:hist:{ticker}", [p.model_dump() for p in pts])
        return pts

    def peer_snapshot(self, ticker: str) -> dict:
        ticker = ticker.upper().strip()
        snap = self._get(f"{self._base}/v2/stocks/{ticker}/snapshot", feed="iex") or {}
        daily = snap.get("dailyBar") or {}
        return {"ticker": ticker, "name": None, "market_cap": None, "pe_ttm": None,
                "ev_ebitda": None, "ps": None, "pb": None, "price": _f(daily.get("c"))}

    def _news(self, ticker: str) -> list[NewsItem]:
        data = self._get(f"{self._base}/v1beta1/news", symbols=ticker, limit=10)
        items = data.get("news") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [
            NewsItem(title=n.get("headline") or "(untitled)", publisher=n.get("source"),
                     url=n.get("url"), published=n.get("created_at"),
                     summary=(n.get("summary") or "")[:300] or None)
            for n in items if n.get("headline")
        ]
