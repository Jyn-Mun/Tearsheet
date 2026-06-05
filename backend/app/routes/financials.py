"""/financials/{ticker} and /valuation/{ticker}."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import provider_dep
from app.providers import DataProvider
from app.services.financials_service import build_financials
from app.services.valuation_service import build_valuation

router = APIRouter(tags=["financials"])


@router.get("/financials/{ticker}")
def financials(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    return build_financials(provider.retrieve(ticker))


@router.get("/valuation/{ticker}")
def valuation(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    return build_valuation(provider.retrieve(ticker), provider)
