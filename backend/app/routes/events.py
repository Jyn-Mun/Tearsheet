"""/events/{ticker} — earnings-behaviour & seasonality statistics (descriptive)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import provider_dep
from app.providers import DataProvider
from app.services.event_analytics import build_events

router = APIRouter(tags=["events"])


@router.get("/events/{ticker}")
def events(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    return build_events(provider.retrieve(ticker))
