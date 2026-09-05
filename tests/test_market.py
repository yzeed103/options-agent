from __future__ import annotations

import pytest

from options_agent.errors import UpstreamError, ValidationError
from options_agent.market import MarketDataService

from .conftest import FakeTicker


def test_price_is_rounded():
    service = MarketDataService(ticker_factory=lambda _s: FakeTicker(), cache_ttl=0)
    assert service.get_price("aapl") == 201.23


def test_invalid_symbol_raises_validation_error():
    service = MarketDataService(ticker_factory=lambda _s: FakeTicker(), cache_ttl=0)
    with pytest.raises(ValidationError):
        service.get_price("../etc/passwd")


def test_upstream_failure_is_wrapped():
    def boom(_symbol: str):
        raise RuntimeError("yahoo down")

    service = MarketDataService(ticker_factory=boom, cache_ttl=0)
    with pytest.raises(UpstreamError):
        service.get_summary("AAPL")


def test_symbol_without_options_raises_upstream_error():
    class NoOptions(FakeTicker):
        options = ()

    service = MarketDataService(ticker_factory=lambda _s: NoOptions(), cache_ttl=0)
    with pytest.raises(UpstreamError):
        service.get_options_chain("AAPL")


def test_cache_avoids_repeat_calls():
    calls: list[str] = []

    def factory(symbol: str):
        calls.append(symbol)
        return FakeTicker()

    service = MarketDataService(ticker_factory=factory, cache_ttl=60)
    service.get_price("AAPL")
    service.get_price("AAPL")
    assert calls == ["AAPL"]


def test_unknown_expiry_falls_back_to_first():
    service = MarketDataService(ticker_factory=lambda _s: FakeTicker(), cache_ttl=0)
    assert service.get_options_chain("AAPL", "1999-01-01")["expiry"] == "2030-01-17"
