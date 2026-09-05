from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from stage10.system_test_e2e import run

class Stage10SystemE2ETests(unittest.TestCase):
 def test_conditional_fill_restart_exit_closed_trade_and_report_isolation(self):
  with tempfile.TemporaryDirectory() as td:
   result=run(Path(td)/"proof.db")
   self.assertEqual(result["status"],"PASS")
   self.assertEqual(result["counts"]["stage5_sim_orders"],1)
   self.assertEqual(result["counts"]["stage5_sim_fills"],1)
   self.assertEqual(result["counts"]["stage5_sim_positions"],1)
   self.assertEqual(result["counts"]["stage6_closed_trades"],1)
   self.assertEqual(result["counts"]["stage10_test_only_provenance"],1)
   self.assertTrue(result["test_only_excluded_from_reports"])

if __name__=="__main__":unittest.main()
