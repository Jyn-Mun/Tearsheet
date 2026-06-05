"""/dcf/{ticker} — transparent DCF with assumptions, projection, sensitivity, guardrails."""

from __future__ import annotations

from fastapi import APIRouter

from app.providers import get_provider
from app.services.dcf_service import build_dcf

router = APIRouter(tags=["dcf"])


@router.get("/dcf/{ticker}")
def dcf(ticker: str) -> dict:
    payload = get_provider().retrieve(ticker)
    return build_dcf(payload)
