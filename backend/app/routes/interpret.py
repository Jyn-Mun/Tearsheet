"""/interpret/{ticker} and /explain-move/{ticker}."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import provider_dep
from app.providers import DataProvider
from app.services.interpretation_service import build_interpretation
from app.services.move_service import build_move

router = APIRouter(tags=["interpretation"])


@router.get("/interpret/{ticker}")
def interpret(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    return build_interpretation(provider.retrieve(ticker), provider)


@router.get("/explain-move/{ticker}")
def explain_move(
    ticker: str, date: str | None = None, provider: DataProvider = Depends(provider_dep)
) -> dict:
    return build_move(provider.retrieve(ticker), provider, target_date=date)
