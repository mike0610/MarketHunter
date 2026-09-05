from __future__ import annotations
import sqlite3, tempfile, unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from risk_mm.engine import evaluate_risk
from risk_mm.models import PortfolioRiskState, RiskDecision, RiskInput, RiskPolicy, TradingAccount
from risk_mm.store import RiskPlanStore

NOW=datetime(2026,9,5,2,30,tzinfo=timezone.utc)
POLICY=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"),Decimal("3"),3600)

def inp(**kw):
    d=dict(trading_decision_id="d1",symbol="SPY",direction="LONG",decided_at=NOW,
           evidence_status="OK",reference_price=Decimal("100"),stop_price=Decimal("98"),cluster_key="US_MEGA_TECH")
    d.update(kw); return RiskInput(**d)

def state(**kw):
    d=dict(account=TradingAccount.SPOT,equity=Decimal("2000"),available_cash=Decimal("2000"),
           aggregate_open_risk=Decimal("0"),cluster_open_risk=Decimal("0"),cluster_key="US_MEGA_TECH",
           requested_leverage=Decimal("1"))
    d.update(kw); return PortfolioRiskState(**d)

class Stage4Tests(unittest.TestCase):
    def test_approved_sized_plan_has_no_execution_surface(self):
        p=evaluate_risk(inp(),state(),POLICY,evaluated_at=NOW)
        self.assertEqual(p.decision,RiskDecision.APPROVED)
        self.assertEqual(p.risk_amount,Decimal("20"))
        self.assertEqual(p.quantity,Decimal("10.00000000"))
        for x in ("order","fill","position","broker"): self.assertFalse(hasattr(p,x))

    def test_missing_stop_veto(self):
        self.assertEqual(evaluate_risk(inp(stop_price=None),state(),POLICY,evaluated_at=NOW).decision,RiskDecision.REJECTED)

    def test_stale_veto(self):
        old=NOW-timedelta(hours=2)
        self.assertIn("STALE_DECISION",evaluate_risk(inp(decided_at=old),state(),POLICY,evaluated_at=NOW).reasons)

    def test_insufficient_cash_veto(self):
        p=evaluate_risk(inp(reference_price=Decimal("1000"),stop_price=Decimal("999")),state(available_cash=Decimal("10")),POLICY,evaluated_at=NOW)
        self.assertIn("INSUFFICIENT_CASH_OR_BUYING_POWER",p.reasons)

    def test_aggregate_risk_veto(self):
        p=evaluate_risk(inp(),state(aggregate_open_risk=Decimal("50")),POLICY,evaluated_at=NOW)
        self.assertIn("AGGREGATE_RISK_LIMIT",p.reasons)

    def test_correlation_concentration_veto(self):
        p=evaluate_risk(inp(),state(cluster_open_risk=Decimal("30")),POLICY,evaluated_at=NOW)
        self.assertIn("CORRELATION_CONCENTRATION_LIMIT",p.reasons)

    def test_futures_over_3x_veto(self):
        p=evaluate_risk(inp(),state(account=TradingAccount.FUTURES,requested_leverage=Decimal("3.01")),POLICY,evaluated_at=NOW)
        self.assertIn("FUTURES_LEVERAGE_CAP_EXCEEDED",p.reasons)

    def test_spot_must_be_1x(self):
        p=evaluate_risk(inp(),state(requested_leverage=Decimal("2")),POLICY,evaluated_at=NOW)
        self.assertIn("SPOT_LEVERAGE_MUST_BE_1X",p.reasons)

    def test_duplicate_decision_is_idempotent_and_zero_execution_tables(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"risk.db"; s=RiskPlanStore(db)
            p=evaluate_risk(inp(),state(),POLICY,evaluated_at=NOW)
            s.record(p); s.record(p)
            con=sqlite3.connect(db)
            tables={r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            count=con.execute("select count(*) from risk_sized_plans").fetchone()[0]; con.close()
            self.assertEqual(count,1); self.assertEqual(tables,{"risk_sized_plans"})

if __name__=="__main__": unittest.main()
