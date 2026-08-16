"""
MarketHunter

models/risk_result_record.py

Immutable, versioned, append-only record of a RiskResult
calculation, owned entirely by the Risk domain. Never infers or
copies from ResearchTrade.notional, and never invents a canonical
Signal ID or StrategyVersion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from models.risk_result import RiskResult


class IdentityState(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


def _require_nonblank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _require_optional_nonblank(value: str | None, field_name: str) -> None:
    if value is not None and not value.strip():
        raise ValueError(f"{field_name} must be non-blank when provided")


def _require_float(value: float, field_name: str) -> None:
    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be float, got {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class RiskResultRecord:
    """
    Durable, versioned RiskResult record.

    One lineage is identified by risk_result_id. Within a lineage,
    revisions are strictly append-only: revision 1 has no
    predecessor, every later revision supersedes an earlier revision
    in the same lineage.
    """

    risk_result_id: str
    revision: int
    generated_at: datetime
    supersedes_revision: int | None

    source_state: IdentityState
    source_reference_kind: str | None
    source_reference: str | None

    risk_policy_state: IdentityState
    risk_policy_version: str | None

    strategy_name: str | None
    strategy_version_state: IdentityState
    strategy_version: str | None

    entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    position_size: float
    risk_amount: float
    account_size: float
    risk_percent: float

    def __post_init__(self) -> None:
        _require_nonblank(self.risk_result_id, "risk_result_id")

        if self.revision <= 0:
            raise ValueError("revision must be > 0")

        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware UTC")

        if self.generated_at.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("generated_at must be UTC")

        _require_optional_nonblank(
            self.source_reference_kind, "source_reference_kind"
        )
        _require_optional_nonblank(self.source_reference, "source_reference")
        _require_optional_nonblank(self.risk_policy_version, "risk_policy_version")
        _require_optional_nonblank(self.strategy_name, "strategy_name")
        _require_optional_nonblank(self.strategy_version, "strategy_version")

        if self.source_state is IdentityState.KNOWN:
            if self.source_reference_kind is None or self.source_reference is None:
                raise ValueError(
                    "KNOWN source_state requires source_reference_kind and "
                    "source_reference"
                )
        else:
            if (
                self.source_reference_kind is not None
                or self.source_reference is not None
            ):
                raise ValueError(
                    "UNKNOWN source_state requires source_reference_kind and "
                    "source_reference to be None"
                )

        if self.risk_policy_state is IdentityState.KNOWN:
            if self.risk_policy_version is None:
                raise ValueError(
                    "KNOWN risk_policy_state requires risk_policy_version"
                )
        else:
            if self.risk_policy_version is not None:
                raise ValueError(
                    "UNKNOWN risk_policy_state requires risk_policy_version "
                    "to be None"
                )

        if self.strategy_version_state is IdentityState.KNOWN:
            if self.strategy_version is None:
                raise ValueError(
                    "KNOWN strategy_version_state requires strategy_version"
                )
        else:
            if self.strategy_version is not None:
                raise ValueError(
                    "UNKNOWN strategy_version_state requires strategy_version "
                    "to be None"
                )

        _require_float(self.entry, "entry")
        _require_float(self.stop_loss, "stop_loss")
        _require_float(self.take_profit, "take_profit")
        _require_float(self.risk_reward, "risk_reward")
        _require_float(self.position_size, "position_size")
        _require_float(self.risk_amount, "risk_amount")
        _require_float(self.account_size, "account_size")
        _require_float(self.risk_percent, "risk_percent")

    @staticmethod
    def from_risk_result(
        risk_result: RiskResult,
        *,
        risk_result_id: str,
        revision: int,
        generated_at: datetime,
        source_state: IdentityState,
        risk_policy_state: IdentityState,
        strategy_version_state: IdentityState,
        supersedes_revision: int | None = None,
        source_reference_kind: str | None = None,
        source_reference: str | None = None,
        risk_policy_version: str | None = None,
        strategy_name: str | None = None,
        strategy_version: str | None = None,
    ) -> "RiskResultRecord":
        """
        Build a RiskResultRecord from the current RiskResult
        calculation payload. Copies the eight calculation values
        exactly, with no coercion. If the source RiskResult holds a
        non-float value for any of them, this is a stale-handoff
        signal against the base-SHA contract, not a value to coerce.
        """

        for field_name in (
            "entry",
            "stop_loss",
            "take_profit",
            "risk_reward",
            "position_size",
            "risk_amount",
            "account_size",
            "risk_percent",
        ):
            value = getattr(risk_result, field_name)
            if not isinstance(value, float):
                raise TypeError(
                    f"RiskResult.{field_name} is {type(value).__name__}, "
                    "not float; refusing to coerce"
                )

        return RiskResultRecord(
            risk_result_id=risk_result_id,
            revision=revision,
            generated_at=generated_at,
            supersedes_revision=supersedes_revision,
            source_state=source_state,
            source_reference_kind=source_reference_kind,
            source_reference=source_reference,
            risk_policy_state=risk_policy_state,
            risk_policy_version=risk_policy_version,
            strategy_name=strategy_name,
            strategy_version_state=strategy_version_state,
            strategy_version=strategy_version,
            entry=risk_result.entry,
            stop_loss=risk_result.stop_loss,
            take_profit=risk_result.take_profit,
            risk_reward=risk_result.risk_reward,
            position_size=risk_result.position_size,
            risk_amount=risk_result.risk_amount,
            account_size=risk_result.account_size,
            risk_percent=risk_result.risk_percent,
        )
