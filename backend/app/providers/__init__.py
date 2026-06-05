"""providers package — the data swap point.

`get_provider()` returns the configured DataProvider. In "free" mode it returns a wrapper that
serves live yfinance data but, if a live fetch comes back essentially empty (Yahoo rate-limit /
block) and `fixture_fallback` is on, transparently falls back to a recorded sample for that
ticker — labelled as such, never passed off as live.
"""

from __future__ import annotations

from app.config import settings
from app.models.schemas import CompanyPayload
from app.providers.base import DataProvider
from app.providers.fixture_provider import FixtureProvider
from app.providers.free_provider import FreeProvider


def _is_empty(p: CompanyPayload) -> bool:
    return (
        p.price.current is None
        and not p.financials.income
        and not p.profile.name
    )


class FreeWithFixtureFallback(DataProvider):
    name = "yfinance"

    def __init__(self) -> None:
        self._free = FreeProvider()
        self._fix = FixtureProvider()

    def retrieve(self, ticker: str) -> CompanyPayload:
        payload = self._free.retrieve(ticker)
        if settings.fixture_fallback and _is_empty(payload):
            if ticker.upper().strip() in self._fix.available():
                fb = self._fix.retrieve(ticker)
                fb.warnings.insert(
                    0,
                    "Live Yahoo data was unavailable (rate-limit/block); showing recorded "
                    "SAMPLE data so the app is usable. This is not live market data.",
                )
                return fb
        return payload


_PROVIDER: DataProvider | None = None


def get_provider() -> DataProvider:
    global _PROVIDER
    if _PROVIDER is None:
        if settings.data_provider == "fixture":
            _PROVIDER = FixtureProvider()
        else:
            _PROVIDER = FreeWithFixtureFallback()
    return _PROVIDER
