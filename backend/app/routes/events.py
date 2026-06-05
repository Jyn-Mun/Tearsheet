"""/events/{ticker} — earnings-behaviour & seasonality statistics (descriptive)."""

from __future__ import annotations

from fastapi import APIRouter

from app.providers import get_provider
from app.services.event_analytics import build_events

router = APIRouter(tags=["events"])


@router.get("/events/{ticker}")
def events(ticker: str) -> dict:
    payload = get_provider().retrieve(ticker)
    return build_events(payload)
