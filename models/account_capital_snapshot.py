"""
MarketHunter

models/account_capital_snapshot.py

Immutable upstream capital-fact contract. Represents exactly what an
external Account Capital Authority reported, with no derivation,
normalization, or monetary decision policy. Portfolio treats this as
read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class CapitalSnapshotState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"


def _require_decimal_or_none(value: Decimal | None, field_name: str) -> None:
    if value is not None and not isinstance(value, Decimal):
        raise TypeError(
            f"{field_name} must be Decimal or None, got {type(value).__name__}"
        )


@dataclass(frozen=True, slots=True)
class AccountCapitalSnapshot:
    """
    A single upstream capital-fact snapshot. Every field is required
    explicitly at construction time - there are no silent defaults.
    """

    state: CapitalSnapshotState

    source_authority: str | None
    source_snapshot_id: str | None
    source_revision: str | None

    venue: str | None
    account_id: str | None
    subaccount_id: str | None
    environment: str | None
    currency: str | None

    as_of: datetime | None

    account_equity: Decimal | None
    cash: Decimal | None
    balance: Decimal | None
    margin_balance: Decimal | None
    buying_power: Decimal | None
    available_capital: Decimal | None

    def __post_init__(self) -> None:
        if self.as_of is not None and self.as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware when provided")

        _require_decimal_or_none(self.account_equity, "account_equity")
        _require_decimal_or_none(self.cash, "cash")
        _require_decimal_or_none(self.balance, "balance")
        _require_decimal_or_none(self.margin_balance, "margin_balance")
        _require_decimal_or_none(self.buying_power, "buying_power")
        _require_decimal_or_none(self.available_capital, "available_capital")
