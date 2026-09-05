"""Domain model for an options contract, with strict payload validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .errors import ValidationError

SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
MAX_QTY = 10_000
MAX_PRICE = 1_000_000.0


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


def normalize_symbol(raw: Any, field: str = "symbol") -> str:
    """Uppercase and validate a ticker symbol."""
    if not isinstance(raw, str):
        raise ValidationError(f"الحقل '{field}' يجب أن يكون نصاً")
    symbol = raw.strip().upper()
    if not SYMBOL_RE.match(symbol):
        raise ValidationError(f"رمز غير صالح: '{raw}'")
    return symbol


def _price(payload: Mapping[str, Any], field: str, *, default: float | None = None) -> float:
    raw = payload.get(field, None)
    if raw is None:
        if default is not None:
            return default
        raise ValidationError(f"الحقل '{field}' مطلوب")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ValidationError(f"الحقل '{field}' يجب أن يكون رقماً")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValidationError(f"الحقل '{field}' يجب أن يكون رقماً") from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise ValidationError(f"الحقل '{field}' يجب أن يكون رقماً")
    if value <= 0:
        raise ValidationError(f"الحقل '{field}' يجب أن يكون أكبر من صفر")
    if value > MAX_PRICE:
        raise ValidationError(f"الحقل '{field}' يتجاوز الحد المسموح")
    return round(value, 4)


def _qty(payload: Mapping[str, Any]) -> int:
    raw = payload.get("qty", 1)
    if raw is None:
        return 1
    if isinstance(raw, bool):
        raise ValidationError("الحقل 'qty' يجب أن يكون عدداً صحيحاً")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("الحقل 'qty' يجب أن يكون عدداً صحيحاً") from exc
    if not 1 <= value <= MAX_QTY:
        raise ValidationError(f"الحقل 'qty' يجب أن يكون بين 1 و {MAX_QTY}")
    return value


def _enum(payload: Mapping[str, Any], field: str, enum_cls: type[Enum]) -> Any:
    raw = payload.get(field)
    if not isinstance(raw, str):
        raise ValidationError(f"الحقل '{field}' مطلوب")
    try:
        return enum_cls(raw.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ValidationError(f"الحقل '{field}' يجب أن يكون أحد: {allowed}") from exc


def _expiry(payload: Mapping[str, Any]) -> date:
    raw = payload.get("expiry")
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationError("الحقل 'expiry' مطلوب بصيغة YYYY-MM-DD")
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValidationError("صيغة 'expiry' يجب أن تكون YYYY-MM-DD") from exc


@dataclass(frozen=True)
class Contract:
    """A single options position."""

    symbol: str
    type: OptionType
    side: Side
    strike: float
    entry_premium: float
    current_premium: float
    qty: int
    expiry: date
    added_at: datetime
    id: int | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "Contract":
        """Build a contract from untrusted JSON. Raises ValidationError."""
        if not isinstance(payload, Mapping):
            raise ValidationError("الطلب يجب أن يكون كائن JSON")
        entry = _price(payload, "entry_premium")
        return cls(
            symbol=normalize_symbol(payload.get("symbol")),
            type=_enum(payload, "type", OptionType),
            side=_enum(payload, "side", Side),
            strike=_price(payload, "strike"),
            entry_premium=entry,
            current_premium=_price(payload, "current_premium", default=entry),
            qty=_qty(payload),
            expiry=_expiry(payload),
            added_at=datetime.now(timezone.utc),
        )

    def with_id(self, contract_id: int) -> "Contract":
        return replace(self, id=contract_id)

    @property
    def is_expired(self) -> bool:
        return self.expiry < datetime.now(timezone.utc).date()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "type": self.type.value,
            "side": self.side.value,
            "strike": self.strike,
            "entry_premium": self.entry_premium,
            "current_premium": self.current_premium,
            "qty": self.qty,
            "expiry": self.expiry.isoformat(),
            "added_at": self.added_at.isoformat(),
        }
