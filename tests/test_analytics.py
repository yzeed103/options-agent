from __future__ import annotations

from options_agent.analytics import analyze_portfolio, break_even, calc_pnl, cost_basis
from options_agent.models import OptionType, Side

from .conftest import make_contract


def test_long_call_profit():
    contract = make_contract(entry_premium=5.0, current_premium=7.5, qty=2)
    assert calc_pnl(contract) == 500.0


def test_long_position_loss_is_negative():
    contract = make_contract(entry_premium=7.5, current_premium=5.0, qty=1)
    assert calc_pnl(contract) == -250.0


def test_short_position_inverts_direction():
    contract = make_contract(side=Side.SHORT, entry_premium=5.0, current_premium=3.0, qty=1)
    assert calc_pnl(contract) == 200.0


def test_break_even_call_and_put():
    assert break_even(make_contract(type=OptionType.CALL, strike=200, entry_premium=5)) == 205.0
    assert break_even(make_contract(type=OptionType.PUT, strike=200, entry_premium=5)) == 195.0


def test_cost_basis():
    assert cost_basis(make_contract(entry_premium=5.0, qty=3)) == 1500.0


def test_empty_portfolio_is_not_an_error():
    result = analyze_portfolio([])
    assert result["empty"] is True
    assert result["total_pnl"] == 0.0
    assert result["win_rate"] == 0.0
    assert result["contracts_detail"] == []


def test_portfolio_aggregates():
    contracts = [
        make_contract(symbol="AAPL", entry_premium=5.0, current_premium=7.0, qty=1),
        make_contract(
            symbol="TSLA",
            type=OptionType.PUT,
            side=Side.SHORT,
            entry_premium=4.0,
            current_premium=6.0,
            qty=1,
        ),
    ]
    result = analyze_portfolio(contracts)
    assert result["empty"] is False
    assert result["total_contracts"] == 2
    assert result["calls"] == 1 and result["puts"] == 1
    assert result["long_positions"] == 1 and result["short_positions"] == 1
    assert result["total_pnl"] == 0.0
    assert result["total_cost"] == 900.0
    assert result["win_rate"] == 50.0
