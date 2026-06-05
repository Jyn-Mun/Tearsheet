"""The swap point.

Everything that touches the outside world lives behind `DataProvider`. The free
implementation uses yfinance; a fixture implementation serves recorded sample data offline.
Swapping the data/retrieval layer onto any other web-data API is one new class implementing
this same interface — that is the whole architectural story (README §"swap point").
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.schemas import CompanyPayload


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
