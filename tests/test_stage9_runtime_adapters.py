from __future__ import annotations
import tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from stage9.health import health_snapshot
from stage9.policy import DEFAULT_PIPELINES
from stage9.wiring import build_registry,run_pipeline
T=datetime(2026,9,5,15,tzinfo=timezone.utc)
class Stage9AdapterTests(unittest.TestCase):
 def test_operational_pipelines_have_independent_leases(self):
  with tempfile.TemporaryDirectory() as td:
   r=build_registry(Path(td)/"o.db",T);calls=[]
   self.assertEqual(run_pipeline(r,"execution_monitor",lambda:calls.append("exec"),T).outcome,"SUCCEEDED")
   self.assertEqual(run_pipeline(r,"position_monitor",lambda:calls.append("pos"),T).outcome,"SUCCEEDED")
   self.assertEqual(run_pipeline(r,"portfolio_mtm",lambda:calls.append("mtm"),T).outcome,"SUCCEEDED")
   self.assertEqual(calls,["exec","pos","mtm"])
 def test_execution_failure_does_not_stop_position_monitor(self):
  with tempfile.TemporaryDirectory() as td:
   r=build_registry(Path(td)/"o.db",T)
   bad=run_pipeline(r,"execution_monitor",lambda:(_ for _ in ()).throw(RuntimeError("temporary quote failure")),T)
   good=run_pipeline(r,"position_monitor",lambda:None,T)
   self.assertEqual(bad.outcome,"FAILED");self.assertEqual(good.outcome,"SUCCEEDED")
   h={p["pipeline_id"]:p for p in health_snapshot(r,T)["pipelines"]}
   self.assertEqual(h["execution_monitor"]["health"],"FAILED");self.assertEqual(h["position_monitor"]["health"],"HEALTHY")
 def test_restart_does_not_repeat_completed_cycle(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"o.db";r=build_registry(db,T);calls=[]
   run_pipeline(r,"position_monitor",lambda:calls.append(1),T)
   r2=build_registry(db,T+timedelta(minutes=1))
   self.assertEqual(run_pipeline(r2,"position_monitor",lambda:calls.append(2),T+timedelta(minutes=1)).outcome,"SKIPPED_NOT_DUE")
   self.assertEqual(calls,[1])
 def test_policy_contains_separate_operational_cadences(self):
  p={s.pipeline_id:s for s in DEFAULT_PIPELINES}
  self.assertEqual(p["trading_scanner"].cadence,timedelta(minutes=30))
  for k in ("execution_monitor","position_monitor","portfolio_mtm"):self.assertEqual(p[k].cadence,timedelta(minutes=5))
  self.assertEqual(p["investment_discovery"].cadence,timedelta(hours=6))
if __name__=="__main__":unittest.main()
