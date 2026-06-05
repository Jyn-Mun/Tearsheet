"""/financials/{ticker} and /valuation/{ticker}."""

from __future__ import annotations

from fastapi import APIRouter

from app.providers import get_provider
from app.services.financials_service import build_financials
from app.services.valuation_service import build_valuation

router = APIRouter(tags=["financials"])


@router.get("/financials/{ticker}")
def financials(ticker: str) -> dict:
    payload = get_provider().retrieve(ticker)
    return build_financials(payload)


@router.get("/valuation/{ticker}")
def valuation(ticker: str) -> dict:
    provider = get_provider()
    payload = provider.retrieve(ticker)
    return build_valuation(payload, provider)
