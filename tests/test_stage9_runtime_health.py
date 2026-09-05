from __future__ import annotations
import tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from stage9.control import OrchestrationRegistry
from stage9.health import health_snapshot
from stage9.models import PipelineSpec
from stage9.runner import run_controlled_cycle
from stage9.store import OrchestrationStore
T=datetime(2026,9,5,13,tzinfo=timezone.utc)
class RuntimeHealthTests(unittest.TestCase):
 def reg(self,db):
  specs=[PipelineSpec("scanner",timedelta(minutes=30),timedelta(hours=2)),PipelineSpec("investments",timedelta(hours=6),timedelta(days=1))]
  r=OrchestrationRegistry(OrchestrationStore(db),specs);r.register_all(T);return r
 def test_success_and_health(self):
  with tempfile.TemporaryDirectory() as td:
   r=self.reg(Path(td)/"x.db");called=[]
   out=run_controlled_cycle(r,"scanner","r1",T,lambda:called.append(1))
   self.assertEqual(out.outcome,"SUCCEEDED");self.assertEqual(called,[1]);self.assertEqual(health_snapshot(r,T)["overall"],"HEALTHY")
 def test_failure_is_contained_and_other_pipeline_runs(self):
  with tempfile.TemporaryDirectory() as td:
   r=self.reg(Path(td)/"x.db")
   out=run_controlled_cycle(r,"scanner","r1",T,lambda:(_ for _ in ()).throw(RuntimeError("feed down")))
   self.assertEqual(out.outcome,"FAILED")
   other=run_controlled_cycle(r,"investments","i1",T,lambda:None)
   self.assertEqual(other.outcome,"SUCCEEDED")
   h=health_snapshot(r,T);self.assertEqual(h["overall"],"DEGRADED")
   self.assertEqual({p["pipeline_id"]:p["health"] for p in h["pipelines"]},{"investments":"HEALTHY","scanner":"FAILED"})
 def test_repeated_cycle_is_skipped_not_duplicated(self):
  with tempfile.TemporaryDirectory() as td:
   r=self.reg(Path(td)/"x.db");n=[]
   self.assertEqual(run_controlled_cycle(r,"scanner","r1",T,lambda:n.append(1)).outcome,"SUCCEEDED")
   self.assertEqual(run_controlled_cycle(r,"scanner","r2",T+timedelta(minutes=1),lambda:n.append(2)).outcome,"SKIPPED_NOT_DUE")
   self.assertEqual(n,[1])
 def test_restart_uses_same_durable_schedule(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"x.db";r=self.reg(db)
   run_controlled_cycle(r,"scanner","r1",T,lambda:None)
   r2=self.reg(db)
   self.assertEqual(run_controlled_cycle(r2,"scanner","r2",T+timedelta(minutes=2),lambda:None).outcome,"SKIPPED_NOT_DUE")
if __name__=="__main__":unittest.main()
