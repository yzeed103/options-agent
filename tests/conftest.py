from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest

from options_agent import create_app
from options_agent.ai import ClaudeAdvisor
from options_agent.config import Settings
from options_agent.market import MarketDataService
from options_agent.models import Contract, OptionType, Side
from options_agent.repository import ContractRepository
from options_agent.services import Services


def make_contract(**overrides: Any) -> Contract:
    defaults: dict[str, Any] = dict(
        symbol="AAPL",
        type=OptionType.CALL,
        side=Side.LONG,
        strike=200.0,
        entry_premium=5.0,
        current_premium=7.5,
        qty=2,
        expiry=date(2030, 1, 17),
        added_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Contract(**defaults)


class FakeChain:
    def __init__(self, calls: Any, puts: Any) -> None:
        self.calls = calls
        self.puts = puts


class FakeFrame:
    """Minimal stand-in for the pandas frames yfinance returns."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __getitem__(self, columns: list[str]) -> "FakeFrame":
        return FakeFrame([{c: row.get(c) for c in columns} for row in self._records])

    def head(self, n: int) -> "FakeFrame":
        return FakeFrame(self._records[:n])

    def to_dict(self, _orient: str) -> list[dict[str, Any]]:
        return list(self._records)


class FakeTicker:
    options = ("2030-01-17", "2030-02-21")

    class _FastInfo:
        last_price = 201.234

    fast_info = _FastInfo()
    info = {"currentPrice": 201.23, "fiftyTwoWeekHigh": 260.0, "sector": "Technology"}

    def history(self, period: str = "5d") -> dict[str, Any]:
        class _Series(list):
            @property
            def iloc(self):
                return self

        closes = _Series([100.0, 110.0])
        return {"Close": closes}

    def option_chain(self, expiry: str) -> FakeChain:
        row = {
            "strike": 200.0,
            "lastPrice": 5.5,
            "bid": 5.4,
            "ask": 5.6,
            "volume": 10,
            "openInterest": 20,
            "impliedVolatility": 0.31,
        }
        return FakeChain(FakeFrame([row]), FakeFrame([row]))


class FakeMessage:
    class _Block:
        text = "تحليل تجريبي"

    content = [_Block()]


class FakeAnthropicClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.calls: list[dict[str, Any]] = []

        class _Messages:
            def __init__(self, outer: "FakeAnthropicClient") -> None:
                self._outer = outer

            def create(self, **kwargs: Any) -> FakeMessage:
                self._outer.calls.append(kwargs)
                return FakeMessage()

        self.messages = _Messages(self)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_path=tmp_path / "test.db",
        legacy_data_file=tmp_path / "legacy.json",
        anthropic_api_key="sk-test",
        anthropic_model="claude-opus-5",
        anthropic_max_tokens=256,
        market_cache_ttl=0,
    )


@pytest.fixture
def repository(settings: Settings) -> ContractRepository:
    repo = ContractRepository(settings.database_path)
    repo.initialize()
    return repo


@pytest.fixture
def created_clients() -> list[FakeAnthropicClient]:
    return []


@pytest.fixture
def app(settings: Settings, repository: ContractRepository, created_clients):
    def client_factory(api_key: str) -> FakeAnthropicClient:
        client = FakeAnthropicClient(api_key)
        created_clients.append(client)
        return client

    services = Services(
        settings=settings,
        contracts=repository,
        market=MarketDataService(ticker_factory=lambda _s: FakeTicker(), cache_ttl=0),
        advisor=ClaudeAdvisor(settings, client_factory=client_factory),
    )
    application = create_app(settings, services=services)
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    return app.test_client()
