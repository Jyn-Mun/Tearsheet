"""/dcf/{ticker} — transparent DCF with assumptions, projection, sensitivity, guardrails."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import provider_dep
from app.providers import DataProvider
from app.services.dcf_service import build_dcf

router = APIRouter(tags=["dcf"])


@router.get("/dcf/{ticker}")
def dcf(ticker: str, provider: DataProvider = Depends(provider_dep)) -> dict:
    return build_dcf(provider.retrieve(ticker))
