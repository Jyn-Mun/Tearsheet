"""/news/{ticker} and /analysis/{ticker}."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import provider_dep
from app.providers import DataProvider
from app.services.analysis_service import build_analysis
from app.services.news_service import build_news

router = APIRouter(tags=["analysis"])


@router.get("/news/{ticker}")
def news(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    return build_news(provider.retrieve(ticker))


@router.get("/analysis/{ticker}")
def analysis(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    return build_analysis(provider.retrieve(ticker))
