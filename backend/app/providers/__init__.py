"""providers package — the data swap point.

`get_provider(mode)` returns the data source for a request:
  - mode="offline" → FixtureProvider (recorded snapshots; always works, no network/limit).
  - mode="live"    → the configured live provider with a snapshot fallback: it tries the real
                     API and, if that returns nothing (rate-limit/coverage), transparently serves
                     a recorded snapshot for that ticker — clearly flagged, never passed off as live.
  - mode=None      → the default for the deployment (settings.data_provider).

This powers the UI's Live/Offline toggle and its honest data badge.
"""

from __future__ import annotations

from app.config import settings
from app.models.schemas import CompanyPayload
from app.providers.base import DataProvider
from app.providers.edgar_provider import EdgarProvider
from app.providers.fixture_provider import FixtureProvider
from app.providers.free_provider import FreeProvider
from app.providers.hybrid_provider import HybridProvider


def _is_empty(p: CompanyPayload) -> bool:
    return p.price.current is None and not p.financials.income and not p.profile.name


class _WithSnapshotFallback(DataProvider):
    """Wrap a live provider so that, on an empty result, it serves a recorded snapshot (flagged)."""

    def __init__(self, live: DataProvider, label: str) -> None:
        self._live = live
        self._fix = FixtureProvider()
        self.name = label

    def retrieve(self, ticker: str) -> CompanyPayload:
        payload = self._live.retrieve(ticker)
        if _is_empty(payload) and ticker.upper().strip() in self._fix.available():
            fb = self._fix.retrieve(ticker)
            fb.warnings.insert(
                0,
                "Live data was unavailable (rate-limit/coverage); showing a recorded SNAPSHOT for "
                "this ticker. Not live market data.",
            )
            return fb
        if _is_empty(payload):
            payload.warnings.insert(
                0,
                "Live data unavailable for this ticker (rate-limit, coverage, or daily limit) and "
                "no offline snapshot exists for it. Try a snapshotted ticker, or switch to Offline.",
            )
        return payload

    # Lightweight methods pass through to the live provider (peers/ETFs); they tolerate emptiness.
    def peer_snapshot(self, ticker: str) -> dict:
        snap = self._live.peer_snapshot(ticker)
        if snap.get("market_cap") is None and ticker.upper().strip() in self._fix.available():
            return self._fix.peer_snapshot(ticker)
        return snap

    def price_history(self, ticker: str):
        hist = self._live.price_history(ticker)
        if not hist and ticker.upper().strip() in self._fix.available():
            return self._fix.price_history(ticker)
        return hist


def _build_live() -> DataProvider:
    if settings.data_provider == "hybrid":
        return _WithSnapshotFallback(HybridProvider(), "SEC EDGAR + Yahoo Finance")
    if settings.data_provider == "edgar":
        return _WithSnapshotFallback(EdgarProvider(), "SEC EDGAR (filings)")
    if settings.data_provider == "free":
        return _WithSnapshotFallback(FreeProvider(), "Yahoo / yfinance (live)")
    return FixtureProvider()  # configured offline-only


_LIVE: DataProvider | None = None
_OFFLINE: DataProvider | None = None


def get_provider(mode: str | None = None) -> DataProvider:
    global _LIVE, _OFFLINE
    if _OFFLINE is None:
        _OFFLINE = FixtureProvider()
    if _LIVE is None:
        _LIVE = _build_live()

    if mode == "offline":
        return _OFFLINE
    if mode == "live":
        return _LIVE
    # default for the deployment
    return _OFFLINE if settings.data_provider == "fixture" else _LIVE
