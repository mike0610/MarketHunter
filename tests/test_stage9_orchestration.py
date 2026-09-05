from __future__ import annotations
import tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from stage9.control import NotDue,OrchestrationRegistry,OverlapBlocked
from stage9.models import PipelineHealth,PipelineSpec
from stage9.policy import DEFAULT_PIPELINES
from stage9.store import OrchestrationStore

T0=datetime(2026,9,5,12,tzinfo=timezone.utc)

class Stage9ControlPlaneTests(unittest.TestCase):
 def spec(self,pid="a",minutes=10,max_minutes=80):
  return PipelineSpec(pid,timedelta(minutes=minutes),timedelta(minutes=max_minutes))

 def test_restart_recovery_preserves_durable_state(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"o.db";s=OrchestrationStore(db);r=OrchestrationRegistry(s,[self.spec()]);r.register_all(T0)
   r.begin("a","run-1",T0);r.succeed("a","run-1",T0+timedelta(minutes=1))
   s2=OrchestrationStore(db);state=s2.state("a")
   self.assertEqual(state.health,PipelineHealth.HEALTHY)
   self.assertEqual(state.last_success_at,T0+timedelta(minutes=1))
   self.assertEqual(state.next_eligible_at,T0+timedelta(minutes=11))

 def test_overlap_is_blocked_without_mutating_owner(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"o.db";s=OrchestrationStore(db);r=OrchestrationRegistry(s,[self.spec()]);r.register_all(T0)
   r.begin("a","run-1",T0)
   with self.assertRaises(OverlapBlocked):r.begin("a","run-2",T0)
   self.assertEqual(s.state("a").active_run_id,"run-1")

 def test_not_due_is_fail_closed(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"o.db";s=OrchestrationStore(db);r=OrchestrationRegistry(s,[self.spec()]);r.register_all(T0)
   r.begin("a","r1",T0);r.succeed("a","r1",T0)
   with self.assertRaises(NotDue):r.begin("a","r2",T0+timedelta(minutes=5))

 def test_backoff_doubles_and_caps(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"o.db";s=OrchestrationStore(db);r=OrchestrationRegistry(s,[self.spec(minutes=10,max_minutes=40)]);r.register_all(T0)
   now=T0
   expected=[10,20,40,40]
   for i,mins in enumerate(expected,1):
    rid=f"r{i}";r.begin("a",rid,now);r.fail("a",rid,now,"boom")
    st=s.state("a");self.assertEqual(st.consecutive_failures,i);self.assertEqual(st.next_eligible_at,now+timedelta(minutes=mins))
    now=st.next_eligible_at

 def test_failure_isolation_between_pipelines(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"o.db";s=OrchestrationStore(db);r=OrchestrationRegistry(s,[self.spec("a"),self.spec("b")]);r.register_all(T0)
   r.begin("a","ra",T0);r.fail("a","ra",T0,"source down")
   r.begin("b","rb",T0);r.succeed("b","rb",T0)
   self.assertEqual(s.state("a").health,PipelineHealth.FAILED)
   self.assertEqual(s.state("b").health,PipelineHealth.HEALTHY)
   self.assertEqual(s.state("b").consecutive_failures,0)

 def test_run_ownership_prevents_wrong_completion(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"o.db";s=OrchestrationStore(db);r=OrchestrationRegistry(s,[self.spec()]);r.register_all(T0)
   r.begin("a","owner",T0)
   with self.assertRaises(OverlapBlocked):r.succeed("a","other",T0)
   self.assertEqual(s.state("a").active_run_id,"owner")

 def test_default_cadences_match_stage9_boundary(self):
  specs={s.pipeline_id:s for s in DEFAULT_PIPELINES}
  self.assertEqual(specs["trading_scanner"].cadence,timedelta(minutes=30))
  self.assertLess(specs["execution_position_monitor"].cadence,specs["trading_scanner"].cadence)
  self.assertGreater(specs["investment_discovery"].cadence,specs["trading_scanner"].cadence)

if __name__=="__main__":unittest.main()
