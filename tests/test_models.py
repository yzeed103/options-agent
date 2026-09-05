from __future__ import annotations

from datetime import date

import pytest

from options_agent.errors import ValidationError
from options_agent.models import Contract, OptionType, Side, normalize_symbol

VALID = {
    "symbol": " aapl ",
    "type": "CALL",
    "side": "Long",
    "strike": 200,
    "entry_premium": "5.25",
    "current_premium": 7.5,
    "qty": 2,
    "expiry": "2030-01-17",
}


def test_from_payload_normalises_fields():
    contract = Contract.from_payload(VALID)
    assert contract.symbol == "AAPL"
    assert contract.type is OptionType.CALL
    assert contract.side is Side.LONG
    assert contract.strike == 200.0
    assert contract.entry_premium == 5.25
    assert contract.expiry == date(2030, 1, 17)
    assert contract.id is None


def test_current_premium_defaults_to_entry():
    payload = {**VALID}
    payload.pop("current_premium")
    assert Contract.from_payload(payload).current_premium == 5.25


def test_qty_defaults_to_one_when_null():
    contract = Contract.from_payload({**VALID, "qty": None})
    assert contract.qty == 1


@pytest.mark.parametrize(
    "override",
    [
        {"symbol": ""},
        {"symbol": "TOOLONGSYMBOL"},
        {"symbol": 12},
        {"type": "spread"},
        {"side": None},
        {"strike": 0},
        {"strike": -1},
        {"strike": "abc"},
        {"entry_premium": None},
        {"qty": 0},
        {"qty": 999_999},
        {"expiry": "17-01-2030"},
        {"expiry": ""},
    ],
)
def test_invalid_payloads_rejected(override):
    with pytest.raises(ValidationError):
        Contract.from_payload({**VALID, **override})


def test_non_mapping_payload_rejected():
    with pytest.raises(ValidationError):
        Contract.from_payload(None)


def test_expired_flag():
    assert Contract.from_payload({**VALID, "expiry": "2000-01-01"}).is_expired
    assert not Contract.from_payload(VALID).is_expired


def test_to_dict_is_json_serialisable():
    payload = Contract.from_payload(VALID).with_id(4).to_dict()
    assert payload["id"] == 4
    assert payload["expiry"] == "2030-01-17"
    assert payload["type"] == "call"


def test_normalize_symbol_rejects_injection():
    with pytest.raises(ValidationError):
        normalize_symbol("AAPL; DROP TABLE contracts")
