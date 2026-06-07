"""AlpacaProvider — keyed, cloud-safe US-equity market data (price + daily bars + news).

This is the PRODUCTION market-data source. Alpaca authenticates by API key (header), so it is NOT
IP-blocked like Yahoo/yfinance — it works fine from a shared cloud IP. Free plan uses the IEX feed
(real-time-ish), which is plenty for a research tool. Keys come from env only.

Every market-data call explicitly sends feed=<settings.alpaca_feed> (default "iex"): the FREE
plan only includes IEX, and an implicit/SIP request returns empty on free. Set ALPACA_FEED=sip
only if you upgrade. The feed + HTTP status of every call is logged so IEX usage is verifiable.

Endpoints (data.alpaca.markets), all with &feed=iex:
  /v2/stocks/{sym}/snapshot           → latest trade + daily/prev-daily bar (price, prev close)
  /v2/stocks/{sym}/bars?timeframe=1Day → ~1y daily history (auto-widens if IEX returns too few)
  /v1beta1/news?symbols={sym}          → real headlines (not feed-gated)

Market cap isn't in the API → computed downstream as price × EDGAR shares. Every external call is
gated by cache_policy.should_fetch_live() (request path never calls upstream in cache-only mode)
and cached on disk.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.cache_policy import read_ttl, should_fetch_live
from app.config import settings
from app.models.schemas import NewsItem, PriceData, PricePoint, Provenance
from app.utils import cache

log = logging.getLogger("tearsheet")

_TTL = 60 * 5  # ~5 min live freshness
_MIN_BARS = 30  # below this the sparkline/52w range is too thin — widen the IEX lookback and retry


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
        self._feed = (settings.alpaca_feed or "iex").lower()  # FREE tier = iex
        self.rate_limited = False
        self._last_status: int | str | None = None  # HTTP status of the most recent call (for logs)
        self._warned_no_key = False

    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": self._key or "", "APCA-API-SECRET-KEY": self._secret or ""}

    def _get(self, url: str, **params: Any) -> Any:
        endpoint = url.split("/v2/")[-1].split("/v1beta1/")[-1]  # short label for logs
        feed = params.get("feed", "n/a")
        # --- previously-silent early returns: now explained in the logs ---
        if not self._key:
            self._last_status = "no-key"
            if not self._warned_no_key:  # log once, not per request
                log.warning("Alpaca: NO API KEY loaded — price calls skipped (set ALPACA_API_KEY_ID/"
                            "ALPACA_API_SECRET_KEY or APCA_API_KEY_ID/APCA_API_SECRET_KEY)")
                self._warned_no_key = True
            return None
        if not should_fetch_live():
            # Cache-only request path: by design we don't call upstream here — the prefetch job does.
            self._last_status = "cache-only"
            log.info("Alpaca %s feed=%s skipped: serve-from-cache-only (request path)", endpoint, feed)
            return None

        import httpx

        try:
            r = httpx.get(url, params=params, headers=self._headers(), timeout=15.0)
            self._last_status = r.status_code
            if r.status_code == 429:
                self.rate_limited = True
                log.warning("Alpaca 429 RATE-LIMITED on %s feed=%s: %s", endpoint, feed, r.text[:300])
                return None
            if r.status_code >= 400:
                # The FULL error: status + body. A SIP request on the free plan shows up here as
                # 403/422 with a body like "subscription does not permit querying recent SIP data".
                log.warning("Alpaca HTTP %s on %s feed=%s — body: %s",
                            r.status_code, endpoint, feed, r.text[:500])
                return None
            return r.json()
        except Exception as e:  # noqa: BLE001 — graceful failure preserved, but now fully logged
            self._last_status = "exception"
            log.warning("Alpaca request to %s feed=%s raised %s: %s",
                        endpoint, feed, type(e).__name__, e)
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
        snap = self._get(f"{self._base}/v2/stocks/{ticker}/snapshot", feed=self._feed)
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

        # One-line per-fetch summary for the snapshot/quote call: ticker, feed, status, price.
        log.info("Alpaca snap   %-6s feed=%s HTTP=%s current=%s closes=%d",
                 ticker, self._feed, self._last_status, price.current, len(closes))

        news = self._news(ticker)
        out = {"price": price, "news": news, "warnings": warnings}
        if price.current is not None:
            cache.set(f"alpaca:market:{ticker}", {"price": price.model_dump(),
                                                  "news": [n.model_dump() for n in news], "warnings": warnings})
        return out

    def _bars(self, ticker: str, lookback_days: int) -> list[PricePoint]:
        """Fetch daily-close bars over the last `lookback_days` from the IEX feed (oldest-first)."""
        start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
        data = self._get(f"{self._base}/v2/stocks/{ticker}/bars",
                         timeframe="1Day", start=start, limit=10000,
                         adjustment="all", feed=self._feed)
        pts: list[PricePoint] = []
        bars = data.get("bars") if isinstance(data, dict) else None
        if isinstance(bars, list):
            for b in bars:  # Alpaca returns oldest-first
                c = _f(b.get("c"))
                t = b.get("t")
                if c is not None and t:
                    pts.append(PricePoint(date=t[:10], close=c))
        # One-line per-fetch summary: ticker, feed, HTTP status, bar count.
        log.info("Alpaca bars   %-6s feed=%s HTTP=%s bars=%d (lookback=%dd)",
                 ticker, self._feed, self._last_status, len(pts), lookback_days)
        return pts

    def price_history(self, ticker: str) -> list[PricePoint]:
        ticker = ticker.upper().strip()
        cached = cache.get(f"alpaca:hist:{ticker}", read_ttl(_TTL))
        if cached is not None:
            return [PricePoint(**p) for p in cached]
        # Memory guard: request ~max_history_days (default ~1y) of daily bars, not a fixed 2y window.
        pts = self._bars(ticker, settings.max_history_days)
        # IEX has thinner coverage than SIP, so a 1y window can come back short for some symbols
        # (incl. sector ETFs). If we got too few points to draw a sparkline / 52w range, widen the
        # lookback once and retry — keeps the chart populated on the free feed.
        if len(pts) < _MIN_BARS and should_fetch_live() and not self.rate_limited:
            wider = max(settings.max_history_days * 3, 1095)  # ≥3y
            log.info("Alpaca IEX returned %d bars for %s (<%d); retrying with %d-day lookback",
                     len(pts), ticker, _MIN_BARS, wider)
            pts = self._bars(ticker, wider) or pts
            # Cap back to the memory budget once we have enough — keep the most recent points.
            if len(pts) > settings.max_history_days:
                pts = pts[-settings.max_history_days:]
        if pts:
            cache.set(f"alpaca:hist:{ticker}", [p.model_dump() for p in pts])
        return pts

    def peer_snapshot(self, ticker: str) -> dict:
        ticker = ticker.upper().strip()
        snap = self._get(f"{self._base}/v2/stocks/{ticker}/snapshot", feed=self._feed) or {}
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
