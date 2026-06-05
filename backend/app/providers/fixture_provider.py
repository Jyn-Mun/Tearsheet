"""FixtureProvider — serves recorded SYNTHETIC sample payloads from disk, no network.

Same DataProvider interface as FreeProvider, so the rest of the app is identical regardless
of source. Used for offline dev, deterministic tests, and the eval harness. Every payload is
labelled `source: "fixture (recorded sample)"` so it is never mistaken for live data.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import CompanyPayload, CompanyProfile, PriceData
from app.providers.base import DataProvider

_FIX_DIR = Path(__file__).resolve().parent / "fixtures"


class FixtureProvider(DataProvider):
    name = "fixture (recorded sample)"

    def available(self) -> list[str]:
        return sorted(p.stem for p in _FIX_DIR.glob("*.json"))

    def retrieve(self, ticker: str) -> CompanyPayload:
        ticker = ticker.upper().strip()
        path = _FIX_DIR / f"{ticker}.json"
        if not path.exists():
            return CompanyPayload(
                ticker=ticker,
                as_of="",
                source=self.name,
                profile=CompanyProfile(),
                price=PriceData(),
                warnings=[
                    f"No fixture for {ticker}. Available sample tickers: {', '.join(self.available())}."
                ],
            )
        return CompanyPayload.model_validate(json.loads(path.read_text()))
