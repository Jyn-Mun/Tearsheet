"""Request dependencies. `provider_dep` reads the ?mode=live|offline toggle and returns the
matching DataProvider, so every endpoint supports the Live/Offline switch uniformly."""

from __future__ import annotations

from typing import Literal

from fastapi import Query

from app.providers import DataProvider, get_provider


def provider_dep(
    mode: Literal["live", "offline"] = Query("live", description="Data source: live API or offline snapshots"),
) -> DataProvider:
    return get_provider(mode)
