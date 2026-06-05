"""/company/{ticker} — profile + price + key metrics (the Overview tab)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import provider_dep
from app.providers import DataProvider

router = APIRouter(tags=["company"])


@router.get("/company/{ticker}")
def company(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    payload = provider.retrieve(ticker)
    return {
        "ticker": payload.ticker,
        "as_of": payload.as_of,
        "source": payload.source,
        "profile": payload.profile.model_dump(),
        "price": payload.price.model_dump(exclude={"history"}),
        "sparkline": [p.close for p in payload.price.history[-90:]],
        "key_metrics": payload.key_metrics.model_dump(),
        "provenance": {k: v.model_dump() for k, v in payload.provenance.items()},
        "warnings": payload.warnings,
    }
