"""Shared fixtures: a FixtureProvider-backed NVDA payload, no network needed."""

import pytest

from app.providers.fixture_provider import FixtureProvider


@pytest.fixture(scope="session")
def provider() -> FixtureProvider:
    return FixtureProvider()


@pytest.fixture(scope="session")
def nvda(provider):
    return provider.retrieve("NVDA")
