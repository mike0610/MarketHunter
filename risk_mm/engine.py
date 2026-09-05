from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from hashlib import sha256

from risk_mm.models import (
    PortfolioRiskState, RiskDecision, RiskInput, RiskPolicy, SizedExecutionPlan, TradingAccount,
)


def evaluate_risk(
    item: RiskInput,
    state: PortfolioRiskState,
    policy: RiskPolicy,
    *,
    evaluated_at: datetime | None = None,
) -> SizedExecutionPlan:
    now = evaluated_at or datetime.now(timezone.utc)
    pid = "risk:" + sha256(f"{item.trading_decision_id}|{policy.policy_id}|{policy.version}".encode()).hexdigest()
    reasons=[]

    age=(now-item.decided_at).total_seconds()
    if age < 0 or age > policy.max_decision_age_seconds:
        reasons.append("STALE_DECISION")
    if item.evidence_status != "OK":
        reasons.append("EVIDENCE_NOT_OK")
    if item.stop_price is None or item.stop_price <= 0 or item.stop_price == item.reference_price:
        reasons.append("INVALID_OR_MISSING_STOP")
    if state.equity <= 0 or state.available_cash < 0:
        reasons.append("INVALID_ACCOUNT_STATE")
    if state.account is TradingAccount.SPOT and state.requested_leverage != Decimal("1"):
        reasons.append("SPOT_LEVERAGE_MUST_BE_1X")
    if state.account is TradingAccount.FUTURES and state.requested_leverage > policy.futures_max_leverage:
        reasons.append("FUTURES_LEVERAGE_CAP_EXCEEDED")

    risk_budget=state.equity * policy.risk_per_trade_pct / Decimal("100")
    max_aggregate=state.equity * policy.max_aggregate_risk_pct / Decimal("100")
    max_cluster=state.equity * policy.max_cluster_risk_pct / Decimal("100")
    if state.aggregate_open_risk + risk_budget > max_aggregate:
        reasons.append("AGGREGATE_RISK_LIMIT")
    if state.cluster_key == item.cluster_key and state.cluster_open_risk + risk_budget > max_cluster:
        reasons.append("CORRELATION_CONCENTRATION_LIMIT")

    if reasons:
        return SizedExecutionPlan(pid,item.trading_decision_id,RiskDecision.REJECTED,state.account,
            policy.policy_id,policy.version,now,tuple(reasons))

    stop_distance=abs(item.reference_price-item.stop_price)
    quantity=(risk_budget/stop_distance).quantize(Decimal("0.00000001"),rounding=ROUND_DOWN)
    notional=quantity*item.reference_price
    buying_power=state.available_cash * state.requested_leverage
    if quantity <= 0:
        reasons.append("ZERO_POSITION_SIZE")
    if notional > buying_power:
        reasons.append("INSUFFICIENT_CASH_OR_BUYING_POWER")
    if reasons:
        return SizedExecutionPlan(pid,item.trading_decision_id,RiskDecision.REJECTED,state.account,
            policy.policy_id,policy.version,now,tuple(reasons))

    return SizedExecutionPlan(pid,item.trading_decision_id,RiskDecision.APPROVED,state.account,
        policy.policy_id,policy.version,now,("RISK_POLICY_APPROVED",),quantity,item.reference_price,
        item.stop_price,risk_budget,notional,state.requested_leverage)
