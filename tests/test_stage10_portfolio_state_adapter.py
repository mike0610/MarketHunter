from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.models import AccountKind, AccountState
from risk_mm.models import RiskDecision, SizedExecutionPlan, TradingAccount
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.portfolio_state_adapter import build_portfolio_risk_state


NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def account_state(account: AccountKind, *, equity: str = "2000", available: str = "1800") -> AccountState:
    return AccountState(
        account=account,
        starting_cash=Decimal("2000"),
        cash=Decimal("1900"),
        realized_pnl=Decimal("0"),
        fees_paid=Decimal("0"),
        peak_equity=Decimal("2000"),
        last_equity=Decimal(equity),
        max_drawdown=Decimal("0"),
        used_margin=Decimal("100"),
        available_cash=Decimal(available),
    )


def plan(plan_id: str, account: TradingAccount, risk: str = "50") -> SizedExecutionPlan:
    return SizedExecutionPlan(
        plan_id,
        "decision-" + plan_id,
        RiskDecision.APPROVED,
        account,
        "policy",
        "1",
        NOW,
        ("RISK_POLICY_APPROVED",),
        Decimal("10"),
        Decimal("100"),
        Decimal("95"),
        Decimal(risk),
        Decimal("1000"),
        Decimal("1"),
    )


class PortfolioRiskStateAdapterTests(unittest.TestCase):
    def test_spot_1x_uses_durable_equity_cash_and_exposure(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = OpenRiskLedger(Path(td) / "risk.db")
            ledger.record_open(
                position_id="p1",
                plan=plan("plan1", TradingAccount.SPOT),
                symbol="ABC",
                cluster_key="TECH",
                filled_quantity=Decimal("10"),
            )
            state = build_portfolio_risk_state(
                account_state=account_state(AccountKind.SPOT),
                open_risk_ledger=ledger,
                account=TradingAccount.SPOT,
                cluster_key="TECH",
                requested_leverage=Decimal("1"),
            )
            self.assertEqual(state.equity, Decimal("2000"))
            self.assertEqual(state.available_cash, Decimal("1800"))
            self.assertEqual(state.aggregate_open_risk, Decimal("50"))
            self.assertEqual(state.cluster_open_risk, Decimal("50"))
            self.assertEqual(state.requested_leverage, Decimal("1"))

    def test_futures_leverage_is_preserved_not_invented(self):
        with tempfile.TemporaryDirectory() as td:
            state = build_portfolio_risk_state(
                account_state=account_state(AccountKind.FUTURES),
                open_risk_ledger=OpenRiskLedger(Path(td) / "risk.db"),
                account=TradingAccount.FUTURES,
                cluster_key="CRYPTO",
                requested_leverage=Decimal("3"),
            )
            self.assertEqual(state.requested_leverage, Decimal("3"))

    def test_restart_restores_aggregate_and_cluster_risk_and_close_zeroes_it(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "risk.db"
            ledger = OpenRiskLedger(db)
            ledger.record_open(
                position_id="p1",
                plan=plan("plan1", TradingAccount.SPOT, "40"),
                symbol="ABC",
                cluster_key="TECH",
                filled_quantity=Decimal("10"),
            )
            ledger.record_open(
                position_id="p2",
                plan=plan("plan2", TradingAccount.SPOT, "30"),
                symbol="XYZ",
                cluster_key="OTHER",
                filled_quantity=Decimal("10"),
            )
            restarted = OpenRiskLedger(db)
            state = build_portfolio_risk_state(
                account_state=account_state(AccountKind.SPOT),
                open_risk_ledger=restarted,
                account=TradingAccount.SPOT,
                cluster_key="TECH",
                requested_leverage=Decimal("1"),
            )
            self.assertEqual(state.aggregate_open_risk, Decimal("70"))
            self.assertEqual(state.cluster_open_risk, Decimal("40"))
            restarted.reduce("p1", Decimal("10"))
            restarted.reduce("p2", Decimal("10"))
            closed = build_portfolio_risk_state(
                account_state=account_state(AccountKind.SPOT),
                open_risk_ledger=OpenRiskLedger(db),
                account=TradingAccount.SPOT,
                cluster_key="TECH",
                requested_leverage=Decimal("1"),
            )
            self.assertEqual(closed.aggregate_open_risk, Decimal("0"))
            self.assertEqual(closed.cluster_open_risk, Decimal("0"))

    def test_missing_or_mismatched_context_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = OpenRiskLedger(Path(td) / "risk.db")
            with self.assertRaises(ValueError):
                build_portfolio_risk_state(
                    account_state=account_state(AccountKind.SPOT),
                    open_risk_ledger=ledger,
                    account=TradingAccount.SPOT,
                    cluster_key="",
                    requested_leverage=Decimal("1"),
                )
            with self.assertRaises(ValueError):
                build_portfolio_risk_state(
                    account_state=account_state(AccountKind.SPOT),
                    open_risk_ledger=ledger,
                    account=TradingAccount.FUTURES,
                    cluster_key="TECH",
                    requested_leverage=Decimal("1"),
                )
            with self.assertRaises(ValueError):
                build_portfolio_risk_state(
                    account_state=account_state(AccountKind.SPOT),
                    open_risk_ledger=ledger,
                    account=TradingAccount.SPOT,
                    cluster_key="TECH",
                    requested_leverage=Decimal("0"),
                )


if __name__ == "__main__":
    unittest.main()
