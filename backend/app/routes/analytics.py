"""/analytics/{ticker} — the deterministic analytics layer (scores, risk, peers, rules). No LLM."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.analytics.service import build_analytics
from app.deps import provider_dep
from app.providers import DataProvider

router = APIRouter(tags=["analytics"])


@router.get("/analytics/{ticker}")
def analytics(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    return build_analytics(provider.retrieve(ticker), provider)
