from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.models import AccountKind, AccountState
from risk_mm.models import RiskDecision, RiskPolicy, TradingAccount
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.candidate_risk_pipeline import process_candidate_to_risk
from strategies.registry_foundation import StrategyUsability, StrategyVersionAssessment
from strategy_engine.models import StrategyDecisionOutcome
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import (
    LiquidityContext,
    QueueState,
    SetupFamily,
    TradingCandidate,
    VolatilityContext,
)


NOW = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
USABLE = StrategyVersionAssessment(StrategyUsability.USABLE, ())
POLICY = RiskPolicy("MH-RISK", "1", Decimal("1"), Decimal("3"), Decimal("2"))


def candidate(
    *,
    family: SetupFamily = SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,
    stop: str | None = "close back below the breakout level (490)",
) -> TradingCandidate:
    return TradingCandidate(
        1,
        "SPY",
        "STK",
        "SMART",
        "USD",
        family,
        ("setup confirmed",),
        LiquidityContext(Decimal("1000000"), Decimal("500000000"), Decimal("500")),
        VolatilityContext(Decimal("1.2")),
        "OK",
        True,
        NOW,
        "cycle-1",
        f"1:{family.value}:cycle-1",
        QueueState.CANDIDATE,
        invalidation_reference=stop,
    )


def account_state(kind: AccountKind) -> AccountState:
    return AccountState(
        account=kind,
        starting_cash=Decimal("2000"),
        cash=Decimal("2000"),
        realized_pnl=Decimal("0"),
        fees_paid=Decimal("0"),
        peak_equity=Decimal("2000"),
        last_equity=Decimal("2000"),
        max_drawdown=Decimal("0"),
        used_margin=Decimal("0"),
        available_cash=Decimal("2000"),
    )


class CandidateStrategyRiskWiringTests(unittest.TestCase):
    def test_directional_candidate_reaches_existing_risk_engine_and_stores_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = process_candidate_to_risk(
                candidate=candidate(),
                strategy_assessment=USABLE,
                strategy_store=StrategyDecisionStore(root / "strategy.db"),
                risk_store=RiskPlanStore(root / "riskplans.db"),
                account_state=account_state(AccountKind.SPOT),
                open_risk_ledger=OpenRiskLedger(root / "openrisk.db"),
                account=TradingAccount.SPOT,
                cluster_key="US_MEGA_TECH",
                requested_leverage=Decimal("1"),
                risk_policy=POLICY,
            )
            self.assertEqual(result.strategy_decision.outcome, StrategyDecisionOutcome.LONG)
            self.assertIsNotNone(result.risk_plan)
            self.assertEqual(result.risk_plan.decision, RiskDecision.APPROVED)

    def test_missing_structural_stop_is_rejected_not_fabricated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = process_candidate_to_risk(
                candidate=candidate(stop=None),
                strategy_assessment=USABLE,
                strategy_store=StrategyDecisionStore(root / "strategy.db"),
                risk_store=RiskPlanStore(root / "riskplans.db"),
                account_state=account_state(AccountKind.SPOT),
                open_risk_ledger=OpenRiskLedger(root / "openrisk.db"),
                account=TradingAccount.SPOT,
                cluster_key="US_MEGA_TECH",
                requested_leverage=Decimal("1"),
                risk_policy=POLICY,
            )
            self.assertEqual(result.risk_plan.decision, RiskDecision.REJECTED)
            self.assertIn("INVALID_OR_MISSING_STOP", result.risk_plan.reasons)

    def test_no_trade_never_reaches_risk_mm(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            risk_store = RiskPlanStore(root / "riskplans.db")
            result = process_candidate_to_risk(
                candidate=candidate(family=SetupFamily.ABNORMAL_VOLUME_CATALYST, stop=None),
                strategy_assessment=USABLE,
                strategy_store=StrategyDecisionStore(root / "strategy.db"),
                risk_store=risk_store,
                account_state=account_state(AccountKind.SPOT),
                open_risk_ledger=OpenRiskLedger(root / "openrisk.db"),
                account=TradingAccount.SPOT,
                cluster_key="US_MEGA_TECH",
                requested_leverage=Decimal("1"),
                risk_policy=POLICY,
            )
            self.assertEqual(result.strategy_decision.outcome, StrategyDecisionOutcome.NO_TRADE)
            self.assertIsNone(result.risk_plan)

    def test_context_is_explicit_and_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(ValueError):
                process_candidate_to_risk(
                    candidate=candidate(),
                    strategy_assessment=USABLE,
                    strategy_store=StrategyDecisionStore(root / "strategy.db"),
                    risk_store=RiskPlanStore(root / "riskplans.db"),
                    account_state=account_state(AccountKind.SPOT),
                    open_risk_ledger=OpenRiskLedger(root / "openrisk.db"),
                    account=TradingAccount.FUTURES,
                    cluster_key="US_MEGA_TECH",
                    requested_leverage=Decimal("1"),
                    risk_policy=POLICY,
                )


if __name__ == "__main__":
    unittest.main()
