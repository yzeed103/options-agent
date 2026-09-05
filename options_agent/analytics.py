"""Pure portfolio analytics. No I/O, no globals — trivially testable."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .models import Contract, OptionType, Side

CONTRACT_MULTIPLIER = 100


def calc_pnl(contract: Contract) -> float:
    """Unrealised profit/loss in dollars (negative for a losing position)."""
    direction = 1 if contract.side is Side.LONG else -1
    delta = contract.current_premium - contract.entry_premium
    return round(delta * contract.qty * CONTRACT_MULTIPLIER * direction, 2)


def break_even(contract: Contract) -> float:
    """Underlying price at which the position breaks even at expiry."""
    if contract.type is OptionType.CALL:
        return round(contract.strike + contract.entry_premium, 2)
    return round(contract.strike - contract.entry_premium, 2)


def cost_basis(contract: Contract) -> float:
    """Premium paid (long) or collected (short), always positive."""
    return round(contract.entry_premium * contract.qty * CONTRACT_MULTIPLIER, 2)


def contract_detail(contract: Contract) -> dict[str, Any]:
    return {
        "id": contract.id,
        "symbol": contract.symbol,
        "type": contract.type.value,
        "side": contract.side.value,
        "strike": contract.strike,
        "entry": contract.entry_premium,
        "current": contract.current_premium,
        "qty": contract.qty,
        "pnl": calc_pnl(contract),
        "break_even": break_even(contract),
        "cost": cost_basis(contract),
        "expiry": contract.expiry.isoformat(),
        "expired": contract.is_expired,
    }


def analyze_portfolio(contracts: Sequence[Contract]) -> dict[str, Any]:
    """Aggregate portfolio statistics. Safe for an empty portfolio."""
    details = [contract_detail(c) for c in contracts]
    total = len(details)
    if total == 0:
        return {
            "empty": True,
            "total_contracts": 0,
            "total_pnl": 0.0,
            "total_cost": 0.0,
            "calls": 0,
            "puts": 0,
            "long_positions": 0,
            "short_positions": 0,
            "win_rate": 0.0,
            "contracts_detail": [],
        }

    winners = sum(1 for d in details if d["pnl"] > 0)
    return {
        "empty": False,
        "total_contracts": total,
        "total_pnl": round(sum(d["pnl"] for d in details), 2),
        "total_cost": round(sum(d["cost"] for d in details), 2),
        "calls": sum(1 for d in details if d["type"] == OptionType.CALL.value),
        "puts": sum(1 for d in details if d["type"] == OptionType.PUT.value),
        "long_positions": sum(1 for d in details if d["side"] == Side.LONG.value),
        "short_positions": sum(1 for d in details if d["side"] == Side.SHORT.value),
        "win_rate": round(winners / total * 100, 1),
        "contracts_detail": details,
    }
