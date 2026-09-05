from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from experiment1.models import AccountState
from risk_mm.engine import evaluate_risk
from risk_mm.models import RiskInput, RiskPolicy, SizedExecutionPlan, TradingAccount
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.portfolio_state_adapter import build_portfolio_risk_state
from risk_mm.store import RiskPlanStore
from strategies.registry_foundation import StrategyVersionAssessment
from strategy_engine.engine import validate_candidate
from strategy_engine.models import StrategyDecisionOutcome, StrategyDecisionRecord
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import TradingCandidate


@dataclass(frozen=True, slots=True)
class CandidateRiskResult:
    strategy_decision: StrategyDecisionRecord
    risk_plan: SizedExecutionPlan | None


def process_candidate_to_risk(
    *,
    candidate: TradingCandidate,
    strategy_assessment: StrategyVersionAssessment,
    strategy_store: StrategyDecisionStore,
    risk_store: RiskPlanStore,
    account_state: AccountState,
    open_risk_ledger: OpenRiskLedger,
    account: TradingAccount,
    cluster_key: str,
    requested_leverage: Decimal,
    risk_policy: RiskPolicy,
) -> CandidateRiskResult:
    """Stage 10 integration only: Candidate -> Strategy -> Risk/MM.

    All business context remains caller-supplied. This function does not
    choose account, cluster, leverage, policy, stop, direction or sizing.
    Non-directional strategy outcomes never reach Risk/MM.
    """
    decision = strategy_store.record(
        validate_candidate(
            candidate,
            strategy_assessment=strategy_assessment,
        )
    )

    if decision.outcome not in (
        StrategyDecisionOutcome.LONG,
        StrategyDecisionOutcome.SHORT,
    ):
        return CandidateRiskResult(decision, None)

    if decision.reference_price is None:
        raise ValueError("directional strategy decision requires reference_price")

    risk_input = RiskInput(
        trading_decision_id=decision.decision_id,
        symbol=decision.symbol,
        direction=decision.outcome.value,
        decided_at=decision.decided_at,
        evidence_status=decision.candidate_evidence_status,
        reference_price=decision.reference_price,
        stop_price=decision.structural_stop_price,
        cluster_key=cluster_key,
    )
    portfolio_state = build_portfolio_risk_state(
        account_state=account_state,
        open_risk_ledger=open_risk_ledger,
        account=account,
        cluster_key=cluster_key,
        requested_leverage=requested_leverage,
    )
    plan = risk_store.record(
        evaluate_risk(
            risk_input,
            portfolio_state,
            risk_policy,
            evaluated_at=decision.decided_at,
        )
    )
    return CandidateRiskResult(decision, plan)
