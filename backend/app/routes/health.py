"""Liveness endpoint — the frontend pings this on load to confirm the backend is reachable."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.providers import get_provider

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    """Return basic liveness + which optional integrations are configured.

    No secrets are returned — only booleans indicating whether a key is present, so the
    frontend can show what's available without exposing anything.
    """
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "integrations": {
            "anthropic": settings.anthropic_api_key is not None
            and settings.anthropic_api_key != "",
            "fred": settings.fred_api_key is not None and settings.fred_api_key != "",
        },
        "data_source": get_provider().name,
    }
