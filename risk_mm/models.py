from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class RiskDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TradingAccount(str, Enum):
    SPOT = "SPOT"
    FUTURES = "FUTURES"


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    policy_id: str
    version: str
    risk_per_trade_pct: Decimal
    max_aggregate_risk_pct: Decimal
    max_cluster_risk_pct: Decimal
    futures_max_leverage: Decimal = Decimal("3")
    max_decision_age_seconds: int = 3600


@dataclass(frozen=True, slots=True)
class PortfolioRiskState:
    account: TradingAccount
    equity: Decimal
    available_cash: Decimal
    aggregate_open_risk: Decimal
    cluster_open_risk: Decimal
    cluster_key: str
    requested_leverage: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class RiskInput:
    trading_decision_id: str
    symbol: str
    direction: str
    decided_at: datetime
    evidence_status: str
    reference_price: Decimal
    stop_price: Decimal | None
    cluster_key: str


@dataclass(frozen=True, slots=True)
class SizedExecutionPlan:
    plan_id: str
    trading_decision_id: str
    decision: RiskDecision
    account: TradingAccount
    policy_id: str
    policy_version: str
    evaluated_at: datetime
    reasons: tuple[str, ...]
    quantity: Decimal | None = None
    reference_price: Decimal | None = None
    stop_price: Decimal | None = None
    risk_amount: Decimal | None = None
    notional: Decimal | None = None
    leverage: Decimal | None = None
