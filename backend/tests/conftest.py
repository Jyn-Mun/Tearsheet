"""Shared fixtures: a FixtureProvider over the engineered test fixtures, no network needed."""

from pathlib import Path

import pytest

from app.providers.fixture_provider import FixtureProvider

TEST_FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def provider() -> FixtureProvider:
    return FixtureProvider(TEST_FIXTURES)


@pytest.fixture(scope="session")
def nvda(provider):
    return provider.retrieve("NVDA")
