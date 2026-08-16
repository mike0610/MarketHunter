"""
MarketHunter

portfolio/capital_snapshot.py

Pure Portfolio-side usability assessment of an upstream
AccountCapitalSnapshot. Read-only: never mutates the snapshot, never
computes or exposes a monetary amount, and never makes a monetary
decision (USABLE is not APPROVED/PROCEED).
"""

from __future__ import annotations

from enum import Enum

from models.account_capital_snapshot import (
    AccountCapitalSnapshot,
    CapitalSnapshotState,
)


class CapitalSnapshotUsability(str, Enum):
    USABLE = "USABLE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"


_PASS_THROUGH_STATES = {
    CapitalSnapshotState.UNKNOWN: CapitalSnapshotUsability.UNKNOWN,
    CapitalSnapshotState.UNAVAILABLE: CapitalSnapshotUsability.UNAVAILABLE,
    CapitalSnapshotState.STALE: CapitalSnapshotUsability.STALE,
    CapitalSnapshotState.CONFLICT: CapitalSnapshotUsability.CONFLICT,
}


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def assess_capital_snapshot(
    snapshot: AccountCapitalSnapshot,
) -> CapitalSnapshotUsability:
    """
    Assess whether an upstream capital snapshot is usable as Portfolio
    input. Any uncertainty fails closed to UNKNOWN rather than
    inferring usability.
    """

    if not isinstance(snapshot, AccountCapitalSnapshot):
        raise TypeError(
            f"snapshot must be an AccountCapitalSnapshot, got "
            f"{type(snapshot).__name__}"
        )

    if snapshot.state in _PASS_THROUGH_STATES:
        return _PASS_THROUGH_STATES[snapshot.state]

    if (
        _blank(snapshot.source_authority)
        or _blank(snapshot.source_snapshot_id)
        or _blank(snapshot.account_id)
        or _blank(snapshot.environment)
        or _blank(snapshot.currency)
        or snapshot.as_of is None
        or (
            snapshot.account_equity is None
            and snapshot.cash is None
            and snapshot.balance is None
            and snapshot.margin_balance is None
            and snapshot.buying_power is None
            and snapshot.available_capital is None
        )
    ):
        return CapitalSnapshotUsability.UNKNOWN

    return CapitalSnapshotUsability.USABLE
