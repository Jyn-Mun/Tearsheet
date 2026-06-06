"""Cache-policy: the public request path must not call upstream when SERVE_FROM_CACHE_ONLY is on;
only the pre-fetch job (live_fetch) may. read_ttl bridges prefetch cycles."""

from app import cache_policy
from app.cache_policy import live_fetch, read_ttl, should_fetch_live
from app.config import settings


def test_request_path_blocks_live_in_cache_only(monkeypatch):
    monkeypatch.setattr(settings, "serve_from_cache_only", True)
    # request path (no live_fetch context) → not allowed to call upstream
    assert should_fetch_live() is False
    # the pre-fetch job opts in explicitly
    with live_fetch():
        assert should_fetch_live() is True
    assert should_fetch_live() is False


def test_normal_mode_allows_live(monkeypatch):
    monkeypatch.setattr(settings, "serve_from_cache_only", False)
    assert should_fetch_live() is True


def test_read_ttl_bridges_prefetch_cycle(monkeypatch):
    monkeypatch.setattr(settings, "serve_from_cache_only", False)
    assert read_ttl(300) == 300                              # normal: short live TTL
    monkeypatch.setattr(settings, "serve_from_cache_only", True)
    monkeypatch.setattr(settings, "prefetch_interval_hours", 6.0)
    assert read_ttl(300) == 6.0 * 3600 * 1.5                 # cache-only: stale-OK up to ~1.5 cycles


def test_provider_returns_empty_in_cache_only(monkeypatch):
    """A market provider must not hit the network on the request path in cache-only mode."""
    from app.providers.twelvedata_provider import TwelveDataProvider

    monkeypatch.setattr(settings, "serve_from_cache_only", True)
    monkeypatch.setattr(settings, "twelvedata_api_key", "dummy")
    p = TwelveDataProvider()
    # _get is gated → returns None without any HTTP call (no key would also gate it)
    assert p._get("quote", symbol="AAPL") is None
