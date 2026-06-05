"""/interpret/{ticker} and /explain-move/{ticker}."""

from __future__ import annotations

from fastapi import APIRouter

from app.providers import get_provider
from app.services.interpretation_service import build_interpretation
from app.services.move_service import build_move

router = APIRouter(tags=["interpretation"])


@router.get("/interpret/{ticker}")
def interpret(ticker: str) -> dict:
    payload = get_provider().retrieve(ticker)
    return build_interpretation(payload)


@router.get("/explain-move/{ticker}")
def explain_move(ticker: str, date: str | None = None) -> dict:
    provider = get_provider()
    payload = provider.retrieve(ticker)
    return build_move(payload, provider, target_date=date)
