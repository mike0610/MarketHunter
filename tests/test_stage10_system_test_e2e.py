from __future__ import annotations
import tempfile,unittest
from decimal import Decimal
from pathlib import Path

from risk_mm.models import TradingAccount
from stage10.system_test_e2e import run

class Stage10SystemE2ETests(unittest.TestCase):
 def _assert_pass(self,result,expected_leverage):
  self.assertEqual(result["status"],"PASS")
  self.assertEqual(result["risk_decision"],"APPROVED")
  self.assertEqual(Decimal(result["leverage"]),Decimal(expected_leverage))
  self.assertGreater(Decimal(result["risk_amount"]),0)
  self.assertGreater(Decimal(result["quantity"]),0)
  self.assertEqual(result["counts"]["stage5_sim_orders"],1)
  self.assertEqual(result["counts"]["stage5_sim_fills"],1)
  self.assertEqual(result["counts"]["stage5_sim_positions"],1)
  self.assertEqual(result["counts"]["stage6_closed_trades"],1)
  self.assertEqual(result["counts"]["stage10_test_only_provenance"],1)
  self.assertTrue(result["test_only_excluded_from_reports"])

 def test_spot_1x_runs_real_risk_conditional_fill_restart_exit_and_report_isolation(self):
  with tempfile.TemporaryDirectory() as td:
   self._assert_pass(run(Path(td)/"spot.db",TradingAccount.SPOT),"1")

 def test_futures_3x_runs_real_risk_conditional_fill_restart_exit_and_report_isolation(self):
  with tempfile.TemporaryDirectory() as td:
   self._assert_pass(run(Path(td)/"futures.db",TradingAccount.FUTURES),"3")

if __name__=="__main__":unittest.main()
