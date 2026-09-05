from __future__ import annotations
import tempfile,unittest
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from risk_mm.models import RiskDecision,SizedExecutionPlan,TradingAccount
from risk_mm.open_risk_ledger import OpenRiskLedger

NOW=datetime(2026,9,5,tzinfo=timezone.utc)
def plan():
 return SizedExecutionPlan("p1","d1",RiskDecision.APPROVED,TradingAccount.SPOT,"pol","1",NOW,(),Decimal("10"),Decimal("100"),Decimal("95"),Decimal("50"),Decimal("1000"),Decimal("1"))

class OpenRiskLedgerTests(unittest.TestCase):
 def test_fill_partial_exit_restart_and_close_are_durable(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"risk.db";l=OpenRiskLedger(db)
   l.record_open(position_id="pos1",plan=plan(),symbol="ABC",cluster_key="TECH",filled_quantity=Decimal("10"))
   self.assertEqual(l.aggregate(TradingAccount.SPOT,"TECH"),(Decimal("50"),Decimal("50")))
   l.reduce("pos1",Decimal("4"))
   self.assertEqual(OpenRiskLedger(db).aggregate(TradingAccount.SPOT,"TECH"),(Decimal("30"),Decimal("30")))
   OpenRiskLedger(db).reduce("pos1",Decimal("6"))
   self.assertEqual(OpenRiskLedger(db).aggregate(TradingAccount.SPOT,"TECH"),(Decimal("0"),Decimal("0")))

 def test_duplicate_same_plan_is_idempotent_and_conflict_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   l=OpenRiskLedger(Path(td)/"risk.db");p=plan()
   l.record_open(position_id="pos1",plan=p,symbol="ABC",cluster_key="TECH",filled_quantity=Decimal("10"))
   l.record_open(position_id="pos1",plan=p,symbol="ABC",cluster_key="TECH",filled_quantity=Decimal("10"))
   with self.assertRaises(ValueError):
    l.record_open(position_id="other",plan=p,symbol="ABC",cluster_key="TECH",filled_quantity=Decimal("10"))

if __name__=="__main__":unittest.main()
