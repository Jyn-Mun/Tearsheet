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

# App fixtures = the deploy snapshot set (real data baked by scripts/snapshot.py).
# Tests/eval use a separate dir of engineered fixtures so snapshots can't break them.
_DEFAULT_DIR = Path(__file__).resolve().parent / "fixtures"


class FixtureProvider(DataProvider):
    name = "fixture (recorded sample)"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._dir = fixtures_dir or _DEFAULT_DIR

    def available(self) -> list[str]:
        return sorted(p.stem for p in self._dir.glob("*.json"))

    def retrieve(self, ticker: str) -> CompanyPayload:
        ticker = ticker.upper().strip()
        path = self._dir / f"{ticker}.json"
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
