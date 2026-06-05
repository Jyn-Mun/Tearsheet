"""The swap point.

Everything that touches the outside world lives behind `DataProvider`. The free
implementation uses yfinance; a fixture implementation serves recorded sample data offline.
Swapping the data/retrieval layer onto any other web-data API is one new class implementing
this same interface — that is the whole architectural story (README §"swap point").
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.schemas import CompanyPayload, PricePoint


class DataProvider(ABC):
    """A source of normalized company data. One method to implement."""

    name: str = "base"

    @abstractmethod
    def retrieve(self, ticker: str) -> CompanyPayload:
        """Return a normalized CompanyPayload for `ticker`.

        Implementations MUST degrade gracefully: missing fields become None (rendered "n/a"),
        never an exception and never an invented value. Append human-readable notes to
        `payload.warnings` when a section could not be fetched.
        """
        raise NotImplementedError

    # --- optional lightweight fetches (override for metered APIs to save calls) ---

    def peer_snapshot(self, ticker: str) -> dict:
        """Just the fields the peer table needs. Default derives from a full retrieve(); metered
        providers override this to fetch only quote + multiples (far fewer calls)."""
        p = self.retrieve(ticker)
        return {
            "ticker": ticker.upper(),
            "name": p.profile.name,
            "market_cap": p.price.market_cap,
            "pe_ttm": p.key_metrics.pe_ttm,
            "ev_ebitda": p.key_metrics.ev_ebitda,
            "ps": p.key_metrics.ps,
            "pb": p.key_metrics.pb,
        }

    def price_history(self, ticker: str) -> list[PricePoint]:
        """Just the daily close history (for move attribution's index/sector ETFs). Default derives
        from a full retrieve(); metered providers override this to fetch only the price series."""
        return self.retrieve(ticker).price.history
