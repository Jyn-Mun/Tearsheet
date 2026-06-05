"""/news/{ticker} and /analysis/{ticker}."""

from __future__ import annotations

from fastapi import APIRouter

from app.providers import get_provider
from app.services.analysis_service import build_analysis
from app.services.news_service import build_news

router = APIRouter(tags=["analysis"])


@router.get("/news/{ticker}")
def news(ticker: str) -> dict:
    payload = get_provider().retrieve(ticker)
    return build_news(payload)


@router.get("/analysis/{ticker}")
def analysis(ticker: str) -> dict:
    payload = get_provider().retrieve(ticker)
    return build_analysis(payload)
